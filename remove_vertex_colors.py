# remove_vertex_colors.py — strip COLOR_n vertex attributes from a glTF.
#
# ROOT CAUSE of the long-standing "vec4→vec3 dimension mismatch" shader
# failures (the bug that forced glider models down to point markers on some
# GPUs): every MSFS/Babylon-exported glider carries COLOR_0 accessors that
# violate the glTF spec — VEC4 of signed BYTE (5120, not a legal COLOR
# component type at all) or unsigned SHORT (5123) without the mandatory
# "normalized": true. Fed this invalid input, CesiumJS's model pipeline
# generates GLSL that declares the attribute `in vec4 a_color_0` but the
# processed-attributes struct field `vec3 color_0` — invalid GLSL that
# strict ANGLE/driver combinations reject at compile time:
#
#   ERROR: 'assign' : cannot convert from 'in highp 4-component vector of
#           float' to 'highp 3-component vector of float'
#           (attributes.color_0 = a_color_0;)
#
# The materials are texture/factor driven and the vertex colours are
# visually inert, so the safe, deterministic fix is to drop the COLOR_n
# attribute references entirely (JSON-only — buffers are left untouched,
# orphaned accessors are simply never read).
#
# Usage: python remove_vertex_colors.py <model.gltf> [...]

import json
import sys

for path in sys.argv[1:]:
    g = json.load(open(path, encoding="utf-8-sig"))
    removed = 0
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            for key in [k for k in attrs if k.startswith("COLOR")]:
                del attrs[key]
                removed += 1
            # morph targets can carry COLOR deltas too
            for target in prim.get("targets", []):
                for key in [k for k in target if k.startswith("COLOR")]:
                    del target[key]
                    removed += 1
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{path}: removed {removed} COLOR attribute reference(s)")
