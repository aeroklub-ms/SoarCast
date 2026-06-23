# convert_ktx2_textures.py — MSFS ships textures as KTX2 containers holding
# raw BC1/BC3/BC4/BC5/BC7 GPU blocks (optionally zstd-supercompressed).
# CesiumJS only accepts Basis Universal inside KTX2, so it rejects these with
# "Invalid KTX2 file". This script decodes level 0 to plain PNG next to the
# source and rewrites the given glTFs to reference the PNGs directly
# (KHR_texture_basisu indirection removed).
#
# Usage: py -3.11 convert_ktx2_textures.py <model1.gltf> [<model2.gltf> ...]

import json
import os
import struct
import sys

import numpy as np
import texture2ddecoder
import zstandard
from PIL import Image

VK_DECODERS = {
    131: ("BC1",  texture2ddecoder.decode_bc1),   # BC1_RGB_UNORM
    133: ("BC1",  texture2ddecoder.decode_bc1),   # BC1_RGBA_UNORM
    137: ("BC3",  texture2ddecoder.decode_bc3),   # BC3_UNORM
    139: ("BC4",  texture2ddecoder.decode_bc4),   # BC4_UNORM
    141: ("BC5",  texture2ddecoder.decode_bc5),   # BC5_UNORM
    145: ("BC7",  texture2ddecoder.decode_bc7),   # BC7_UNORM
    146: ("BC7",  texture2ddecoder.decode_bc7),   # BC7_SRGB
}


def convert_ktx2(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:7] != b"\xabKTX 20":
        raise ValueError("not KTX2")
    (vk_format, _ts, w, h, _d, _layers, _faces, levels, scheme) = struct.unpack_from("<9I", data, 12)
    # level index starts right after header(80) + index is at offset 80
    lvl_off, lvl_len, _lvl_unc = struct.unpack_from("<3Q", data, 80)
    blob = data[lvl_off:lvl_off + lvl_len]
    if scheme == 2:
        blob = zstandard.ZstdDecompressor().decompress(blob, max_output_size=w * h * 8)
    elif scheme not in (0,):
        raise ValueError(f"unsupported supercompression {scheme}")
    if vk_format not in VK_DECODERS:
        raise ValueError(f"unsupported vkFormat {vk_format}")
    name, decode = VK_DECODERS[vk_format]
    bgra = np.frombuffer(decode(blob, w, h), dtype=np.uint8).reshape(h, w, 4)
    rgba = bgra[:, :, [2, 1, 0, 3]].copy()
    if name == "BC5" or path.lower().endswith(("_norm.png.ktx2", "norm.ktx2")):
        # 2-channel normal map: reconstruct Z so glTF rgb sampling works
        x = rgba[:, :, 0].astype(np.float32) / 127.5 - 1.0
        y = rgba[:, :, 1].astype(np.float32) / 127.5 - 1.0
        z = np.sqrt(np.clip(1.0 - x * x - y * y, 0.0, 1.0))
        rgba[:, :, 2] = np.round((z + 1.0) * 127.5).astype(np.uint8)
        rgba[:, :, 3] = 255
    out = path[:-5] if path.lower().endswith(".ktx2") else path + ".png"
    Image.fromarray(rgba, "RGBA").save(out)
    return os.path.basename(out), name, f"{w}x{h}"


for gltf_path in sys.argv[1:]:
    base = os.path.dirname(gltf_path)
    g = json.load(open(gltf_path, encoding="utf-8-sig"))
    converted = {}
    for img in g.get("images", []):
        uri = img.get("uri", "")
        if not uri.lower().endswith(".ktx2"):
            continue
        src = os.path.normpath(os.path.join(base, uri.replace("%20", " ")))
        try:
            if src not in converted:
                converted[src] = convert_ktx2(src)
                print(f"  {os.path.basename(src)} -> {converted[src]}")
            img["uri"] = uri[:-5]  # …png.ktx2 → …png
        except Exception as e:
            print(f"  FAILED {os.path.basename(src)}: {e}")
    # drop the basisu indirection — textures now reference plain PNGs
    for tex in g.get("textures", []):
        ext = tex.get("extensions", {})
        b = ext.pop("KHR_texture_basisu", None)
        if b is not None and "source" not in tex:
            tex["source"] = b["source"]
        if not ext:
            tex.pop("extensions", None)
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in g:
            g[key] = [e for e in g[key] if e != "KHR_texture_basisu"]
            if not g[key]:
                del g[key]
    json.dump(g, open(gltf_path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"updated {gltf_path}")
