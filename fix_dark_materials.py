# fix_dark_materials.py — Two problems plague every glider's cesium.gltf:
#
# 1) The bright fluorescent-green cockpit is a debug "ENVIROMENT" (sic) world-
#    reference plane the MSFS modelers left behind. baseColorFactor =
#    [0, 0.8, 0, 1].  Hide it by zeroing alpha + alphaMode BLEND.
#
# 2) Every body/wing/livery material has M=1 R=1 because the glTF spec defaults
#    metallicFactor and roughnessFactor to 1.0 when omitted, and
#    fix_texture_links.py stripped the metallicRoughnessTexture without
#    writing the factors back.  Fully metallic + fully rough = renders as
#    dark grey carbon with no specular response under Cesium's IBL.
#
#    Set M=0 (gelcoat is plastic, not metal) and R=0.4 (semi-gloss finish).
#    Glass/canopy materials need R~0.05 so the windshield looks polished.
#
# Usage: py -3.11 fix_dark_materials.py

import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))

MODELS = [
    "assets/Glider models/js3_full/models/js3_cesium.gltf",
    "assets/Glider models/d2c/models/d2c_exterior_lod0_cesium.gltf",
    "assets/Glider models/as33/models/as33_me_18m_exterior_lod0_cesium.gltf",
    "assets/Glider models/ls4 clean/exterior.gltf",
    "assets/Glider models/dg1001/models/dg1001_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_airframe_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_l_cesium.gltf",
    "assets/Glider models/ls8_3d/models/ls8_wing_r_cesium.gltf",
]

GLASS_KEYS = ("glass", "canopy.tinted", "window", "windshield", "windscreen",
              "lens", "led", "strobe_glass", "fuzz")
METAL_KEYS = ("brake_disc", "brakedisc", "rim", "axle", "bolt", "hexagon",
              "metal", "chrome", "wheel_m_", "wheel_pres")

for rel in MODELS:
    path = os.path.join(ROOT, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        print(f"  MISSING: {rel}")
        continue

    g = json.load(open(path, encoding="utf-8-sig"))
    mats = g.get("materials", [])

    m_set = r_set = env_hidden = glass = metal = 0

    for m in mats:
        name = (m.get("name") or "").lower()
        pbr = m.setdefault("pbrMetallicRoughness", {})

        # 1. Kill the bright-green ENVIROMENT debug plane
        if "enviroment" in name or "environment" == name:
            pbr["baseColorFactor"] = [0.0, 0.0, 0.0, 0.0]
            pbr["metallicFactor"]  = 0.0
            pbr["roughnessFactor"] = 1.0
            m["alphaMode"] = "BLEND"
            m["doubleSided"] = False
            env_hidden += 1
            continue

        # 2. Restore sane defaults so non-metal surfaces light correctly
        if "metallicFactor" not in pbr:
            if any(k in name for k in METAL_KEYS):
                pbr["metallicFactor"] = 0.7
                metal += 1
            else:
                pbr["metallicFactor"] = 0.0
            m_set += 1

        if "roughnessFactor" not in pbr:
            if any(k in name for k in GLASS_KEYS):
                # Polished canopy / glass: very smooth so it reflects sky
                pbr["roughnessFactor"] = 0.05
                glass += 1
            elif any(k in name for k in METAL_KEYS):
                pbr["roughnessFactor"] = 0.35
            else:
                # Gelcoat / paint / decals: semi-gloss
                pbr["roughnessFactor"] = 0.4
            r_set += 1

    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{os.path.basename(path):42s}  "
          f"M-set={m_set:3d}  R-set={r_set:3d}  "
          f"glass={glass:2d}  metal={metal:2d}  ENV-hidden={env_hidden}")

print("\nDone. Bump MODEL_CACHE_V in tracker.html to ?v=8")
