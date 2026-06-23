#!/usr/bin/env python3
"""
convert_xplane_objs.py — Convert X-Plane .obj glider archives into Cesium-ready glTF 2.0.

X-Plane .obj is NOT Wavefront OBJ. It's a sim-specific text format with header
"800 / OBJ", `VT x y z nx ny nz u v` lines (interleaved vertex/normal/uv), and
`IDX`/`IDX10` index lines.  This script:

  1. extracts each archive in models to add/
  2. parses all .obj parts inside (the wings, fuselage, canopy, etc.)
  3. merges them into one mesh per glider
  4. writes a glTF 2.0 + .bin + texture.png to assets/Glider models/<key>/

Requires only the Python stdlib + Pillow (for any DDS or odd texture conversion).
Run:   python convert_xplane_objs.py

After it succeeds, I'll wire the resulting glTFs into tracker.html's
GLIDER_MODELS + GLIDER_TYPE_RULES.
"""
import os, sys, json, struct, zipfile, shutil, tempfile, glob
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE_DIR = HERE.parent.parent / "models to add"
ASSET_DIR   = HERE / "assets" / "Glider models"

# (archive_filename, output_key, inner-path-glob, INCLUDE list)
# INCLUDE list pinpoints EXTERIOR-ONLY parts (no pilot/wreck/engine/instruments).
# Lowercase substring match against the file basename.  Empty list = "all .obj".
# Per-job options:
#   include:          .obj basenames to use (empty = all)
#   drop_floaters:    apply connected-component analysis to drop tiny islands
#                     (antennas, pitot stubs, orphan vertices) from the body mesh
#   canopy_heuristic: for single-file gliders where the canopy is baked into the
#                     body, classify top-front triangles as glass.  Set the
#                     fraction args: x_front (how far back from the nose the
#                     canopy extends), y_top (how far down from the top it
#                     extends), both as 0..1 of the body bbox.
JOBS = [
    {"arc": "ASG29_B21_V1.00.zip",   "key": "asg29", "glob": "ASG29_B21/**/*.obj",
     "include": ['asg-29_cockpit.obj'],
     # ASG-29 is one big merged mesh where the X-Plane authors used many
     # disconnected sub-meshes (rivets, fairings, antenna stubs, etc.) that
     # cluster all OVER the glider — not just on the antenna.  Floater removal
     # by distance-to-centroid mistakenly classifies wing-tip skin sub-meshes
     # as "far" because the wing IS far from the model's centroid.  Disable
     # for this glider; the few real floaters are acceptable.
     "drop_floaters": False, "canopy_heuristic": (0.40, 0.45)},
    {"arc": "ASK21-E_NHA_1.0.6.ZIP", "key": "ask21", "glob": "ASK21-E_NHA/objects/*.obj",
     "include": ['fuse.obj', 'wing_l.obj', 'wing_r.obj', 'tail_oriz.obj', 'glass.obj'],
     "drop_floaters": True, "canopy_heuristic": None},
    {"arc": "Asw-28 v1.0.6.zip",     "key": "asw28", "glob": "Aircraft/ASW-28/objects/*.obj",
     "include": ['hull.obj', 'canopy.obj', 'canopy edge.obj'],
     "drop_floaters": True, "canopy_heuristic": None},
    {"arc": "Pik-20_1_0_1.zip",      "key": "pik20", "glob": "Pik-20/objects/*.obj",
     "include": ['pik20b.obj', 'glass.obj'],
     "drop_floaters": True, "canopy_heuristic": None},
    {"arc": "SZD 41 A.zip",          "key": "szd41", "glob": "SZD 41 A/objekts/*.obj",
     "include": [],
     "drop_floaters": True, "canopy_heuristic": (0.45, 0.40)},
]

# Universal skip — these never belong in the exterior even if INCLUDE matches.
SKIP_NAME_FRAGS = ['particle', 'light_', 'instrument', 'panel', 'shadow', 'gauge',
                   'pilot', 'wreck', 'internal', 'engine', 'ipad', 'prop',
                   'setup', 'spin', 'sticker', 'lx9000', 'cockpit', 'fuz_inner',
                   'fuz inner']

