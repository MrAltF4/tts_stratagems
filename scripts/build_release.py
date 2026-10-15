"""
Build a release: every pulled zip in scripts/input -> 11e-stratagems/<version>/ + versions.json.

    python -I build_release.py                      (asks for the version and whether it's latest)
    python -I build_release.py --version v0.2 --latest --yes
    python -I build_release.py --version v0.3 --no-latest --yes

Options:
    --input DIR       pulled zips + .source.json files       (default: scripts/input)
    --root DIR        hosted folder holding versions.json    (default: 11e-stratagems)
    --card-back FILE  card back image                        (default: assets/card_back_original.jpg)
    --version vX.Y    release folder name                    (default: asks, suggesting the next one)
    --latest / --no-latest   make it the TTS default or not  (default: asks)
    --yes             don't ask for confirmation before writing
    --with-cards      also publish every card as its own PNG (off by default: TTS only uses the
                      _deck.png sheets, and the singles more than double the release size)

What it does:
  - reads every datacards_*.zip (and its .source.json from pull_datacards.py)
  - skips factions with no stratagems, keeps one copy of the core cards (checks they match)
  - checks card counts against the game-datacards data the cards were made from
  - crops the transparent band off every card, fits the card back to the same shape
  - cleans names: strips the _1/_2 game-datacards adds to repeated stratagems, plain-ASCII slugs
  - renames factions to their common names for TTS (scripts/faction_names.json, e.g. Asuryani -> Aeldari)
  - writes <root>/<version>/ (_deck.png sheets, card_back.jpg, manifest.json; single cards with --with-cards)
  - adds the version to <root>/versions.json (and sets it as latest if asked)
It never overwrites an existing version folder and never touches GitHub; you commit and push.
"""
import argparse
import collections
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import unicodedata
import zipfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SMALL = {"of", "the", "to", "a", "an", "and", "in", "on", "for", "at", "by"}
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)$")


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------
def tidy(s):
    """Display text: curly apostrophes -> ', non-breaking/odd hyphens -> -."""
    return (s.replace("’", "'").replace("‘", "'")
             .replace("‑", "-").replace("‐", "-").replace("–", "-"))


def ascii_fold(s):
    """ë -> e, â -> a, etc. so slugs/URLs stay plain ASCII."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def slug(s):
    s = ascii_fold(tidy(s)).lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def file_slug(stem):
    s = ascii_fold(tidy(stem)).lower().replace("'", "")
    return re.sub(r"[^a-z0-9_-]+", "_", s).strip("_")


def card_title(stem):
    """'armour_of_contempt_3' -> 'Armour of Contempt'. game-datacards numbers repeated stratagem
    names across detachments (_1, _2...); the number isn't part of the name."""
    stem = re.sub(r"_\d+$", "", tidy(stem))
    words = stem.replace("_", " ").split(" ")
    out = []
    for i, w in enumerate(words):
        out.append(w if (i and w in SMALL) else w[:1].upper() + w[1:])
    return " ".join(out)


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------
def alpha_bbox(data):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    return im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()


def crop_png(data, box):
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGBA").crop(box).save(out, "PNG", optimize=True)
    return out.getvalue()


def grid(n, max_cols=4):
    cols = min(n, 3 if n <= 6 else max_cols)
    return cols, math.ceil(n / cols)


def stitch(card_bytes, dest):
    ims = [Image.open(io.BytesIO(b)).convert("RGBA") for b in card_bytes]
    w, h = ims[0].size
    if any(i.size != (w, h) for i in ims):
        raise BuildError(f"card sizes differ in {dest}")
    cols, rows = grid(len(ims))
    sheet = Image.new("RGBA", (cols * w, rows * h), (0, 0, 0, 0))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(dest, optimize=True)
    return cols, rows, sheet.size


def fit_back(path, size, dest):
    """Resize the back to the card width and crop to card height (biased to keep the logo at top)."""
    cw, ch = size
    b = Image.open(path).convert("RGB")
    b = b.resize((cw, round(b.height * cw / b.width)), Image.LANCZOS)
    if b.height < ch:
        b = b.resize((cw, ch), Image.LANCZOS)
    top = round(max(0, b.height - ch) * 0.3)
    b.crop((0, top, cw, top + ch)).save(dest, quality=92)


