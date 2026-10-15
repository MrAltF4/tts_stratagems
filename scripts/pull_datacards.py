"""
Headless pull of stratagem card zips from the game-datacards.eu image generator.

    python -I pull_datacards.py <outdir> "Necrons" ["Orks" ...]
    python -I pull_datacards.py <outdir> --all
    python -I pull_datacards.py --list

Drives the real image generator page in a hidden Chromium (Playwright), one faction per
browser session so a big export can't exhaust memory the way a 5+ faction browser export does.
For each faction it saves:
    <outdir>/datacards_<slug>.zip            the same zip a manual "Generate" gives you
    <outdir>/datacards_<slug>.source.json    which game-datacards data/site version it came from

The version info is read from the data the page itself downloaded, so it matches the zip exactly.
The image generator always uses the live ("Latest") data; it has no data-version picker.

Setup (once):  python -m pip install playwright  &&  python -m playwright install chromium
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

PAGE_URL = "https://game-datacards.eu/image-generator"
EDITION = "40k 11th Edition"
DATA_URL_PART = "/11th/gdc/"
GENERATE_TIMEOUT_MS = 10 * 60 * 1000   # rendering a big faction in-browser can take a while


def slugify(name):
    s = name.replace("’", "").replace("'", "").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def open_generator(page, captured):
    """Load the page, record every 11th-edition data file it fetches, and pick the edition."""
    def on_response(resp):
        url = resp.url
        if DATA_URL_PART in url or url.split("?")[0].endswith("/version.json"):
            try:
                captured[url.split("?")[0]] = resp.json()
            except Exception:
                pass   # not JSON / body unavailable; version info for it is just missing
    page.on("response", on_response)

    page.goto(PAGE_URL)
    page.get_by_role("button", name="Skip Tutorial").click(timeout=30000)
    # site version isn't reliably seen in traffic (may be served from cache), so ask for it directly
    try:
        captured["/version.json"] = page.evaluate(
            "() => fetch('/version.json?_t=' + Date.now()).then(r => r.json())")
    except Exception:
        pass
    page.locator(".ant-select").nth(0).click()
    page.locator(".ant-select-item-option", has_text=EDITION).first.click()
    page.wait_for_timeout(1000)


def faction_options(page):
    """All faction names in the (virtualised) dropdown; scrolls through it to collect them."""
    page.locator(".ant-select-multiple").first.click()
    page.wait_for_timeout(500)
    seen = []
    holder = page.locator(".ant-select-dropdown:visible .rc-virtual-list-holder")
    for _ in range(40):
        for t in page.locator(".ant-select-dropdown:visible .ant-select-item-option").all_inner_texts():
            if t not in seen:
                seen.append(t)
        holder.evaluate("e => e.scrollTop += 150")
        page.wait_for_timeout(100)
    page.keyboard.press("Escape")
    return seen


def select_faction(page, faction):
    """Click the exact faction name. The dropdown's search box filters on internal ids, not names,
    so typing doesn't work; scroll the virtualised list until the option is rendered instead."""
    page.locator(".ant-select-multiple").first.click()
    options = page.locator(".ant-select-dropdown:visible .ant-select-item-option")
    options.first.wait_for(timeout=30000)   # list fills once the faction data has downloaded
    holder = page.locator(".ant-select-dropdown:visible .rc-virtual-list-holder")
    exact = options.filter(has_text=re.compile("^" + re.escape(faction) + "$"))
    for _ in range(40):
        if exact.count():
            exact.first.click()
            page.keyboard.press("Escape")
            return
        holder.evaluate("e => e.scrollTop += 150")
        page.wait_for_timeout(100)
    raise RuntimeError(f"faction '{faction}' not in dropdown (use --list)")


def set_toggle(page, label, on):
    """Stratagems / Datasheets are toggle buttons: 'ant-btn-primary' means selected."""
    btn = page.locator("button", has_text=label).first
    is_on = "ant-btn-primary" in (btn.get_attribute("class") or "")
    if is_on != on:
        btn.evaluate("e => e.click()")   # the page header overlaps these buttons, so a mouse click misses

        page.wait_for_timeout(200)


def source_info(captured, faction):
    site = next((v for k, v in captured.items() if k.endswith("/version.json")), {}) or {}
    data = None
    for url, body in captured.items():
        if DATA_URL_PART in url and isinstance(body, dict) and body.get("name") == faction:
            data = (url, body)
    core = next((b for u, b in captured.items() if u.endswith(DATA_URL_PART + "core.json")), {}) or {}
    info = {
        "faction": faction,
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site_version": site.get("version"),
        "site_build": site.get("buildId"),
        "core_data_version": core.get("compatibleDataVersion"),
        "core_updated": core.get("updated"),
    }
    if data:
        url, body = data
        info.update({
            "data_url": url,
            "data_version": body.get("compatibleDataVersion"),
            "faction_updated": body.get("updated"),
            "expected_stratagems": len(body.get("stratagems") or []),
            "expected_detachments": len(body.get("detachments") or []),
        })
    else:
        info["warning"] = "faction data file not seen in page traffic; version unknown"
    return info


def pull_one(browser, faction, outdir):
    captured = {}
    context = browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 900})
    page = context.new_page()
    try:
        open_generator(page, captured)

        select_faction(page, faction)

        set_toggle(page, "Stratagems", True)
        set_toggle(page, "Datasheets", False)

        generate = page.locator("button", has_text="Generate").first
        if generate.is_disabled():
            raise RuntimeError("Generate button is disabled (faction or card type not selected?)")
        with page.expect_download(timeout=GENERATE_TIMEOUT_MS) as dl:
            generate.evaluate("e => e.click()")   # header overlaps this button too
        slug = slugify(faction)
        zip_path = os.path.join(outdir, f"datacards_{slug}.zip")
        dl.value.save_as(zip_path)

        info = source_info(captured, faction)
        info["download_name"] = dl.value.suggested_filename
        info["zip"] = os.path.basename(zip_path)
        with open(os.path.join(outdir, f"datacards_{slug}.source.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        return zip_path, info
    finally:
        context.close()


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            if argv[0] == "--list":
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                open_generator(page, {})
                for name in faction_options(page):
                    print(name)
                return 0

            outdir, wanted = argv[0], argv[1:]
            os.makedirs(outdir, exist_ok=True)
            if wanted == ["--all"]:
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                open_generator(page, {})
                wanted = faction_options(page)
                page.close()

            failed = []
            for faction in wanted:
                print(f"[{faction}] generating...", flush=True)
                try:
                    zip_path, info = pull_one(browser, faction, outdir)
                    print(f"[{faction}] saved {zip_path}  data v{info.get('data_version')}"
                          f"  ({info.get('expected_stratagems')} stratagems expected)", flush=True)
                except Exception as e:
                    failed.append(faction)
                    print(f"[{faction}] FAILED: {e}", flush=True)
            if failed:
                print("failed:", ", ".join(failed))
                return 1
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
