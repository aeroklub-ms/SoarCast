# fix_interior_textures.py — wire up texture bindings for the D2C and AS33
# interior gltfs the same way fix_texture_links.py did for the exteriors.
# The MSFS/Babylon export drops `textures[i].source` (every texture entry
# is `{}`); without a source pointer, every material's baseColorTexture
# references nothing and the cockpit renders untextured.
#
# Convention (same as exterior fix):
#   - texture index == image index (identity binding)
#   - default trilinear / repeat sampler
#   - only ALBEDO textures kept on materials — drop NORMAL/OCC/COMP/MET-ROUGH
#     for a lighter shader load (interior visibility is brief in cockpit cam)
#
# Usage: py -3.11 fix_interior_textures.py

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SAMPLER = {
    "magFilter": 9729, "minFilter": 9987,
    "wrapS": 10497, "wrapT": 10497
}

JOBS = [
    "assets/Glider models/d2c/models/d2c_interior_lod0_cesium.gltf",
    "assets/Glider models/as33/models/as33_me_18m_interior_lod0_cesium.gltf",
]

for rel in JOBS:
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    g = json.load(open(path, encoding="utf-8-sig"))
    imgs = g.get("images", [])
    texs = g.get("textures", [])
    mats = g.get("materials", [])

    if not g.get("samplers"):
        g["samplers"] = [dict(DEFAULT_SAMPLER)]

    # Build a lookup: lower-case stem → image index, but ONLY for albedo
    # variants (uri ending `_albd.png` or `.png` without obvious channel hint).
    name_to_img = {}
    for i, im in enumerate(imgs):
        uri = (im.get("uri") or "").lower()
        stem = uri.rsplit("/", 1)[-1].rsplit(".", 1)[0]   # filename without ext
        if not stem: continue
        # Prefer _albd variants; strip the suffix so the material name matches
        if stem.endswith("_albd"):
            key = stem[:-5]   # drop "_albd"
            name_to_img[key] = i
        elif not any(stem.endswith(s) for s in ("_norm", "_comp", "_smudge",
                                                  "_rough", "_ao", "_metallic")):
            # Plain texture (no channel suffix) — accept as albedo fallback
            name_to_img.setdefault(stem, i)

    # Identity-bind every texture so EVERY material referencing tex[i] resolves
    # to something — we'll later override baseColorTexture per-material via the
    # name lookup.  This also keeps shaders compileable.
    linked = 0
    for i, t in enumerate(texs):
        if "source" not in t and i < len(imgs):
            t["source"] = i
            t.setdefault("sampler", 0)
            linked += 1
        elif "source" in t:
            t.setdefault("sampler", 0)

    # Per-material albedo lookup: try material name → image stem match.
    # If the material is named DISCUS2C_INT_DETAILS, look for
    # discus2c_int_details (auto-stripped _albd suffix from images).
    matched = name_only = pbr_only = 0
    for m in mats:
        m.pop("normalTexture",   None)
        m.pop("occlusionTexture",None)
        m.pop("emissiveTexture", None)
        pbr = m.setdefault("pbrMetallicRoughness", {})
        pbr.pop("metallicRoughnessTexture", None)
        mat_name = (m.get("name") or "").lower()
        # Try name-based albedo binding.  If a matching `<name>_albd.png`
        # image exists, point baseColorTexture at the corresponding texture
        # entry (texture i has source i after the identity-bind above).
        if mat_name and mat_name in name_to_img:
            img_idx = name_to_img[mat_name]
            # find/create a texture entry pointing at this image
            tex_idx = None
            for j, t in enumerate(texs):
                if t.get("source") == img_idx:
                    tex_idx = j; break
            if tex_idx is None:
                texs.append({"source": img_idx, "sampler": 0})
                tex_idx = len(texs) - 1
            pbr["baseColorTexture"] = {"index": tex_idx}
            matched += 1
        else:
            # No name match — strip whatever bogus baseColorTexture was there
            # so the material falls back to baseColorFactor + factor defaults.
            pbr.pop("baseColorTexture", None)
            name_only += 1

        # Sensible PBR defaults — interior materials are matte plastic
        pbr.setdefault("metallicFactor", 0.0)
        pbr.setdefault("roughnessFactor", 0.7)
        if "baseColorFactor" not in pbr:
            pbr["baseColorFactor"] = [0.78, 0.78, 0.78, 1.0]

    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{os.path.basename(path)}: linked {linked}/{len(texs)}, "
          f"name-matched albedo {matched}/{len(mats)} materials")

print("Done.")
