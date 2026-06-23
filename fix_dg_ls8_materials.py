# fix_dg_ls8_materials.py — Assign realistic per-part PBR colours to DG1001
# and LS8 cesium models.  Their Asobo KTX2 textures use proprietary
# supercompression (scheme 65536) that no open-source decoder supports, so
# a plain white texture was substituted.  This script replaces the flat-white
# look with sensible material colours: white gelcoat body, dark tyres, grey
# metal landing gear, etc.  The fuselage material keeps the white livery
# texture (textures/livery_base/<class>_base.png) so the studio's repaint
# panel still works for the body colour.
#
# Usage: py -3.11 fix_dg_ls8_materials.py

import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))

# -----------------------------------------------------------------
# Per-URI-keyword material overrides.
# baseColorFactor is RGBA [0-1]; metallicFactor / roughnessFactor set
# the PBR surface appearance.  If keep_texture is True the existing
# baseColorTexture (white livery) is left in place; otherwise it is
# removed so the factor alone drives the colour.
# -----------------------------------------------------------------
DG1001_PARTS = {
    "fuselage_albd": dict(factor=[1.0, 1.0, 1.0, 1.0],
                          metallic=0.0, rough=0.35, keep_tex=True),
    "wings_albd":    dict(factor=[1.0, 1.0, 1.0, 1.0],
                          metallic=0.0, rough=0.35, keep_tex=True),
    "decals_albd":   dict(factor=[0.95, 0.97, 1.0, 1.0],
                          metallic=0.0, rough=0.4,  keep_tex=False),
    "landinggear_albd": dict(factor=[0.28, 0.29, 0.32, 1.0],
                              metallic=0.6, rough=0.45, keep_tex=False),
    "tires_albd":    dict(factor=[0.07, 0.07, 0.07, 1.0],
                          metallic=0.0, rough=0.85, keep_tex=False),
    "cover_preflight_albd": dict(factor=[0.75, 0.76, 0.78, 1.0],
                                  metallic=0.0, rough=0.55, keep_tex=False),
    "brakedisc_albd": dict(factor=[0.3, 0.3, 0.32, 1.0],
                            metallic=0.8, rough=0.3,  keep_tex=False),
    "propeller_albd": dict(factor=[0.2, 0.2, 0.22, 1.0],
                            metallic=0.7, rough=0.35, keep_tex=False),
    "landinggear_cover": dict(factor=[0.28, 0.29, 0.32, 1.0],
                               metallic=0.5, rough=0.5, keep_tex=False),
}

LS8_PARTS = {
    "fuselage_albd": dict(factor=[1.0, 1.0, 1.0, 1.0],
                           metallic=0.0, rough=0.3,  keep_tex=True),
    "wings_albd":    dict(factor=[1.0, 1.0, 1.0, 1.0],
                           metallic=0.0, rough=0.3,  keep_tex=True),
    "decals1_albd":  dict(factor=[0.95, 0.95, 0.95, 1.0],
                           metallic=0.0, rough=0.45, keep_tex=False),
    "details_albd":  dict(factor=[0.45, 0.46, 0.5, 1.0],
                           metallic=0.5, rough=0.4,  keep_tex=False),
    "wheels_albd":   dict(factor=[0.07, 0.07, 0.07, 1.0],
                           metallic=0.0, rough=0.85, keep_tex=False),
    "tires_albd":    dict(factor=[0.07, 0.07, 0.07, 1.0],
                           metallic=0.0, rough=0.85, keep_tex=False),
    "decals_albd":   dict(factor=[0.9, 0.9, 0.9, 1.0],
                           metallic=0.0, rough=0.45, keep_tex=False),
}


JOBS = [
    # (original lod01.gltf, cesium.gltf to update, parts dict)
    ("assets/Glider models/dg1001/models/dg1001_airframe_lod01.gltf",
     "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
     DG1001_PARTS),

    ("assets/Glider models/ls8_3d/models/ls8_airframe_lod01.gltf",
     "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
     LS8_PARTS),

    ("assets/Glider models/ls8_3d/models/ls8_wing_l_lod01.gltf",
     "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
     LS8_PARTS),

    ("assets/Glider models/ls8_3d/models/ls8_wing_r_lod01.gltf",
     "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
     LS8_PARTS),
]


def get_tex_source(textures, ti):
    """Return image index for texture ti, handling MSFT_texture_dds."""
    if ti >= len(textures):
        return None
    t = textures[ti]
    ext = t.get("extensions", {})
    for k in ("MSFT_texture_dds", "KHR_texture_basisu"):
        if k in ext:
            return ext[k].get("source")
    return t.get("source")


def process(orig_rel, cev_rel, parts_map):
    orig_path = os.path.join(ROOT, orig_rel.replace("/", os.sep))
    cev_path  = os.path.join(ROOT, cev_rel.replace("/", os.sep))
    print(f"\n{'='*55}")
    print(f"Model: {os.path.basename(cev_path)}")

    orig = json.load(open(orig_path, encoding="utf-8-sig"))
    cev  = json.load(open(cev_path,  encoding="utf-8-sig"))

    orig_imgs  = orig.get("images", [])
    orig_texs  = orig.get("textures", [])
    orig_mats  = orig.get("materials", [])
    cev_mats   = cev.get("materials", [])

    updated = 0
    for mi, orig_mat in enumerate(orig_mats):
        if mi >= len(cev_mats):
            continue
        pbr_orig = orig_mat.get("pbrMetallicRoughness", {})
        bct = pbr_orig.get("baseColorTexture")
        if not bct:
            continue
        img_idx = get_tex_source(orig_texs, bct.get("index", -1))
        if img_idx is None or img_idx >= len(orig_imgs):
            continue
        uri = orig_imgs[img_idx].get("uri", "").lower()

        # Find the best matching part rule
        match = None
        for key, rule in parts_map.items():
            if key in uri:
                match = rule
                break
        if not match:
            continue

        pbr_cev = cev_mats[mi].setdefault("pbrMetallicRoughness", {})
        pbr_cev["baseColorFactor"]  = match["factor"]
        pbr_cev["metallicFactor"]   = match["metallic"]
        pbr_cev["roughnessFactor"]  = match["rough"]
        if not match["keep_tex"]:
            pbr_cev.pop("baseColorTexture", None)

        print(f"  mat[{mi:2d}] {os.path.basename(uri.rstrip('.ktx2'))}: "
              f"factor={match['factor'][:3]}  "
              f"M={match['metallic']} R={match['rough']}"
              + (" [livery tex kept]" if match["keep_tex"] else ""))
        updated += 1

    # Materials that got no update: make them non-metallic grey gelcoat
    for mi, cev_mat in enumerate(cev_mats):
        if mi < len(orig_mats):
            # Check if it had any baseColorTexture at all in the original
            pbr_orig = orig_mats[mi].get("pbrMetallicRoughness", {})
            if not pbr_orig.get("baseColorTexture"):
                # Glass, special surfaces — leave as-is but make less metallic
                pbr_cev = cev_mat.setdefault("pbrMetallicRoughness", {})
                pbr_cev.setdefault("metallicFactor", 0.0)
                pbr_cev.setdefault("roughnessFactor", 0.5)

    json.dump(cev, open(cev_path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  -> {updated} materials updated in {os.path.basename(cev_path)}")


for orig_rel, cev_rel, parts in JOBS:
    process(orig_rel, cev_rel, parts)

print("\nDone. Bump MODEL_CACHE_V in tracker.html to ?v=6.")
