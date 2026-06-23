# strip_gltf_textures.py — remove all texture references from a glTF.
#
# Used for the LS8 + DG1001 airframes: their MSFS textures are KTX2
# containers with Asobo-proprietary supercompression (vendor scheme 65536)
# that nothing outside MSFS can decode. Without textures the materials fall
# back to their PBR factors — a clean white gelcoat, which is what these
# gliders look like anyway.
#
# Usage: python strip_gltf_textures.py <model.gltf> [...]

import json
import sys

for path in sys.argv[1:]:
    g = json.load(open(path, encoding="utf-8-sig"))
    for m in g.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        had_base = pbr.pop("baseColorTexture", None) is not None
        pbr.pop("metallicRoughnessTexture", None)
        m.pop("normalTexture", None)
        m.pop("occlusionTexture", None)
        m.pop("emissiveTexture", None)
        if m.get("alphaMode") == "BLEND":
            # canopy glass — smoked, glossy, translucent
            pbr["baseColorFactor"] = [0.16, 0.19, 0.23, 0.32]
            pbr["metallicFactor"]  = 0.0
            pbr["roughnessFactor"] = 0.06
        else:
            # glossy gelcoat — glider fuselage/wings are polished white
            if had_base or "baseColorFactor" not in pbr:
                pbr["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]
            pbr["metallicFactor"]  = 0.0
            pbr["roughnessFactor"] = 0.3
        m["pbrMetallicRoughness"] = pbr
    for key in ("textures", "images", "samplers"):
        g.pop(key, None)
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in g:
            g[key] = [e for e in g[key]
                      if e not in ("KHR_texture_basisu", "KHR_texture_transform")]
            if not g[key]:
                del g[key]
    json.dump(g, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print("stripped", path)