# ---------------------------------------------------------------------------
# versions
# ---------------------------------------------------------------------------
def version_key(v):
    m = VERSION_RE.match(v)
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def load_versions(root):
    path = os.path.join(root, "versions.json")
    if not os.path.exists(path):
        return path, {"latest": None, "versions": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("versions", [])
    data.setdefault("latest", None)
    return path, data


def suggest_version(versions):
    known = [version_key(v) for v in versions if VERSION_RE.match(v)]
    if not known:
        return "v0.1"
    major, minor = max(known)
    return f"v{major}.{minor + 1}"


# ---------------------------------------------------------------------------
# read input
# ---------------------------------------------------------------------------
def read_input(indir):
    zips = sorted(f for f in os.listdir(indir) if f.lower().endswith(".zip"))
    if not zips:
        raise BuildError(f"no zips in {indir} - run pull_all.bat first")

    factions = {}                       # name -> {"detachments": {det: {stem: bytes}}, "source": {...}}
    core_versions = collections.defaultdict(set)   # stem -> {sha1}
    core = {}
    skipped, problems, warnings = [], [], []

    for zf in zips:
        src_path = os.path.join(indir, zf[:-4] + ".source.json")
        source = {}
        if os.path.exists(src_path):
            with open(src_path, encoding="utf-8") as f:
                source = json.load(f)
        else:
            warnings.append(f"{zf}: no .source.json (pulled by hand?) - counts can't be checked")

        z = zipfile.ZipFile(os.path.join(indir, zf))   # zipfile keeps UTF-8 names intact (unzip CLI doesn't)
        dets = collections.defaultdict(dict)
        tops = set()
        for info in z.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".png"):
                continue
            parts = info.filename.split("/")
            data = z.read(info)
            if parts[0] == "basic" and len(parts) == 2:
                stem = parts[1][:-4]
                core_versions[stem].add(hashlib.sha1(data).hexdigest())
                core.setdefault(stem, data)
            elif len(parts) == 3:
                tops.add(parts[0])
                dets[parts[1]][parts[2][:-4]] = data
            else:
                problems.append(f"{zf}: unexpected file {info.filename}")

        if not dets:
            skipped.append(source.get("faction") or zf)
            continue
        if len(tops) != 1:
            problems.append(f"{zf}: expected one faction folder, found {sorted(tops)}")
            continue
        name = tops.pop()
        if name in factions:
            problems.append(f"{zf}: faction '{name}' appears in more than one zip")
            continue

        n_cards = sum(len(c) for c in dets.values())
        expected = source.get("expected_stratagems")
        if expected is not None and expected != n_cards:
            problems.append(f"{name}: zip has {n_cards} cards but the data says {expected} - re-pull it")
        factions[name] = {"detachments": dets, "source": source, "zip": zf}

    if not core:
        problems.append("no core (basic/) cards found in any zip")
    for stem, hashes in core_versions.items():
        if len(hashes) > 1:
            problems.append(f"core card '{stem}' differs between zips - re-pull so they match")

    data_versions = sorted({f["source"].get("data_version") for f in factions.values()} - {None})
    if len(data_versions) > 1:
        warnings.append(f"zips come from different game-datacards data versions {data_versions} "
                        "- consider re-pulling everything")
    return factions, core, skipped, problems, warnings, data_versions


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
def write_group(dirpath, urlpath, cards, box, problems, with_cards):
    """Writes the group's _deck.png. Individual card PNGs are only written with --with-cards:
    TTS only uses the deck sheet, and the singles roughly double the release size."""
    os.makedirs(dirpath, exist_ok=True)
    entries, cropped, used = [], [], {}
    for stem in sorted(cards):
        fn = file_slug(stem) + ".png"
        if fn in used:
            problems.append(f"{urlpath}: '{stem}' and '{used[fn]}' both become {fn}")
            continue
        used[fn] = stem
        data = crop_png(cards[stem], box)
        cropped.append(data)
        entry = {"name": card_title(stem), "sha1": hashlib.sha1(data).hexdigest()[:12],
                 "deck_index": len(entries)}
        if with_cards:
            with open(os.path.join(dirpath, fn), "wb") as f:
                f.write(data)
            entry.update({"file": fn, "path": f"{urlpath}/{fn}"})
        entries.append(entry)
    cols, rows, size = stitch(cropped, os.path.join(dirpath, "_deck.png"))
    return {"cards": entries, "deck": {"path": f"{urlpath}/_deck.png", "cols": cols, "rows": rows,
                                       "sheet_px": list(size), "count": len(entries)}}


