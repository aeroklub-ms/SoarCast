# fix_gltf_for_cesium.py — JSON-level repair of MSFS/Babylon glTF exports so
# CesiumJS 1.142 can load them. The binary buffers and textures are left
# untouched; only the glTF JSON is rewritten:
#
#   1. animations / skins / node.skin removed (tracker renders static
#      airframes; the broken skin structures crash loaders)
#   2. JOINTS_* / WEIGHTS_* vertex attributes dropped (dead without skins,
#      and some are spec-violating SCALARs)
#   3. spec-violating VEC4 NORMAL accessors re-declared as VEC3 via a new
#      16-byte-strided bufferView over the same data (4th float skipped)
#   4. meshes with no primitives unlinked from nodes
#   5. string-valued "extras" and ASOBO_* extension blocks removed
#      (Cesium's preprocessor crashes on them)
#   6. MSFT_texture_dds texture indirection rewritten to KHR_texture_basisu
#      (the referenced images are KTX2, which Cesium supports natively)
#
# Usage: python fix_gltf_for_cesium.py <in.gltf> <out.gltf> [--steps=a,b,…]
#   steps: anim (strip animations/skins/joints/weights), normals (VEC4→VEC3),
#          empty (unlink empty meshes), sanitize (extras/ASOBO), dds (→basisu)
#   default: all steps

import json
import sys

src, dst = sys.argv[1], sys.argv[2]
ALL_STEPS = {"anim", "normals", "empty", "sanitize", "dds"}
steps = ALL_STEPS
for a in sys.argv[3:]:
    if a.startswith("--steps="):
        steps = set(a.split("=", 1)[1].split(","))
g = json.load(open(src, encoding="utf-8-sig"))
stats = {}


def bump(k, n=1):
    stats[k] = stats.get(k, 0) + n


# ── 1. static airframe: no animations, no skins ──────────────────────────
if "anim" in steps:
    for key in ("animations", "skins"):
        if key in g:
            bump(f"removed {key}", len(g[key]))
            del g[key]
    for n in g.get("nodes", []):
        n.pop("skin", None)

# ── 2./3. per-primitive attribute repair ──────────────────────────────────
acc = g.get("accessors", [])
views = g.get("bufferViews", [])
vec3_normal_cache = {}  # old accessor idx -> fixed accessor idx

def fix_vec4_normal(ai):
    if ai in vec3_normal_cache:
        return vec3_normal_cache[ai]
    a = acc[ai]
    old_view = views[a["bufferView"]]
    stride = old_view.get("byteStride", 16)  # VEC4 float = 16 bytes packed
    new_view = {
        "buffer":     old_view["buffer"],
        "byteOffset": old_view.get("byteOffset", 0) + a.get("byteOffset", 0),
        # last element only needs 12 bytes (VEC3 float), not a full stride —
        # count*stride can overrun the buffer on interleaved views
        "byteLength": (a["count"] - 1) * stride + 12,
        "byteStride": stride,
    }
    if "target" in old_view:
        new_view["target"] = old_view["target"]
    views.append(new_view)
    new_acc = {
        "bufferView":    len(views) - 1,
        "byteOffset":    0,
        "componentType": a["componentType"],
        "count":         a["count"],
        "type":          "VEC3",
    }
    acc.append(new_acc)
    vec3_normal_cache[ai] = len(acc) - 1
    bump("VEC4 NORMAL fixed")
    return vec3_normal_cache[ai]


for mesh in g.get("meshes", []):
    for prim in mesh.get("primitives", []):
        attrs = prim.get("attributes", {})
        for sem in list(attrs.keys()):
            if sem.startswith(("JOINTS_", "WEIGHTS_")) and "anim" in steps:
                del attrs[sem]
                bump("skin attrs dropped")
            elif sem == "NORMAL" and acc[attrs[sem]]["type"] == "VEC4" and "normals" in steps:
                attrs[sem] = fix_vec4_normal(attrs[sem])

# ── 4. unlink empty meshes ────────────────────────────────────────────────
if "empty" in steps:
    empty = {i for i, m in enumerate(g.get("meshes", [])) if not m.get("primitives")}
    for n in g.get("nodes", []):
        if n.get("mesh") in empty:
            del n["mesh"]
            bump("empty mesh unlinked")

# ── 5. extras / ASOBO cleanup (recursive) ─────────────────────────────────
def sanitize(node):
    if isinstance(node, list):
        for item in node:
            sanitize(item)
        return
    if not isinstance(node, dict):
        return
    if "extras" in node and not isinstance(node["extras"], dict):
        del node["extras"]
        bump("string extras removed")
    ext = node.get("extensions")
    if isinstance(ext, dict):
        for k in [k for k in ext if k.startswith("ASOBO")]:
            del ext[k]
            bump("ASOBO ext removed")
        if not ext:
            del node["extensions"]
    for v in list(node.values()):
        sanitize(v)


if "sanitize" in steps:
    sanitize(g)

# ── 6. MSFT_texture_dds → KHR_texture_basisu ─────────────────────────────
uses_basisu = False
for tex in (g.get("textures", []) if "dds" in steps else []):
    ext = tex.get("extensions", {})
    dds = ext.pop("MSFT_texture_dds", None)
    if dds is not None:
        uri = g["images"][dds["source"]].get("uri", "")
        if uri.endswith(".ktx2"):
            ext["KHR_texture_basisu"] = {"source": dds["source"]}
            uses_basisu = True
            bump("texture → basisu")
        elif "source" not in tex:
            tex["source"] = dds["source"]
            bump("texture → plain source")
    if not ext:
        tex.pop("extensions", None)

# ── extension lists ───────────────────────────────────────────────────────
for key in ("extensionsUsed", "extensionsRequired"):
    if key in g:
        g[key] = [e for e in g[key]
                  if not e.startswith("ASOBO") and e != "MSFT_texture_dds"]
        if uses_basisu and key == "extensionsUsed" and "KHR_texture_basisu" not in g[key]:
            g[key].append("KHR_texture_basisu")
        if not g[key]:
            del g[key]

json.dump(g, open(dst, "w", encoding="utf-8"), separators=(",", ":"))
print(json.dumps(stats, indent=1))
print("wrote", dst)
