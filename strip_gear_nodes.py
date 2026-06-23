# strip_gear_nodes.py — Remove the mesh reference from every gear/wheel node
# in each glider cesium.gltf so the landing gear never renders.
# Nodes are kept in the scene graph (hierarchy intact) but their mesh is
# cleared, which is the standard glTF way to hide geometry without breaking
# animation rigs or parent-child transforms.
#
# Usage: py -3.11 strip_gear_nodes.py
# After running: bump MODEL_CACHE_V in tracker.html to ?v=7

import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))

# Substring patterns (case-insensitive) that identify gear/wheel nodes.
# Matched against the node's "name" field.
GEAR_PATTERNS = re.compile(
    r'gear|wheel|landing_gear|preflight_wheel|pneu|roue|bequille|jambe',
    re.IGNORECASE
)

JOBS = [
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
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
        print(f"  MISSING: {path}")
        return 0

    g = json.load(open(path, encoding="utf-8-sig"))
    nodes = g.get("nodes", [])

    stripped = []
    for node in nodes:
        name = node.get("name", "")
        if "mesh" in node and GEAR_PATTERNS.search(name):
            del node["mesh"]
            stripped.append(name)

    if stripped:
        json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
        print(f"  Stripped {len(stripped)} gear nodes:")
        for n in stripped:
            print(f"    - {n}")
    else:
        print(f"  No gear nodes found (names searched: {len(nodes)} nodes)")
    return len(stripped)


total = 0
for rel in JOBS:
    print(f"\n{'='*55}")
    print(f"Model: {os.path.basename(rel)}")
    total += process(rel)

print(f"\n{'='*55}")
print(f"Done. {total} gear nodes stripped across all models.")
print("Bump MODEL_CACHE_V in tracker.html to ?v=7")