def load_renames(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("renames", {})


def display_name(name, renames):
    return renames.get(name) or renames.get(tidy(name)) or tidy(name)


def build(factions, core, out, card_back, version, data_versions, with_cards, renames):
    problems = []

    # one crop box for every card so all cards (and so all deck cells) are the same size
    boxes = [alpha_bbox(d) for f in factions.values() for c in f["detachments"].values() for d in c.values()]
    boxes += [alpha_bbox(d) for d in core.values()]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
           max(b[2] for b in boxes), max(b[3] for b in boxes))
    card_size = (box[2] - box[0], box[3] - box[1])
    print(f"Cropping every card to {card_size[0]}x{card_size[1]} (removes the transparent band)")

    sources = [f["source"] for f in factions.values() if f["source"]]
    manifest = {
        "edition": "11e",
        "version": version,
        "card_back": "card_back.jpg",
        "source": {
            "name": "game-datacards.eu",
            "data_version": data_versions[0] if len(data_versions) == 1 else data_versions,
            "site_version": next((s.get("site_version") for s in sources if s.get("site_version")), None),
            "pulled_from": min((s["pulled_at"] for s in sources if s.get("pulled_at")), default=None),
            "pulled_to": max((s["pulled_at"] for s in sources if s.get("pulled_at")), default=None),
        },
        "factions": [],
        "core": None,
    }

    fac_slugs = {}
    for name in sorted(factions, key=lambda n: display_name(n, renames).lower()):
        f = factions[name]
        shown = display_name(name, renames)
        fslug = slug(shown)
        if fslug in fac_slugs:
            problems.append(f"factions '{name}' and '{fac_slugs[fslug]}' both become '{fslug}'")
            continue
        fac_slugs[fslug] = name
        n = len(f["detachments"])
        renamed = f"  (from {tidy(name)})" if shown != tidy(name) else ""
        print(f"  {shown}: {n} detachment{'s' if n != 1 else ''}{renamed}", flush=True)
        entry = {"name": shown, "source_name": tidy(name), "slug": fslug, "detachments": [],
                 "data_version": f["source"].get("data_version"),
                 "updated": f["source"].get("faction_updated")}
        det_slugs = {}
        for det in sorted(f["detachments"], key=lambda d: tidy(d).lower()):
            dslug = slug(det)
            if dslug in det_slugs:
                problems.append(f"{name}: detachments '{det}' and '{det_slugs[dslug]}' both become '{dslug}'")
                continue
            det_slugs[dslug] = det
            group = write_group(os.path.join(out, fslug, dslug), f"{fslug}/{dslug}",
                                f["detachments"][det], box, problems, with_cards)
            entry["detachments"].append({"name": tidy(det), "slug": dslug, **group})
        manifest["factions"].append(entry)

    print("  Core Stratagems", flush=True)
    manifest["core"] = {"name": "Core Stratagems", "slug": "core",
                        **write_group(os.path.join(out, "core"), "core", core, box, problems, with_cards)}

    fit_back(card_back, card_size, os.path.join(out, "card_back.jpg"))

    # build id: changes whenever any image changes; the TTS script appends ?v=<build> to image URLs
    # so TTS (which caches by URL) always fetches changed art
    h = hashlib.sha1()
    for dp, dirs, fs in os.walk(out):
        dirs.sort()
        for fn in sorted(fs):
            with open(os.path.join(dp, fn), "rb") as fh:
                h.update(fh.read())
    manifest["build"] = h.hexdigest()[:8]
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest, problems