def parse_xplane_obj(path):
    """Proper X-Plane .obj8 parser with TRIS + ANIM_trans tracking.

       Returns (texture, vertices, indices, is_glass).  Vertices have the
       ANIM_trans translations BAKED IN so control surfaces (ailerons,
       elevator, rudder, speedbrakes) end up at their authored static
       positions instead of all stacked on top of the body at origin —
       which is what every previous round suffered from.

       Only TRIS-emitted triangles are kept; loose IDX entries the source
       never draws are ignored.  ANIM_rotate is not applied (control
       surfaces at rest are at 0° rotation, so it's a no-op)."""
    texture = None
    is_glass = False
    vt_pool  = []     # raw VT lines from the file
    idx_pool = []     # global index pool from IDX / IDX10
    submeshes = []    # list of ((tx,ty,tz), [indices]) — captured at each TRIS
    xform_stack = [(0.0, 0.0, 0.0)]
    in_header = True
    with open(path, 'r', errors='replace') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'): continue
            parts = line.split()
            cmd = parts[0]
            if in_header and cmd in ('A', 'I'):
                continue
            if cmd in ('800', 'OBJ'):
                in_header = False
                continue
            in_header = False
            if cmd == 'TEXTURE' and len(parts) > 1:
                texture = ' '.join(parts[1:]).replace('\\', '/').strip('"')
            elif cmd == 'BLEND_GLASS':
                is_glass = True
            elif cmd == 'VT' and len(parts) >= 9:
                try: nums = [float(p) for p in parts[1:9]]
                except ValueError: continue
                vt_pool.append(tuple(nums))
            elif cmd.startswith('IDX'):
                for n in parts[1:]:
                    try: idx_pool.append(int(n))
                    except ValueError: pass
            elif cmd == 'TRIS' and len(parts) >= 3:
                try: offset, count = int(parts[1]), int(parts[2])
                except ValueError: continue
                if 0 <= offset and offset + count <= len(idx_pool):
                    submeshes.append((xform_stack[-1], idx_pool[offset:offset+count]))
            elif cmd == 'ANIM_begin':
                xform_stack.append(xform_stack[-1])
            elif cmd == 'ANIM_end':
                if len(xform_stack) > 1:
                    xform_stack.pop()
            elif cmd == 'ANIM_trans' and len(parts) >= 4:
                # X-Plane format: dx dy dz [ex ey ez v1 v2 dataref]
                # The first triplet is the static rest position; if dataref
                # is "none" or v1=v2, that's all we need.  We just compose
                # additively onto the current top-of-stack.
                try: dx, dy, dz = float(parts[1]), float(parts[2]), float(parts[3])
                except ValueError: continue
                px, py, pz = xform_stack[-1]
                xform_stack[-1] = (px + dx, py + dy, pz + dz)

    # Bake transforms into a flat vertex / index pair.  Vertices used at
    # different transforms get duplicated; same vertex+same transform reuses.
    cache = {}
    out_v, out_i = [], []
    for (xform, tris_idx) in submeshes:
        tx, ty, tz = xform
        for vi in tris_idx:
            if vi < 0 or vi >= len(vt_pool):
                continue
            key = (vi, xform)
            ci = cache.get(key)
            if ci is None:
                x, y, z, nx, ny, nz, u, v = vt_pool[vi]
                ci = len(out_v)
                cache[key] = ci
                out_v.append((x + tx, y + ty, z + tz, nx, ny, nz, u, v))
            out_i.append(ci)
    # Fallback: some very simple .obj files have no TRIS commands and rely on
    # the index pool directly (canopy-edge files we saw).  Use the pool as-is.
    if not out_v and idx_pool and vt_pool:
        out_v = list(vt_pool)
        out_i = list(idx_pool)
    return texture, out_v, out_i, is_glass


def find_textures(extracted_dir):
    """Return all candidate texture .png paths in the extracted archive."""
    return list(extracted_dir.rglob('*.png')) + list(extracted_dir.rglob('*.PNG'))


def pick_main_texture(texture_refs, extracted_dir):
    """Pick the largest texture referenced by any .obj — that's the body/livery."""
    # First try anything that was named in a TEXTURE line.
    refs = {t.split('/')[-1].lower() for t in texture_refs if t}
    candidates = []
    for png in find_textures(extracted_dir):
        if png.name.lower() in refs:
            candidates.append(png)
    if not candidates:
        candidates = find_textures(extracted_dir)
    if not candidates:
        return None
    # Largest file == the body livery 99% of the time.
    return max(candidates, key=lambda p: p.stat().st_size)


