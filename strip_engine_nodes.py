# strip_engine_nodes.py — competition gliders fly with the motor/sustainer
# retracted; the AS33 and JS3 cesium.gltf models ship with the pylon UP and
# the prop visible, which makes them read as motor gliders instead of pure
# racers.  Same approach as strip_gear_nodes.py: leave the nodes in the
# scene graph (don't break the hierarchy) but clear their `mesh` reference
# so they render nothing.
#
# Patterns matched (case-insensitive):
#   MOTOR_*, PROP_*, ENGINE_*, *_pylon, *_FES, *_sustainer, *_mast
#
# Usage: py -3.11 strip_engine_nodes.py
# After running: bump MODEL_CACHE_V in tracker.html to ?v=9

import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))

ENGINE_PATTERNS = re.compile(
    r'motor|^prop_|engine|pylon|sustain|turbo|fes',
    re.IGNORECASE
)

JOBS = [
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
    "assets/Glider models/js3_full/models/js3_cesium.gltf",
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/ls4 clean/exterior.gltf",
    "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
]


def process(rel):
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print(f"  MISSING: {path}")
        return 0
    g = json.load(open(path, encoding="utf-8-sig"))
    nodes = g.get("nodes", [])
    stripped = []
    for node in nodes:
        name = node.get("name", "")
        if "mesh" in node and ENGINE_PATTERNS.search(name):
            del node["mesh"]
            stripped.append(name)
    if stripped:
        json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
        print(f"  Stripped {len(stripped)} engine/prop nodes:")
        for n in stripped:
            print(f"    - {n}")
    else:
        print(f"  (no engine nodes)")
    return len(stripped)


total = 0
for rel in JOBS:
    print(f"\n{'='*55}")
    print(f"Model: {os.path.basename(rel)}")
    total += process(rel)

print(f"\n{'='*55}")
print(f"Done. {total} engine/prop nodes stripped.")
print("Bump MODEL_CACHE_V in tracker.html to ?v=9")
