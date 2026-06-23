# fix_white_gliders.py — make every exterior glider render as clean opaque
# white gelcoat, EXCEPT the canopy glass (which stays tinted + transparent).
#
# Why:
#   • broadcast-clean look — uniform white airframes read instantly at any
#     distance, no dark/broken/half-transparent texture artifacts
#   • faster load — removing baseColorTexture means the airframe texture
#     PNGs/JPEGs no longer need to download + decode + GPU-upload per pilot
#   • non-transparent — clears stray alpha<1 materials that caused the
#     see-through / floating-white-rectangle glitches
#
# Per material:
#   • canopy GLASS (name matches glass/windshield/windscreen/tinted/
#     canopy.001) → LEFT ALONE (the canopy fix already set these to tinted
#     transparent glass)
#   • everything else → baseColorFactor [1,1,1,1], no baseColorTexture,
#     metallic 0, roughness 0.35, alphaMode OPAQUE, emissive 0
#
# Usage: py -3.11 fix_white_gliders.py
# After running: bump MODEL_CACHE_V in tracker.html

import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))

# Glass materials to PRESERVE (transparent canopy).  Matches the exact set the
# canopy fix script targeted, without catching frames/handles ("window" is
# deliberately excluded so Canopy_window_frames goes white).
GLASS_RE = re.compile(r'glass|windshield|windscreen|tinted|canopy\.001', re.IGNORECASE)

EXTERIORS = [
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/js3_full/models/js3_cesium.gltf",
    "assets/Glider models/ls4 clean/exterior.gltf",
    "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
]


def process(rel):
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print(f"  MISSING: {rel}")
        return
    g = json.load(open(path, encoding="utf-8-sig"))
    white = glass = 0
    for m in g.get("materials", []):
        name = m.get("name", "")
        if GLASS_RE.search(name):
            glass += 1
            continue   # leave canopy glass exactly as-is
        pbr = m.setdefault("pbrMetallicRoughness", {})
        pbr["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]
        pbr.pop("baseColorTexture", None)
        pbr["metallicFactor"]  = 0.0
        pbr["roughnessFactor"] = 0.35
        m["alphaMode"] = "OPAQUE"
        m.pop("alphaCutoff", None)
        m["emissiveFactor"] = [0.0, 0.0, 0.0]
        m.pop("emissiveTexture", None)
        m.pop("normalTexture", None)
        m.pop("occlusionTexture", None)
        # doubleSided = True: thin wing/tail skins on these models have
        # single-sided materials whose normals point the wrong way on the
        # top surface, so the top half of the wing culls and renders
        # see-through.  Disabling backface culling makes both faces draw.
        m["doubleSided"] = True
        white += 1
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  {os.path.basename(path):42s} white={white:3d}  glass-kept={glass}")


print("Making exterior airframes opaque white (canopy glass preserved):")
for rel in EXTERIORS:
    process(rel)
print("\nDone. Bump MODEL_CACHE_V in tracker.html.")