def xplane_to_gltf_axes(x, y, z):
    """X-Plane: +X right, +Y up, +Z back.  glTF:  +X right, +Y up, +Z forward.
       Just negate Z for both positions and normals."""
    return x, y, -z


def drop_floater_components(vertices, indices, max_small=40, dist_factor=1.4):
    """Drop ONLY components that are BOTH small (< max_small verts) AND
       far from the main body centroid (centroid distance > dist_factor ×
       main-body radius).  Conservative — preserves wing/skin sub-meshes that
       X-Plane authors as disconnected, removes only true floaters (antennas,
       orphan vertices, sensor stubs sticking off in space)."""
    n = len(vertices)
    if n == 0 or not indices: return vertices, indices

    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i+1], indices[i+2]
        union(a, b); union(b, c)

    # Group vertex indices by component root.
    comps = {}
    for v in range(n):
        comps.setdefault(find(v), []).append(v)
    # Find the LARGEST component — that's the main body / fuselage.
    main_root = max(comps, key=lambda r: len(comps[r]))
    main_pts  = [vertices[v] for v in comps[main_root]]
    cx = sum(p[0] for p in main_pts) / len(main_pts)
    cy = sum(p[1] for p in main_pts) / len(main_pts)
    cz = sum(p[2] for p in main_pts) / len(main_pts)
    main_radius = max(
        ((p[0]-cx)**2 + (p[1]-cy)**2 + (p[2]-cz)**2) ** 0.5
        for p in main_pts
    )
    far_threshold = main_radius * dist_factor

    drop_roots = set()
    for root, members in comps.items():
        if root == main_root or len(members) >= max_small: continue
        # Centroid distance of this small component.
        mx = sum(vertices[v][0] for v in members) / len(members)
        my = sum(vertices[v][1] for v in members) / len(members)
        mz = sum(vertices[v][2] for v in members) / len(members)
        d = ((mx-cx)**2 + (my-cy)**2 + (mz-cz)**2) ** 0.5
        if d > far_threshold:
            drop_roots.add(root)
    if not drop_roots:
        return vertices, indices

    keep_v = [find(v) not in drop_roots for v in range(n)]
    new_index = {}
    new_verts = []
    for v in range(n):
        if keep_v[v]:
            new_index[v] = len(new_verts)
            new_verts.append(vertices[v])
    new_idx = []
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i+1], indices[i+2]
        if keep_v[a] and keep_v[b] and keep_v[c]:
            new_idx.extend((new_index[a], new_index[b], new_index[c]))
    dropped = n - len(new_verts)
    if dropped:
        print(f"    [floaters] dropped {dropped} verts in {len(drop_roots)} far-away tiny component(s)")
    return new_verts, new_idx


def split_canopy_heuristic(vertices, indices, x_front_frac, y_top_frac):
    """For single-file gliders where the canopy is baked into the body, classify
       triangles whose centroid sits in the top-front region of the bbox as the
       canopy → return (body_v, body_i, glass_v, glass_i) with their own
       re-mapped indices.  No vertex copying — each list keeps its own vertex
       pool from the parent."""
    if not vertices or not indices:
        return vertices, indices, [], []
    xs = [v[0] for v in vertices]; ys = [v[1] for v in vertices]; zs = [v[2] for v in vertices]
    # X-Plane: +X = right, +Y = up, +Z = back  → nose points along -Z (forward).
    # Front (nose-end) = MIN Z.  Top = MAX Y.
    z_min, z_max = min(zs), max(zs)
    y_min, y_max = min(ys), max(ys)
    z_threshold = z_min + (z_max - z_min) * x_front_frac     # front portion
    y_threshold = y_max - (y_max - y_min) * y_top_frac       # top portion

    is_glass_tri = []
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i+1], indices[i+2]
        # Triangle qualifies as canopy when ALL THREE corners are in the
        # top-front region (avoids tagging fuselage skin around the cockpit).
        glass = all(vertices[v][2] <= z_threshold and vertices[v][1] >= y_threshold
                    for v in (a, b, c))
        is_glass_tri.append(glass)

    body_idx, glass_idx = [], []
    for i, g in enumerate(is_glass_tri):
        a, b, c = indices[i*3], indices[i*3+1], indices[i*3+2]
        (glass_idx if g else body_idx).extend((a, b, c))

    # Each primitive needs its own vertex list referencing the verts it uses.
    def repack(idx_list):
        used = {}
        out_v, out_i = [], []
        for v in idx_list:
            if v not in used:
                used[v] = len(out_v)
                out_v.append(vertices[v])
            out_i.append(used[v])
        return out_v, out_i
    body_v, body_i = repack(body_idx)
    glass_v, glass_i = repack(glass_idx)
    if glass_v:
        print(f"    [canopy heuristic] split {len(glass_i)//3} triangle(s) into glass")
    return body_v, body_i, glass_v, glass_i


