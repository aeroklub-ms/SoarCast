# fix_vec4_normals.py — relabel spec-invalid VEC4 NORMAL accessors to VEC3.
#
# SECOND HALF of the "vec4→vec3 dimension mismatch" root cause (the first
# half was invalid COLOR_0 accessors — see remove_vertex_colors.py): the
# MSFS/Babylon exporters pack vertex normals as VEC4 of signed BYTE, the
# 4th component being alignment padding. The glTF spec requires NORMAL to
# be VEC3. Fed a VEC4 normal, CesiumJS declares `in vec4 a_normalMC` and
# `out vec4 v_normalEC` but writes them into vec3 struct fields:
#
#   vertex:   attributes.normalMC = a_normalMC;            (vec4 → vec3)
#   fragment: attributes.normalEC = normalize(v_normalEC); (vec4 → vec3)
#
# — invalid GLSL that strict ANGLE/driver combinations reject. Affected
# models: as33, d2c (the DEFAULT fallback model!), ls4. js3/ls8/dg1001
# already carry VEC3 normals and never failed.
#
# The fix is metadata-only: set the accessor type to VEC3 and make sure the
# bufferView's byteStride still steps over the full 4-byte element, so the
# padding byte is skipped instead of misaligning every following vertex.
#
# Usage: python fix_vec4_normals.py <model.gltf> [...]

import json
import sys

COMP_SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_LEN  = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def element_size(acc):
    return COMP_SIZE[acc["componentType"]] * TYPE_LEN[acc["type"]]


for path in sys.argv[1:]:
    g = json.load(open(path, encoding="utf-8-sig"))
    accessors   = g.get("accessors", [])
    buffer_views = g.get("bufferViews", [])

    # which accessor indices are used as NORMAL (incl. morph targets)?
    normal_idx = set()
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            a = prim.get("attributes", {})
            if "NORMAL" in a:
                normal_idx.add(a["NORMAL"])
            for target in prim.get("targets", []):
                if "NORMAL" in target:
                    normal_idx.add(target["NORMAL"])

    fixed = skipped = 0
    for i in sorted(normal_idx):
        acc = accessors[i]
        if acc.get("type") != "VEC4":
            continue
        old_size = element_size(acc)                       # 4-byte VEC4 step
        bv = buffer_views[acc["bufferView"]] if "bufferView" in acc else None
        if bv is not None and "byteStride" not in bv:
            # stride must keep stepping old_size or every vertex after the
            # first reads the padding byte — only safe if no other accessor
            # with a different element size shares this view
            sharers = [a for a in accessors
                       if a.get("bufferView") == acc["bufferView"] and a is not acc]
            if any(element_size(a) != old_size for a in sharers):
                print(f"  SKIP accessor {i}: shared bufferView, mixed element sizes")
                skipped += 1
                continue
            bv["byteStride"] = old_size
        acc["type"] = "VEC3"
        for key in ("min", "max"):
            if key in acc and len(acc[key]) == 4:
                acc[key] = acc[key][:3]
        fixed += 1

    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{path}: {fixed} VEC4 NORMAL accessor(s) -> VEC3"
          + (f", {skipped} skipped" if skipped else ""))
