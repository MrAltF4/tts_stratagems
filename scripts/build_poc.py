"""Proof of concept: game-datacards zip -> repo tree + manifest + deck sheets + TTS sample bag.

usage: python3 -I build_poc.py <zip> <outdir> [card_back.jpg]
The manifest stores paths relative to the repo's 11e/ folder; the TTS side supplies the base URL.
"""
import io, json, re, sys, zipfile, hashlib, math, os
from PIL import Image

import shutil
ZIP, OUT = sys.argv[1], sys.argv[2]
BACK = sys.argv[3] if len(sys.argv) > 3 else None
VERSION = "11e"
SMALL = {"of", "the", "to", "a", "an", "and", "in", "on", "for"}


def slug(s):
    s = s.lower().replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def file_slug(stem):
    # keep snake_case, strip apostrophes / odd chars
    s = stem.lower().replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9_-]+", "_", s).strip("_")


def title(stem):
    words = stem.replace("’", "'").replace("_", " ").split(" ")
    out = []
    for i, w in enumerate(words):
        out.append(w if (i and w in SMALL) else w[:1].upper() + w[1:])
    return " ".join(out)


def grid(n, max_cols=4):
    cols = min(n, 3 if n <= 6 else max_cols)
    return cols, math.ceil(n / cols)


def stitch(paths, dest):
    ims = [Image.open(p).convert("RGBA") for p in paths]
    w, h = ims[0].size
    assert all(i.size == (w, h) for i in ims), "card sizes differ"
    cols, rows = grid(len(ims))
    sheet = Image.new("RGBA", (cols * w, rows * h), (0, 0, 0, 0))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(dest, optimize=True)
    return cols, rows, sheet.size


z = zipfile.ZipFile(ZIP)
tree = {}  # (faction_or_core, detachment) -> {stem: bytes}
seen_hash = {}
for info in z.infolist():
    if not info.filename.endswith(".png"):
        continue
    parts = info.filename.split("/")
    data = z.read(info)
    if parts[0] == "basic":
        key = ("core", None)
        stem = parts[1][:-4]
    else:
        key = (parts[0], parts[1])
        stem = parts[2][:-4]
    tree.setdefault(key, {})[stem] = data

# ---- trim transparent padding ----
# game-datacards exports each card with a blank transparent band above the art. In TTS the card
# object is the whole image, so that band becomes an invisible slab. Crop every card to the
# union of all cards' visible pixels so all cards stay identical in size.
def alpha_bbox(data):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    return im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()


_boxes = [alpha_bbox(d) for grp in tree.values() for d in grp.values()]
CROP = (min(b[0] for b in _boxes), min(b[1] for b in _boxes),
        max(b[2] for b in _boxes), max(b[3] for b in _boxes))


def crop_png(data):
    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGBA").crop(CROP).save(out, "PNG", optimize=True)
    return out.getvalue()


for _grp in tree.values():
    for _stem in _grp:
        _grp[_stem] = crop_png(_grp[_stem])
print("cropped every card to", CROP, "->", (CROP[2] - CROP[0], CROP[3] - CROP[1]))

repo = os.path.join(OUT, "repo", VERSION)
manifest = {"edition": "11e", "card_back": "card_back.jpg", "factions": [], "core": None}
fac = {}


def write_group(dirpath, urlpath, cards):
    os.makedirs(dirpath, exist_ok=True)
    entries, files = [], []
    for stem in sorted(cards):
        fn = file_slug(stem) + ".png"
        fp = os.path.join(dirpath, fn)
        with open(fp, "wb") as f:
            f.write(cards[stem])
        files.append(fp)
        entries.append({"name": title(stem), "file": fn,
                        "path": f"{urlpath}/{fn}",
                        "sha1": hashlib.sha1(cards[stem]).hexdigest()[:12]})
    cols, rows, size = stitch(files, os.path.join(dirpath, "_deck.png"))
    for i, e in enumerate(entries):
        e["deck_index"] = i
    return {"cards": entries, "deck": {"path": f"{urlpath}/_deck.png",
            "cols": cols, "rows": rows, "sheet_px": list(size), "count": len(entries)}}


for (f, d), cards in sorted(tree.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
    if f == "core":
        manifest["core"] = {"name": "Core Stratagems", "slug": "core",
                            **write_group(os.path.join(repo, "core"), "core", cards)}
    else:
        fe = fac.setdefault(f, {"name": f, "slug": slug(f), "detachments": []})
        fe["detachments"].append({"name": d, "slug": slug(d),
                                  **write_group(os.path.join(repo, fe["slug"], slug(d)),
                                                f"{fe['slug']}/{slug(d)}", cards)})
manifest["factions"] = list(fac.values())

if BACK:
    # fit the back to the same shape as the trimmed faces (centre-ish crop, biased to keep the logo)
    cw, ch = CROP[2] - CROP[0], CROP[3] - CROP[1]
    b = Image.open(BACK).convert("RGB")
    b = b.resize((cw, round(b.height * cw / b.width)), Image.LANCZOS)
    extra = max(0, b.height - ch)
    top = round(extra * 0.3)
    b.crop((0, top, cw, top + ch)).save(os.path.join(repo, "card_back.jpg"), quality=92)
print("done:", sum(len(v) for v in tree.values()), "cards")

# ---- manifest (written last so it can carry a build id) ----
# TTS caches downloaded images by URL and never re-downloads them, and GitHub's raw host caches
# for a few minutes. The build id changes whenever any image changes; the TTS script appends it to
# every image URL (?v=<build>) so updated art is always fetched fresh.
h = hashlib.sha1()
for dp, _, fs in sorted(os.walk(repo)):
    for fn in sorted(fs):
        if fn != "manifest.json":
            h.update(open(os.path.join(dp, fn), "rb").read())
manifest["build"] = h.hexdigest()[:8]
with open(os.path.join(repo, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
print("build id:", manifest["build"])