def _pack_part(vertices, indices, bin_data, vec_min, vec_max):
    """Append vertex/normal/uv/index buffers for one mesh group; return the
       four (offset, count) tuples for its accessors."""
    pos_off = len(bin_data)
    for (x, y, z, nx, ny, nz, u, v) in vertices:
        gx, gy, gz = xplane_to_gltf_axes(x, y, z)
        bin_data += struct.pack('<fff', gx, gy, gz)
        for i, c in enumerate((gx, gy, gz)):
            if c < vec_min[i]: vec_min[i] = c
            if c > vec_max[i]: vec_max[i] = c
    pos_len = len(bin_data) - pos_off

    nrm_off = len(bin_data)
    for (_, _, _, nx, ny, nz, _, _) in vertices:
        ngx, ngy, ngz = xplane_to_gltf_axes(nx, ny, nz)
        bin_data += struct.pack('<fff', ngx, ngy, ngz)
    nrm_len = len(bin_data) - nrm_off

    uv_off = len(bin_data)
    for (_, _, _, _, _, _, u, v) in vertices:
        bin_data += struct.pack('<ff', u, 1.0 - v)
    uv_len = len(bin_data) - uv_off

    # Pad to 4-byte before index buffer (uint32 alignment).
    while len(bin_data) % 4: bin_data += b'\x00'
    idx_off = len(bin_data)
    for i in indices: bin_data += struct.pack('<I', i)
    idx_len = len(bin_data) - idx_off

    return (pos_off, pos_len, nrm_off, nrm_len, uv_off, uv_len, idx_off, idx_len, len(vertices), len(indices))


