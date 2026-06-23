# fix_ktx2_models.py — Convert Asobo KTX2 albedo textures for DG1001 and LS8,
# then rebuild their cesium.gltf texture bindings.
#
# These models shipped with Asobo-proprietary BC1/BC3/BC7 inside KTX2 —
# Cesium only accepts Basis Universal KTX2, so they rejected with
# "Invalid KTX2 file". Previously they were stripped to a white blank.
# This script converts the albedo files to PNG and wires up the materials.
#
# Usage: py -3.11 fix_ktx2_models.py
#
# After running, bump MODEL_CACHE_V in tracker.html to ?v=6.

import json, os, struct, shutil
import numpy as np
import texture2ddecoder, zstandard
from PIL import Image

ROOT      = os.path.dirname(os.path.abspath(__file__))
LIVERY_DIR = os.path.join(ROOT, "textures", "livery_base")
os.makedirs(LIVERY_DIR, exist_ok=True)

DEFAULT_SAMPLER = {"magFilter": 9729, "minFilter": 9987,
                   "wrapS": 10497, "wrapT": 10497}

VK_DECODERS = {
    131: ("BC1", texture2ddecoder.decode_bc1),
    133: ("BC1", texture2ddecoder.decode_bc1),
    137: ("BC3", texture2ddecoder.decode_bc3),
    139: ("BC4", texture2ddecoder.decode_bc4),
    141: ("BC5", texture2ddecoder.decode_bc5),
    145: ("BC7", texture2ddecoder.decode_bc7),
    146: ("BC7", texture2ddecoder.decode_bc7),
}

# Image name substrings that mark non-albedo textures to skip
SKIP_PATTERNS = (
    "_norm", "_comp", "_mask", "_smudge", "insects", "dust", "frost", "mud",
    "microscratches", "leaks", "metal_brakedisc_aniso", "regular_albd",
    "runway_albd", "cockpit_detail", "glass_detail", "prop_blur", "side_blur",
    ".tif.ktx2",   # TIF-wrapped KTX2 usually atmospheric effects; skip for speed
)

JOBS = [
    {
        "original": "assets/Glider models/dg1001/models/dg1001_airframe_lod01.gltf",
        "cesium":   "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
        "livery_key":  "fuselage_albd",
        "livery_file": "dg1001_20m_base.png",
        "livery_depth": 4,
    },
    {
        "original": "assets/Glider models/ls8_3d/models/ls8_airframe_lod01.gltf",
        "cesium":   "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
        "livery_key":  "fuselage_albd",
        "livery_file": "ls8_standard_base.png",
        "livery_depth": 4,
    },
    {
        "original": "assets/Glider models/ls8_3d/models/ls8_wing_l_lod01.gltf",
        "cesium":   "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
        "livery_key":  None,   # wings share the airframe livery; no separate route
        "livery_file": None,
        "livery_depth": None,
    },
    {
        "original": "assets/Glider models/ls8_3d/models/ls8_wing_r_lod01.gltf",
        "cesium":   "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
        "livery_key":  None,
        "livery_file": None,
        "livery_depth": None,
    },
]


def convert_ktx2(path):
    """Decode a KTX2 file to RGBA PNG next to the source. Returns PNG path."""
    out = path[:-5] if path.lower().endswith(".ktx2") else path + ".png"
    if os.path.isfile(out):
        print(f"    skip (cached): {os.path.basename(out)}")
        return out
    data = open(path, "rb").read()
    if data[:7] != b"\xabKTX 20":
        raise ValueError("not KTX2")
    vk, _ts, w, h, _d, _lay, _fac, _lvls, scheme = struct.unpack_from("<9I", data, 12)
    off, ln, _ = struct.unpack_from("<3Q", data, 80)
    blob = data[off:off + ln]
    if scheme == 2:
        blob = zstandard.ZstdDecompressor().decompress(blob, max_output_size=w * h * 8)
    elif scheme != 0:
        raise ValueError(f"unsupported supercompression {scheme}")
    if vk not in VK_DECODERS:
        raise ValueError(f"unsupported vkFormat {vk}")
    fmt, decode = VK_DECODERS[vk]
    bgra = np.frombuffer(decode(blob, w, h), dtype=np.uint8).reshape(h, w, 4)
    rgba = bgra[:, :, [2, 1, 0, 3]].copy()
    Image.fromarray(rgba, "RGBA").save(out)
    print(f"    converted: {os.path.basename(out)} ({fmt} {w}x{h})")
    return out


def is_albedo(uri):
    low = uri.lower()
    return (low.endswith(".ktx2")
            and not any(p in low for p in SKIP_PATTERNS))


