# make_white_liveries.py — give the texture-less airframes a paintable base.
#
# ls8 + dg1001 lost their original textures to Asobo's undecodable KTX2
# supercompression (scheme 65536 — see strip_gltf_textures.py). They still
# carry their UV coordinates, so: generate a near-white 1024² PNG in
# textures/livery_base/ and wire it into every gelcoat (non-BLEND) material
# as the baseColorTexture. Result: identical white look by default, but
# painting the PNG shows up on the airframe after a reload — same
# "download, repaint, give back" loop as the other classes. (The original
# UV layout is Asobo's, so expect to find the islands by experiment.)
#
# Usage: python make_white_liveries.py

import json
import os

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVERY_DIR = os.path.join(ROOT, "textures", "livery_base")
os.makedirs(LIVERY_DIR, exist_ok=True)

JOBS = [
    ("ls8_standard_base.png", 4, [
        r"assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
        r"assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
        r"assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf"]),
    ("dg1001_20m_base.png", 4, [
        r"assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf"]),
]

for livery_file, depth, gltfs in JOBS:
    dst = os.path.join(LIVERY_DIR, livery_file)
    if not os.path.isfile(dst):
        Image.new("RGB", (1024, 1024), (250, 250, 252)).save(dst)
        print(f"created {dst}")
    uri = "../" * depth + "textures/livery_base/" + livery_file
    for rel in gltfs:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        g = json.load(open(path, encoding="utf-8-sig"))
        g["samplers"] = [{"magFilter": 9729, "minFilter": 9987,
                          "wrapS": 10497, "wrapT": 10497}]
        g["images"]   = [{"uri": uri, "mimeType": "image/png"}]
        g["textures"] = [{"sampler": 0, "source": 0}]
        wired = 0
        for m in g.get("materials", []):
            if m.get("alphaMode") == "BLEND":
                continue                      # canopy glass stays untextured
            pbr = m.setdefault("pbrMetallicRoughness", {})
            pbr["baseColorTexture"] = {"index": 0}
            wired += 1
        json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
        print(f"{rel}: white base wired into {wired} material(s)")
