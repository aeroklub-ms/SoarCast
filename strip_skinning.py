# strip_skinning.py — remove skeletal skinning from a glTF.
#
# THIRD spec violation in the MSFS/Babylon glider exports (after the
# COLOR_0 and VEC4-NORMAL bugs — see remove_vertex_colors.py and
# fix_vec4_normals.py): d2c and ls4 declare WEIGHTS_0 accessors as SCALAR
# (single-bone parts), where the glTF spec requires VEC4. CesiumJS then
# declares `in float a_weights_0` and generates
#
#   skinnedMatrix += a_weights_0.x * u_jointMatrices[int(a_joints_0.x)];
#
# — field selection on a float, which no GLSL compiler accepts.
#
# The tracker renders gliders statically (runAnimations: false; the
# skinning only ever drove control-surface deflections), so the fix is to
# drop skinning outright: JOINTS_*/WEIGHTS_* attributes, node skin
# references, and the skins array. Vertices then render in bind pose via
# the node hierarchy, which is the neutral pose these models load in
# anyway.
#
# Usage: python strip_skinning.py <model.gltf> [...]

import json
import sys

for path in sys.argv[1:]:
    g = json.load(open(path, encoding="utf-8-sig"))
    removed_attrs = removed_skins = 0
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            for key in [k for k in attrs
                        if k.startswith("JOINTS") or k.startswith("WEIGHTS")]:
                del attrs[key]
                removed_attrs += 1
    for node in g.get("nodes", []):
        if "skin" in node:
            del node["skin"]
            removed_skins += 1
    g.pop("skins", None)
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{path}: removed {removed_attrs} JOINTS/WEIGHTS attr(s), "
          f"{removed_skins} node skin ref(s)")
