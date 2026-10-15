"""manifest.json -> TTS saved-object JSON (Faction bag > Detachment bag > Deck of cards).

usage: python3 -I gen_tts.py <manifest.json> <base_url_of_11e_folder> <out.json>
Structure follows TTS's saved-object format; NOT yet tested inside TTS.
"""
import json, sys, hashlib

MANIFEST, BASE, OUT = sys.argv[1:4]
BASE = BASE.rstrip("/") + "/"
m = json.load(open(MANIFEST, encoding="utf-8"))
BACK = BASE + m["card_back"]
deck_key = [0]


def guid(s):
    return hashlib.md5(s.encode()).hexdigest()[:6]


def tf(x=0.0, y=1.0, z=0.0, rot_y=180, rot_z=0, scale=1.0):
    return {"posX": x, "posY": y, "posZ": z, "rotX": 0, "rotY": rot_y, "rotZ": rot_z,
            "scaleX": scale, "scaleY": 1.0, "scaleZ": scale}


def base(name, nick, g, transform, colour=None):
    o = {"GUID": guid(g), "Name": name, "Transform": transform, "Nickname": nick,
         "Description": "", "GMNotes": "", "AltLookAngle": {"x": 0, "y": 0, "z": 0},
         "ColorDiffuse": colour or {"r": 0.7, "g": 0.7, "b": 0.7},
         "LayoutGroupSortIndex": 0, "Value": 0, "Locked": False, "Grid": True,
         "Snap": True, "IgnoreFoW": False, "MeasureMovement": False, "DragSelectable": True,
         "Autoraise": True, "Sticky": True, "Tooltip": True, "GridProjection": False,
         "HideWhenFaceDown": False, "Hands": False, "LuaScript": "", "LuaScriptState": "",
         "XmlUI": ""}
    return o


def make_deck(group, path):
    deck_key[0] += 1
    k = deck_key[0]
    d = group["deck"]
    custom = {str(k): {"FaceURL": BASE + d["path"], "BackURL": BACK, "NumWidth": d["cols"],
                       "NumHeight": d["rows"], "BackIsHidden": True, "UniqueBack": False, "Type": 0}}
    cards = []
    for i, c in enumerate(group["cards"]):
        o = base("Card", c["name"], f"{path}/{c['file']}", tf(rot_z=180))
        o.update({"CardID": k * 100 + i, "SidewaysCard": False, "CustomDeck": custom,
                  "Description": path, "HideWhenFaceDown": True, "Hands": True})
        cards.append(o)
    deck = base("DeckCustom", group["name"] + " Stratagems", path + "/deck",
                tf(rot_z=180))
    deck.update({"DeckIDs": [c["CardID"] for c in cards], "CustomDeck": custom,
                 "SidewaysCard": False, "HideWhenFaceDown": True, "Hands": False,
                 "ContainedObjects": cards})
    return deck


def make_bag(nick, path, contents, colour):
    b = base("Bag", nick, path + "/bag", tf(rot_y=0), colour)
    b["ContainedObjects"] = contents
    return b


top = []
for f in m["factions"]:
    dets = [make_bag(d["name"], f"{f['slug']}/{d['slug']}", [make_deck(d, f"{f['slug']}/{d['slug']}")],  # deck nickname uses d["name"]
                     {"r": 0.25, "g": 0.4, "b": 0.35}) for d in f["detachments"]]
    top.append(make_bag(f"{f['name']} - Stratagems", f["slug"], dets, {"r": 0.15, "g": 0.25, "b": 0.2}))
if m.get("core"):
    top.append(make_bag("Core Stratagems", "core", [make_deck(m["core"], "core")],
                        {"r": 0.5, "g": 0.5, "b": 0.5}))

save = {"SaveName": "40K Stratagems (sample)", "GameMode": "", "Date": "", "VersionNumber": "",
        "GameType": "", "GameComplexity": "", "Tags": [], "Gravity": 0.5, "PlayArea": 0.5,
        "Table": "", "Sky": "", "Note": "", "TabStates": {}, "LuaScript": "", "LuaScriptState": "",
        "XmlUI": "", "ObjectStates": top}
for i, o in enumerate(top):  # lay bags out in a row so they don't stack
    o["Transform"]["posX"] = i * 4.0
json.dump(save, open(OUT, "w", encoding="utf-8"), indent=1)
print("bags:", len(top), "decks:", deck_key[0])
