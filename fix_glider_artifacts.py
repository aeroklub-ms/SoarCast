# fix_glider_artifacts.py — Plan B Stage 1
#
# Three fixes from a full material audit across every glider:
#
# 1. AS33 $REG_EXT has emissiveFactor [1,1,1] — the registration text was
#    glowing pure white in every shot, including the photo Jon flagged.
#    Zero the emissive so it lights normally with the rest of the body.
#
# 2. JS3 "Gold" material (baseColorFactor [0.85, 0.78, 0.02]) — bright
#    saturated yellow with no texture override.  This is the suspected
#    wing-root bright-spot artifact.  Map to a desaturated dark grey
#    that matches an unpainted gelcoat trim strip.
#
# 3. LS4 has four internal helper meshes (`VRCollision`, `Box_invisiable`,
#    `power`, `needle_orange`) plus `default3`/`Clear` instruments on JS3
#    that should never be visible from outside the canopy.  Set alpha=0
#    + alphaMode=BLEND so even if the geometry shows through, they don't
#    register as bright artifacts.
#
# Plus a global pass: bump every body/wing/livery material from the
# placeholder gelcoat (M=0, R=0.4) towards a real polished-fibreglass
# response (M=0.04, R=0.25).  Subtle on most surfaces but adds the wet
# specular sheen real gliders have.
#
# Usage: py -3.11 fix_glider_artifacts.py
# After running: bump MODEL_CACHE_V to ?v=10

import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))

# (model path, list of (material name, action) tuples)
# action:
#   ('emi0',)                 → zero emissiveFactor
#   ('bcf', [r,g,b,a])        → overwrite baseColorFactor
#   ('hide',)                 → alpha=0, alphaMode=BLEND
TARGETED_FIXES = {
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf": [
        ("$REG_EXT",   ("emi0",)),
        ("COLLISION",  ("hide",)),
    ],
    "assets/Glider models/js3_full/models/js3_cesium.gltf": [
        ("Gold",       ("bcf", [0.55, 0.50, 0.42, 1.0])),  # warm grey, not gold
        ("default3",   ("emi0",)),
        ("Clear",      ("emi0",)),
        ("Transparent",("hide",)),
        ("MC Needle",  ("hide",)),                          # internal instrument
        ("STF Needle", ("hide",)),
        ("Netto Needle.001", ("hide",)),
    ],
    "assets/Glider models/ls4 clean/exterior.gltf": [
        ("VRCollision",   ("hide",)),
        ("Box_invisiable",("hide",)),
        ("power",         ("hide",)),
        ("needle_orange", ("hide",)),
    ],
}

# All models that get the global gelcoat polish pass
ALL_MODELS = [
    "assets/Glider models/js3_full/models/js3_cesium.gltf",
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
    "assets/Glider models/ls4 clean/exterior.gltf",
    "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
]

BODY_NAME_HINTS = ("body", "fuselage", "wing", "livery", "ext_body",
                   "decal", "airframe", "skin", "fus_")

def apply_action(m, action):
    pbr = m.setdefault("pbrMetallicRoughness", {})
    if action[0] == "emi0":
        m["emissiveFactor"] = [0.0, 0.0, 0.0]
    elif action[0] == "bcf":
        pbr["baseColorFactor"] = action[1]
        pbr.pop("baseColorTexture", None)
    elif action[0] == "hide":
        pbr["baseColorFactor"] = [0, 0, 0, 0]
        pbr["metallicFactor"] = 0.0
        pbr["roughnessFactor"] = 1.0
        m["alphaMode"] = "BLEND"
        m["emissiveFactor"] = [0, 0, 0]
        m["doubleSided"] = False
        pbr.pop("baseColorTexture", None)


# Pass 1: targeted artifact fixes
for rel, fixes in TARGETED_FIXES.items():
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print(f"  MISSING: {rel}")
        continue
    g = json.load(open(path, encoding="utf-8-sig"))
    name_idx = {(m.get("name") or ""): i for i, m in enumerate(g.get("materials", []))}
    hits = 0
    for mat_name, action in fixes:
        i = name_idx.get(mat_name)
        if i is None:
            print(f"  {os.path.basename(rel)}: '{mat_name}' not found")
            continue
        apply_action(g["materials"][i], action)
        hits += 1
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  {os.path.basename(rel)}: {hits} targeted fixes applied")


# Pass 2: global gelcoat polish — every body/wing material gets a slight
# specular sheen.  Doesn't touch glass, tires, brakes, hardware (those
# already have proper M/R values from prior scripts).
print()
for rel in ALL_MODELS:
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        continue
    g = json.load(open(path, encoding="utf-8-sig"))
    touched = 0
    for m in g.get("materials", []):
        name = (m.get("name") or "").lower()
        if not any(h in name for h in BODY_NAME_HINTS):
            continue
        pbr = m.setdefault("pbrMetallicRoughness", {})
        # Only nudge — preserve explicit non-default values from prior scripts
        if pbr.get("metallicFactor", 0) <= 0.05:
            pbr["metallicFactor"] = 0.04
        if 0.30 <= pbr.get("roughnessFactor", 0.4) <= 0.50:
            pbr["roughnessFactor"] = 0.25
        touched += 1
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  {os.path.basename(rel):42s}  gelcoat polish: {touched} materials")

print("\nDone.  Bump MODEL_CACHE_V in tracker.html to ?v=10")
