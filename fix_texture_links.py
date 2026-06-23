# fix_texture_links.py — restore the texture→image bindings the MSFS/Babylon
# exporter never wrote, and route each model's main livery through
# textures/livery_base/.
#
# DISCOVERY (2026-06-12): every glider glTF shipped with an empty `textures`
# array — `[{}, {}, …]`, no `source`, no `sampler` — so no material could
# ever reach its image and Cesium has rendered these models UNTEXTURED from
# day one (the "livery" people saw was vertex colours, which had to be
# removed because they were spec-invalid and crashed shaders — see
# remove_vertex_colors.py). Cross-referencing material slots with image
# names (AS33_EXT_BODY: normal→0=*_NORM, occlusion→1=*_COMP, baseColor→2=
# *_ALBD) proves the exporter's convention: texture index == image index.
#
# What this script does, per glTF:
#   1. samplers: ensure a default trilinear/repeat sampler exists
#   2. textures[i].source = i for every i < len(images)
#   3. materials: keep ONLY baseColorTexture (drop normal/occlusion/
#      metallicRoughness/emissive texture refs — factors take over). This
#      keeps Cesium's generated shader surface small on a renderer that has
#      already burned us with exotic GLSL paths.
#      A baseColorTexture whose mapped image is clearly not an albedo
#      (name ends NORM/COMP) is dropped rather than linked to garbage.
#   4. the designated LIVERY image is copied to textures/livery_base/<file>
#      and the glTF image uri is rewritten to point THERE — the same file
#      the studio panel offers for download. Repaint the file, reload, and
#      every glider of that class wears the new paint.
#
# Usage: python fix_texture_links.py        (paths are baked in below)

import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVERY_DIR = os.path.join(ROOT, "textures", "livery_base")

# gltf path, livery image matcher (name or uri substring, lowercase),
# livery filename in textures/livery_base/, ../ depth from the gltf to root
JOBS = [
    (r"assets/Glider models/js3_full/models/js3_cesium.gltf",
     "jonker", "js3_15m_base.jpg", 4),
    (r"assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
     "as33_ext_body_albd", "as33_open_base.png", 4),
    (r"assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
     "discus2c_ext_albd", "d2c_18m_base.png", 4),
    (r"assets/Glider models/ls4 clean/exterior.gltf",
     "ls4a_g-demg", "ls4_club_base.png", 3),
]

DEFAULT_SAMPLER = {"magFilter": 9729, "minFilter": 9987,
                   "wrapS": 10497, "wrapT": 10497}

os.makedirs(LIVERY_DIR, exist_ok=True)

for rel, livery_key, livery_file, depth in JOBS:
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    g = json.load(open(path, encoding="utf-8-sig"))
    imgs = g.get("images", [])
    texs = g.get("textures", [])

    if not g.get("samplers"):
        g["samplers"] = [dict(DEFAULT_SAMPLER)]

    # 2. identity-link every texture that has a matching image
    linked = 0
    for i, t in enumerate(texs):
        if i < len(imgs):
            t["source"] = i
            t.setdefault("sampler", 0)
            linked += 1

    # 3. slim the materials down to albedo-only texturing
    kept = dropped = 0
    for m in g.get("materials", []):
        m.pop("normalTexture", None)
        m.pop("occlusionTexture", None)
        m.pop("emissiveTexture", None)
        pbr = m.get("pbrMetallicRoughness", {})
        pbr.pop("metallicRoughnessTexture", None)
        bct = pbr.get("baseColorTexture")
        if bct is not None:
            i = bct.get("index", -1)
            name = ""
            if 0 <= i < len(texs) and "source" in texs[i]:
                img = imgs[texs[i]["source"]]
                name = (img.get("name") or img.get("uri") or "").lower()
            if not name or name.endswith("norm") or name.endswith("comp"):
                pbr.pop("baseColorTexture", None)   # unlinked or non-albedo
                dropped += 1
            else:
                kept += 1

    # 4. route the livery image through textures/livery_base/
    gltf_dir = os.path.dirname(path)
    routed = False
    for img in imgs:
        hay = ((img.get("name") or "") + " " + (img.get("uri") or "")).lower()
        if livery_key in hay:
            src = os.path.normpath(os.path.join(
                gltf_dir, (img.get("uri") or "").replace("%20", " ")))
            dst = os.path.join(LIVERY_DIR, livery_file)
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copyfile(src, dst)
            img["uri"] = "../" * depth + "textures/livery_base/" + livery_file
            routed = True
            break

    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{rel}: linked {linked}/{len(texs)} textures, "
          f"albedo kept {kept} / dropped {dropped}, livery routed: {routed}")
