# strip_spoiler_nodes.py — competition gliders fly with spoilers/airbrakes
# RETRACTED.  Several cesium.gltf models ship with the spoiler paddles in the
# DEPLOYED position (raised up on their arms), which makes the glider look
# broken in flight — panels sticking up off the wing, detached-looking plates.
# Same proven approach as strip_gear_nodes / strip_engine_nodes: clear the
# `mesh` reference on every spoiler/airbrake node so it renders nothing, while
# leaving the node in the hierarchy so nothing else breaks.
#
# FLAPS ARE KEPT — they're flush control surfaces on the trailing edge; removing
# them would leave a notch in the wing.  Only the deployable top-surface
# spoilers / airbrakes are stripped.
#
# Usage: py -3.11 strip_spoiler_nodes.py
# After running: bump MODEL_CACHE_V in tracker.html

import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))

# Match spoiler / airbrake but NOT flap, and not bare "brake" (wheel brake etc.)
SPOILER_PATTERNS = re.compile(r'spoiler|airbrake|air_brake|dive_?brake', re.IGNORECASE)

JOBS = [
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
    "assets/Glider models/js3_full/models/js3_cesium.gltf",
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
    "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
    "assets/Glider models/ls4 clean/exterior.gltf",
]


def process(rel):
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print(f"  MISSING: {path}")
        return 0
    g = json.load(open(path, encoding="utf-8-sig"))
    stripped = []
    for node in g.get("nodes", []):
        name = node.get("name", "")
        if "mesh" in node and SPOILER_PATTERNS.search(name):
            del node["mesh"]
            stripped.append(name)
    if stripped:
        json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  {os.path.basename(path):42s} stripped {len(stripped)}")
    return len(stripped)


total = 0
for rel in JOBS:
    total += process(rel)
print(f"\nDone. {total} spoiler/airbrake nodes stripped. Bump MODEL_CACHE_V.")