def validate(out, manifest):
    """Every manifest path exists, sheets have the right size, every deck cell has visible card edges."""
    problems = []
    back = os.path.join(out, manifest["card_back"])
    if not os.path.exists(back):
        problems.append("card_back.jpg missing")
    groups = [(f"{f['name']} / {d['name']}", d) for f in manifest["factions"] for d in f["detachments"]]
    groups.append(("Core", manifest["core"]))
    card_w = card_h = None
    for label, g in groups:
        for c in g["cards"]:
            if "path" in c and not os.path.exists(os.path.join(out, c["path"])):
                problems.append(f"{label}: missing {c['path']}")
        sheet_path = os.path.join(out, g["deck"]["path"])
        if not os.path.exists(sheet_path):
            problems.append(f"{label}: missing deck sheet")
            continue
        sheet = Image.open(sheet_path).convert("RGBA")
        cols, rows, n = g["deck"]["cols"], g["deck"]["rows"], g["deck"]["count"]
        if n != len(g["cards"]) or cols * rows < n:
            problems.append(f"{label}: deck grid {cols}x{rows} doesn't fit {n} cards")
            continue
        w, h = sheet.width // cols, sheet.height // rows
        card_w, card_h = card_w or w, card_h or h
        if (w, h) != (card_w, card_h):
            problems.append(f"{label}: cell size {w}x{h} differs from {card_w}x{card_h}")
        alpha = sheet.getchannel("A")
        for i in range(n):
            x0, y0 = (i % cols) * w, (i // cols) * h
            top = alpha.crop((x0, y0, x0 + w, y0 + 1)).getbbox()
            bottom = alpha.crop((x0, y0 + h - 1, x0 + w, y0 + h)).getbbox()
            if not top or not bottom:
                problems.append(f"{label}: card {i + 1} has a blank top/bottom edge (crop wrong?)")
    return problems


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def ask_yes_no(prompt, default):
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} ({hint}): ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def main(argv):
    p = argparse.ArgumentParser(description="Build a stratagem card release from pulled zips.")
    p.add_argument("--input", default=os.path.join(HERE, "input"))
    p.add_argument("--root", default=os.path.join(REPO, "11e-stratagems"))
    p.add_argument("--card-back", default=os.path.join(REPO, "assets", "card_back_original.jpg"))
    p.add_argument("--version")
    p.add_argument("--latest", dest="latest", action="store_true", default=None)
    p.add_argument("--no-latest", dest="latest", action="store_false")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--names", default=os.path.join(HERE, "faction_names.json"),
                   help="faction renames for TTS (default: scripts/faction_names.json)")
    p.add_argument("--with-cards", action="store_true",
                   help="also publish each card as its own PNG (TTS doesn't need them)")
    args = p.parse_args(argv)

    versions_path, versions = load_versions(args.root)

    print(f"Reading zips in {args.input} ...")
    factions, core, skipped, problems, warnings, data_versions = read_input(args.input)
    n_dets = sum(len(f["detachments"]) for f in factions.values())
    n_cards = sum(len(c) for f in factions.values() for c in f["detachments"].values())
    print()
    print(f"  Factions:     {len(factions)}" + (f"  (skipped, no stratagems: {', '.join(skipped)})" if skipped else ""))
    print(f"  Detachments:  {n_dets}")
    print(f"  Cards:        {n_cards} detachment + {len(core)} core")
    print(f"  Data version: {', '.join(str(v) for v in data_versions) or 'unknown'} (game-datacards)")
    renames = load_renames(args.names)
    found = set(factions) | {tidy(n) for n in factions}
    for old in renames:
        if old not in found:
            warnings.append(f"rename '{old}' in {os.path.basename(args.names)} matches no faction "
                            "(did game-datacards rename it?)")
    for w in warnings:
        print(f"  WARNING: {w}")
    if problems:
        print("\nProblems found - nothing was written:")
        for pr in problems:
            print(f"  - {pr}")
        return 1

    print(f"\nExisting versions: {', '.join(versions['versions']) or 'none'}"
          f"   (latest: {versions['latest'] or 'none'})")
    version = args.version
    while True:
        if version is None:
            version = ask("New version", suggest_version(versions["versions"]))
        if not VERSION_RE.match(version or ""):
            print("  Use the form v<number>.<number>, e.g. v0.2 or v1.0")
        elif version in versions["versions"] or os.path.exists(os.path.join(args.root, version)):
            print(f"  {version} already exists - pick another (published versions are never overwritten)")
        else:
            break
        if args.version:
            return 1
        version = None

    latest = args.latest
    if latest is None:
        latest = ask_yes_no(f"Make {version} the latest (what TTS picks by default)?", True)

    out = os.path.join(args.root, version)
    print(f"\nWill write {out}" + ("  (including individual card images)" if args.with_cards else ""))
    print(f"and add {version} to versions.json" + (" as latest." if latest else " (latest stays "
                                                    f"{versions['latest'] or 'unset'})."))
    if not args.yes and not ask_yes_no("Go ahead?", True):
        print("Cancelled - nothing was written.")
        return 1

    # build into a temporary folder and only rename it into place once it's complete and checked
    tmp = os.path.join(args.root, f".building-{version}")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        print("\nBuilding...")
        manifest, problems = build(factions, core, tmp, args.card_back, version, data_versions,
                                   args.with_cards, renames)
        print("Checking the output...")
        problems += validate(tmp, manifest)
        if problems:
            print("\nProblems found - nothing was published:")
            for pr in problems:
                print(f"  - {pr}")
            return 1
        os.replace(tmp, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    versions["versions"] = sorted(set(versions["versions"]) | {version}, key=version_key, reverse=True)
    if latest:
        versions["latest"] = version
    with open(versions_path, "w", encoding="utf-8") as f:
        json.dump({"latest": versions["latest"], "versions": versions["versions"]}, f, indent=2)
        f.write("\n")

    n_files = sum(len(fs) for _, _, fs in os.walk(out))
    print(f"\nDone: {version} written to {out}  ({n_files} files, build {manifest['build']})")
    print(f"versions.json: latest = {versions['latest']}, versions = {', '.join(versions['versions'])}")
    print("\nNext: commit and push with GitHub Desktop (or git). Once it's on GitHub,"
          f" {version} appears in the TTS Version dropdown.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BuildError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled - nothing was published.")
        sys.exit(1)