def write_gltf(out_dir, key, body_verts, body_idx, glass_verts, glass_idx):
    out_dir.mkdir(parents=True, exist_ok=True)
    bin_name = f"{key}.bin"
    gltf_name = f"{key}_cesium.gltf"
    # FORCE WHITE LIVERY for the body — sponsor-heavy textures stripped, ready
    # for the same livery_base PNG workflow as the other 6 models.  Canopy
    # gets a separate tinted-glass material so it's actually visible.
    tex_name = None

    bin_data = bytearray()
    vec_min, vec_max = [float('inf')] * 3, [-float('inf')] * 3
    body_info  = _pack_part(body_verts,  body_idx,  bin_data, vec_min, vec_max) if body_verts  else None
    glass_info = _pack_part(glass_verts, glass_idx, bin_data, vec_min, vec_max) if glass_verts else None
    (out_dir / bin_name).write_bytes(bytes(bin_data))

    buffer_views, accessors, primitives, materials = [], [], [], []
    def add_part(info, mat_idx):
        pos_off, pos_len, nrm_off, nrm_len, uv_off, uv_len, idx_off, idx_len, n_v, n_i = info
        bv = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": pos_off, "byteLength": pos_len, "target": 34962})
        buffer_views.append({"buffer": 0, "byteOffset": nrm_off, "byteLength": nrm_len, "target": 34962})
        buffer_views.append({"buffer": 0, "byteOffset": uv_off,  "byteLength": uv_len,  "target": 34962})
        buffer_views.append({"buffer": 0, "byteOffset": idx_off, "byteLength": idx_len, "target": 34963})
        a = len(accessors)
        accessors.append({"bufferView": bv,   "componentType": 5126, "count": n_v, "type": "VEC3", "min": vec_min, "max": vec_max})
        accessors.append({"bufferView": bv+1, "componentType": 5126, "count": n_v, "type": "VEC3"})
        accessors.append({"bufferView": bv+2, "componentType": 5126, "count": n_v, "type": "VEC2"})
        accessors.append({"bufferView": bv+3, "componentType": 5125, "count": n_i, "type": "SCALAR"})
        primitives.append({
            "attributes": {"POSITION": a, "NORMAL": a+1, "TEXCOORD_0": a+2},
            "indices": a+3,
            "material": mat_idx
        })

    materials.append({
        "name": f"{key}_body",
        "pbrMetallicRoughness": {
            "baseColorFactor": [1, 1, 1, 1],
            "metallicFactor": 0.05,
            "roughnessFactor": 0.55
        },
        "doubleSided": True
    })
    if body_info:  add_part(body_info, 0)
    if glass_info:
        materials.append({
            "name": f"{key}_canopy",
            "alphaMode": "BLEND",
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.25, 0.32, 0.42, 0.55],  # tinted glass — bluish, half-transparent
                "metallicFactor": 0.1,
                "roughnessFactor": 0.15
            }
        })
        add_part(glass_info, 1)

    g = {
        "asset": {"version": "2.0", "generator": "convert_xplane_objs.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes":  [{"mesh": 0}],
        "buffers": [{"uri": bin_name, "byteLength": len(bin_data)}],
        "bufferViews": buffer_views,
        "accessors":   accessors,
        "meshes":      [{"primitives": primitives}],
        "materials":   materials
    }
    (out_dir / gltf_name).write_text(json.dumps(g, indent=2))


def process(job):
    archive_name = job["arc"]; key = job["key"]; obj_glob = job["glob"]
    include_list = job.get("include", [])
    drop_floaters = job.get("drop_floaters", True)
    canopy_heuristic = job.get("canopy_heuristic")
    arc = ARCHIVE_DIR / archive_name
    if not arc.exists():
        print(f"  [skip] missing: {arc}")
        return False
    print(f"\n=== {archive_name}  ->  {key} ===")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(arc) as zf:
            zf.extractall(tmp)
        obj_paths = sorted(tmp.glob(obj_glob))
        if not obj_paths:
            obj_paths = [p for p in tmp.rglob('*.obj') if 'MACOSX' not in str(p)]
        if include_list:
            inc = [s.lower() for s in include_list]
            obj_paths = [p for p in obj_paths if p.name.lower() in inc]
        else:
            obj_paths = [p for p in obj_paths if not any(s in p.name.lower() for s in SKIP_NAME_FRAGS)]
        print(f"  parsing {len(obj_paths)} .obj parts")

        body_v, body_i, glass_v, glass_i = [], [], [], []
        body_off, glass_off = 0, 0
        for op in obj_paths:
            tex, verts, idx, is_glass_attr = parse_xplane_obj(op)
            if not verts: continue
            name_lower = op.name.lower()
            is_glass = is_glass_attr or 'glass' in name_lower or 'canop' in name_lower
            print(f"    + {op.name}: {len(verts)} verts, {len(idx)} idx{'  [glass]' if is_glass else ''}")
            if is_glass:
                glass_v.extend(verts)
                glass_i.extend(i + glass_off for i in idx)
                glass_off += len(verts)
            else:
                body_v.extend(verts)
                body_i.extend(i + body_off for i in idx)
                body_off += len(verts)
        if not body_v and not glass_v:
            print(f"  [error] no vertices parsed — likely not standard X-Plane format")
            return False

        # Post-process the BODY mesh:
        #   1. Drop tiny disconnected components (antennas, orphan vertices).
        #   2. If this job wants a canopy heuristic (single-file source with the
        #      canopy baked in), split front-top triangles into a glass primitive.
        if drop_floaters and body_v:
            body_v, body_i = drop_floater_components(body_v, body_i)
        if canopy_heuristic and body_v and not glass_v:
            x_front, y_top = canopy_heuristic
            body_v, body_i, hg_v, hg_i = split_canopy_heuristic(body_v, body_i, x_front, y_top)
            glass_v.extend(hg_v); glass_i.extend(hg_i)

        out_dir = ASSET_DIR / key
        write_gltf(out_dir, key, body_v, body_i, glass_v, glass_i)
        print(f"  wrote {out_dir}/{key}_cesium.gltf"
              f"  body {len(body_v)}v/{len(body_i)//3}t  glass {len(glass_v)}v/{len(glass_i)//3}t")
        return True


if __name__ == "__main__":
    print(f"Archive dir: {ARCHIVE_DIR}")
    print(f"Asset dir:   {ASSET_DIR}")
    if not ARCHIVE_DIR.exists():
        print("ERROR: 'models to add' directory not found.")
        sys.exit(1)
    ok = 0
    for job in JOBS:
        if process(job):
            ok += 1
    print(f"\nDone: {ok}/{len(JOBS)} models converted.")
    print("Next: tell Claude the converted keys + we'll wire them into tracker.html.")
