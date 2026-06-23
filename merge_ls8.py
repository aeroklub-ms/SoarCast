# merge_ls8.py — combine the LS8's 3 separate glTFs (airframe + left wing +
# right wing) into ONE glTF so it loads as a single model like every other
# glider.
#
# The 3 files were authored to load into a SHARED scene in MSFS/Blender — each
# part's nodes carry transforms in the same aircraft-body frame (wing rudders
# symmetric at X=+-5.7, tail at Z~-4).  Loading them as 3 independent Cesium
# entities at the same position+orientation fails to reassemble them (they
# render detached / distorted).  Merging them into one scene graph guarantees
# they assemble exactly as authored.
#
# Standard glTF merge: append every array, offsetting all internal index
# references by the base array's pre-append length.  Buffers stay separate
# (glTF supports multiple buffers) so the existing .bin files are reused
# untouched — only the JSON is rewritten.
#
# Usage: py -3.11 merge_ls8.py
# After running: point GLIDER_MODELS.ls8 at the single combined file + bump
# MODEL_CACHE_V.

import json, os, copy

ROOT = os.path.dirname(os.path.abspath(__file__))
DIR  = os.path.join(ROOT, "assets", "Glider models", "ls8_3d", "models")

BASE  = "ls8_airframe_cesium.gltf"
PARTS = ["ls8_wing_l_cesium.gltf", "ls8_wing_r_cesium.gltf"]
OUT   = "ls8_combined_cesium.gltf"


def load(name):
    return json.load(open(os.path.join(DIR, name), encoding="utf-8-sig"))


def merge_into(base, part):
    # Record base lengths BEFORE appending (these are the offsets).
    o_buffers     = len(base.get("buffers", []))
    o_bufferViews = len(base.get("bufferViews", []))
    o_accessors   = len(base.get("accessors", []))
    o_images      = len(base.get("images", []))
    o_samplers    = len(base.get("samplers", []))
    o_textures    = len(base.get("textures", []))
    o_materials   = len(base.get("materials", []))
    o_meshes      = len(base.get("meshes", []))
    o_nodes       = len(base.get("nodes", []))

    base.setdefault("buffers", [])
    base.setdefault("bufferViews", [])
    base.setdefault("accessors", [])
    base.setdefault("images", [])
    base.setdefault("samplers", [])
    base.setdefault("textures", [])
    base.setdefault("materials", [])
    base.setdefault("meshes", [])
    base.setdefault("nodes", [])

    # buffers — copied as-is; their `uri` points at the part's own .bin
    for buf in part.get("buffers", []):
        base["buffers"].append(copy.deepcopy(buf))

    # bufferViews — buffer index offset
    for bv in part.get("bufferViews", []):
        bv = copy.deepcopy(bv)
        bv["buffer"] = bv.get("buffer", 0) + o_buffers
        base["bufferViews"].append(bv)

    # accessors — bufferView index offset
    for a in part.get("accessors", []):
        a = copy.deepcopy(a)
        if "bufferView" in a:
            a["bufferView"] += o_bufferViews
        # sparse accessors would need more work; the LS8 has none
        base["accessors"].append(a)

    # images — copied as-is (uri relative to the gltf dir; same dir, OK)
    for im in part.get("images", []):
        base["images"].append(copy.deepcopy(im))

    # samplers — copied as-is
    for s in part.get("samplers", []):
        base["samplers"].append(copy.deepcopy(s))

    # textures — source (image) + sampler index offsets
    for t in part.get("textures", []):
        t = copy.deepcopy(t)
        if "source" in t:  t["source"]  += o_images
        if "sampler" in t: t["sampler"] += o_samplers
        base["textures"].append(t)

    # materials — every texture reference offset
    def fix_tex_ref(d):
        if isinstance(d, dict) and "index" in d:
            d["index"] += o_textures
    for m in part.get("materials", []):
        m = copy.deepcopy(m)
        pbr = m.get("pbrMetallicRoughness", {})
        fix_tex_ref(pbr.get("baseColorTexture"))
        fix_tex_ref(pbr.get("metallicRoughnessTexture"))
        fix_tex_ref(m.get("normalTexture"))
        fix_tex_ref(m.get("occlusionTexture"))
        fix_tex_ref(m.get("emissiveTexture"))
        base["materials"].append(m)

    # meshes — accessor (attributes + indices) + material index offsets
    for mesh in part.get("meshes", []):
        mesh = copy.deepcopy(mesh)
        for prim in mesh.get("primitives", []):
            attrs = prim.get("attributes", {})
            for k in list(attrs.keys()):
                attrs[k] += o_accessors
            if "indices" in prim:
                prim["indices"] += o_accessors
            if "material" in prim:
                prim["material"] += o_materials
        base["meshes"].append(mesh)

    # nodes — mesh + children index offsets (skins already stripped)
    new_root_nodes = []
    for n in part.get("nodes", []):
        n = copy.deepcopy(n)
        if "mesh" in n:
            n["mesh"] += o_meshes
        if "children" in n:
            n["children"] = [c + o_nodes for c in n["children"]]
        n.pop("skin", None)
        base["nodes"].append(n)

    # scene roots — append the part's root nodes (offset) to the base scene
    part_scene = part.get("scenes", [{}])[part.get("scene", 0)]
    base_scene = base.setdefault("scenes", [{"nodes": []}])[base.get("scene", 0)]
    base_scene.setdefault("nodes", [])
    for ri in part_scene.get("nodes", []):
        base_scene["nodes"].append(ri + o_nodes)

    # merge extensionsUsed/Required
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in part:
            merged = set(base.get(key, [])) | set(part[key])
            base[key] = sorted(merged)


base = load(BASE)
for pname in PARTS:
    merge_into(base, load(pname))

out_path = os.path.join(DIR, OUT)
json.dump(base, open(out_path, "w", encoding="utf-8"), separators=(",", ":"))
print(f"Merged -> {OUT}")
print(f"  buffers={len(base['buffers'])} nodes={len(base['nodes'])} "
      f"meshes={len(base['meshes'])} materials={len(base['materials'])} "
      f"accessors={len(base['accessors'])}")
print("Now point GLIDER_MODELS.ls8 at the single file + bump MODEL_CACHE_V.")