def process(job):
    orig_path = os.path.join(ROOT, job["original"].replace("/", os.sep))
    cev_path  = os.path.join(ROOT, job["cesium"].replace("/", os.sep))
    orig_dir  = os.path.dirname(orig_path)
    cev_dir   = os.path.dirname(cev_path)

    print(f"\n{'='*60}")
    print(f"Model: {os.path.basename(cev_path)}")

    orig = json.load(open(orig_path, encoding="utf-8-sig"))
    cev  = json.load(open(cev_path,  encoding="utf-8-sig"))

    orig_imgs = orig.get("images", [])
    orig_texs = orig.get("textures", [])
    orig_mats = orig.get("materials", [])

    # texture index → image index via MSFT_texture_dds (or direct source)
    def tex_img_idx(ti):
        t = orig_texs[ti] if ti < len(orig_texs) else {}
        ext = t.get("extensions", {})
        src = (ext.get("MSFT_texture_dds") or ext.get("KHR_texture_basisu") or {}).get("source")
        return src if src is not None else t.get("source")

    # For each material: find the baseColorTexture image URI
    mat_to_ktx2_uri = {}   # material index → KTX2 relative URI (from orig_dir)
    for mi, mat in enumerate(orig_mats):
        pbr = mat.get("pbrMetallicRoughness", {})
        bct = pbr.get("baseColorTexture")
        if not bct:
            continue
        ii = tex_img_idx(bct["index"])
        if ii is None or ii >= len(orig_imgs):
            continue
        uri = orig_imgs[ii].get("uri", "")
        if is_albedo(uri):
            mat_to_ktx2_uri[mi] = uri

    print(f"  Materials with albedo KTX2: {len(mat_to_ktx2_uri)}")
    for mi, uri in mat_to_ktx2_uri.items():
        print(f"    mat[{mi}] <- {os.path.basename(uri)}")

    # Convert every unique KTX2 → PNG
    uri_to_png_abs = {}   # relative KTX2 URI → absolute PNG path
    for uri in set(mat_to_ktx2_uri.values()):
        abs_ktx2 = os.path.normpath(os.path.join(orig_dir, uri.replace("%20", " ")))
        if not os.path.isfile(abs_ktx2):
            print(f"  MISSING: {abs_ktx2}")
            continue
        try:
            png_abs = convert_ktx2(abs_ktx2)
            uri_to_png_abs[uri] = png_abs
        except Exception as e:
            print(f"  FAILED {os.path.basename(uri)}: {e}")

    if not uri_to_png_abs:
        print("  No textures converted — skipping gltf update")
        return

    # Build new images list (deduplicated)
    png_abs_to_idx = {}
    new_images = []
    for uri, png_abs in uri_to_png_abs.items():
        if png_abs not in png_abs_to_idx:
            rel = os.path.relpath(png_abs, cev_dir).replace("\\", "/")
            png_abs_to_idx[png_abs] = len(new_images)
            new_images.append({"uri": rel})

    # Route the fuselage livery through textures/livery_base/
    if job.get("livery_key") and job.get("livery_file"):
        depth = job["livery_depth"]
        lf = job["livery_file"]
        for img in new_images:
            if job["livery_key"] in img["uri"].lower():
                src_abs = os.path.normpath(os.path.join(cev_dir, img["uri"]))
                dst_abs = os.path.join(LIVERY_DIR, lf)
                if os.path.isfile(src_abs):
                    shutil.copyfile(src_abs, dst_abs)
                    print(f"  Livery routed → textures/livery_base/{lf}")
                img["uri"] = "../" * depth + "textures/livery_base/" + lf
                break

    # Build textures array: one entry per image
    new_textures = [{"source": i, "sampler": 0} for i in range(len(new_images))]

    # Ensure sampler exists in cesium.gltf
    if not cev.get("samplers"):
        cev["samplers"] = [dict(DEFAULT_SAMPLER)]

    # Build material → new texture index map
    mat_to_new_tex = {}
    for mi, uri in mat_to_ktx2_uri.items():
        if uri not in uri_to_png_abs:
            continue
        png_abs = uri_to_png_abs[uri]
        new_idx = png_abs_to_idx[png_abs]
        mat_to_new_tex[mi] = new_idx   # texture[new_idx].source == image[new_idx]

    # Update materials in cesium.gltf
    cev_mats = cev.get("materials", [])
    updated = 0
    for mi, tex_idx in mat_to_new_tex.items():
        if mi >= len(cev_mats):
            continue
        pbr = cev_mats[mi].setdefault("pbrMetallicRoughness", {})
        pbr["baseColorTexture"] = {"index": tex_idx}
        pbr.setdefault("metallicFactor", 0.0)
        pbr.setdefault("roughnessFactor", 0.6)
        updated += 1

    # Materials without albedo: clear baseColorTexture so they use baseColorFactor
    for mi, mat in enumerate(cev_mats):
        if mi not in mat_to_new_tex:
            pbr = mat.get("pbrMetallicRoughness", {})
            pbr.pop("baseColorTexture", None)

    cev["images"]   = new_images
    cev["textures"] = new_textures

    json.dump(cev, open(cev_path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"  Saved {os.path.basename(cev_path)}: "
          f"{len(new_images)} images, {updated}/{len(cev_mats)} materials textured")


for job in JOBS:
    process(job)

print("\n\nAll done.")
print("Bump MODEL_CACHE_V in tracker.html from '?v=5' to '?v=6'.")
