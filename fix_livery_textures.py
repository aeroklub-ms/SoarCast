# fix_livery_textures.py — Plan B Stage 2
#
# The studio panel's livery PNGs are the single texture every glider of a
# class wears — repaint one of these files and the whole class re-skins.
# Most of them ship flat white or near-flat grey: DG1001 and LS8 are 5 KB
# placeholders, LS4 is a 4K pure-white canvas, AS33 and D2C carry some
# baked content but it sits on a flat 231,231,231 background.  Flat colour
# under PBR lighting reads "plastic toy", not "polished gelcoat".
#
# This pass adds three subtle overlays that work regardless of UV layout
# (no model-specific maps required):
#
#   • Vertical gradient — slightly brighter at the top, slightly darker at
#     the bottom.  Reads as sky reflection on the upper fuselage.
#   • Gelcoat noise — ±3 % luminance variation at a fine scale, so the
#     surface stops looking like a smooth render preview and starts looking
#     like real fibreglass.
#   • Edge vignette — corners 8 % darker.  Even sketchy UV unwraps benefit
#     because most layouts park the body in the middle of the canvas.
#
# For files that are clearly placeholders (≤ 50 KB or flat ≥ 250 RGB), the
# script first synthesises a class-appropriate base livery instead of
# overlaying onto a useless white square.  Decals + registration text
# would need per-glider UVs and aren't attempted here.
#
# Backups of the original files are written to textures/livery_base/_bak/
# so the studio panel's "Reset" can still recover them.
#
# Usage: py -3.11 fix_livery_textures.py

import os, shutil
import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(ROOT, "textures", "livery_base")
BAK_DIR  = os.path.join(BASE_DIR, "_bak")
os.makedirs(BAK_DIR, exist_ok=True)

# Per-class base livery for placeholders.  RGB; alpha defaults to 255.
PLACEHOLDER_BASES = {
    "dg1001_20m_base.png":   (250, 250, 252),   # near-white, slight cool tint
    "ls8_standard_base.png": (250, 250, 252),
    "ls4_club_base.png":     (252, 252, 252),
}

def synthesise_base(size, rgb):
    """Make a flat colour canvas of the given RGB triple."""
    return np.full((size, size, 3), rgb, dtype=np.uint8)

def vertical_gradient(arr):
    """Brighter top, darker bottom — 4 % swing, applied as multiplier."""
    h, w = arr.shape[:2]
    ramp = np.linspace(1.04, 0.96, h, dtype=np.float32)[:, None, None]
    out  = arr.astype(np.float32) * ramp
    return np.clip(out, 0, 255).astype(np.uint8)

def gelcoat_noise(arr, seed=0):
    """Fine-grain ±3 % luminance noise.  Same noise applied to RGB so the
    image's hue is preserved — only brightness varies."""
    h, w = arr.shape[:2]
    rng  = np.random.default_rng(seed)
    n    = rng.normal(loc=1.0, scale=0.03, size=(h, w, 1)).astype(np.float32)
    # Slight smoothing so it reads as texture, not film grain
    n_img = Image.fromarray((n[:, :, 0] * 100).clip(0, 255).astype(np.uint8))
    n_img = n_img.filter(ImageFilter.GaussianBlur(radius=1.2))
    n     = np.asarray(n_img, dtype=np.float32)[:, :, None] / 100.0
    out   = arr.astype(np.float32) * n
    return np.clip(out, 0, 255).astype(np.uint8)

def edge_vignette(arr, strength=0.92):
    """Multiply the corners down to `strength` of centre brightness."""
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h / 2, w / 2
    r2     = ((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2
    mask   = (1.0 - (1.0 - strength) * np.clip(r2, 0, 1.0))[:, :, None]
    out    = arr.astype(np.float32) * mask
    return np.clip(out, 0, 255).astype(np.uint8)

def enhance_one(filename):
    src_path = os.path.join(BASE_DIR, filename)
    bak_path = os.path.join(BAK_DIR, filename)

    # Idempotent: if a backup exists we ALWAYS read from it.  That way
    # re-running this script regenerates the enhanced texture from the
    # pristine original instead of stacking overlays.
    if os.path.isfile(bak_path):
        read_path = bak_path
    elif os.path.isfile(src_path):
        shutil.copyfile(src_path, bak_path)
        read_path = bak_path
    else:
        print(f"  MISSING: {filename}")
        return

    src = Image.open(read_path).convert("RGBA")
    size = max(src.size)
    rgb  = np.asarray(src.convert("RGB"))
    alpha = np.asarray(src)[:, :, 3]

    orig_size = os.path.getsize(read_path)
    center_rgb = tuple(int(c) for c in rgb[rgb.shape[0]//2, rgb.shape[1]//2])
    is_placeholder = (orig_size < 50 * 1024) or all(c >= 250 for c in center_rgb)

    if is_placeholder and filename in PLACEHOLDER_BASES:
        # Synthesise a fresh canvas; original alpha is preserved separately
        rgb = synthesise_base(size, PLACEHOLDER_BASES[filename])
        # Resize alpha to match if needed
        if alpha.shape != rgb.shape[:2]:
            alpha = np.asarray(Image.fromarray(alpha).resize((size, size), Image.BILINEAR))

    # Three-pass overlay
    rgb = vertical_gradient(rgb)
    rgb = gelcoat_noise(rgb, seed=hash(filename) & 0xFFFF)
    rgb = edge_vignette(rgb)

    # JPEG can't hold alpha; PNG keeps it if the original had one.
    is_jpeg = src_path.lower().endswith((".jpg", ".jpeg"))
    if is_jpeg or alpha.shape != rgb.shape[:2]:
        out, mode = rgb, "RGB"
    else:
        out = np.concatenate([rgb, alpha[:, :, None]], axis=2)
        mode = "RGBA"

    save_kwargs = {"quality": 88} if is_jpeg else {"optimize": True}
    Image.fromarray(out, mode).save(src_path, **save_kwargs)
    new_size = os.path.getsize(src_path)
    label = "placeholder" if is_placeholder else "overlay"
    print(f"  {filename:30s} {label:11s}  {orig_size/1024:>5.0f} KB -> {new_size/1024:>5.0f} KB")


for fn in sorted(os.listdir(BASE_DIR)):
    if fn.startswith("_"): continue
    if not (fn.lower().endswith(".png") or fn.lower().endswith(".jpg")): continue
    enhance_one(fn)

print(f"\nDone.  Originals backed up to {os.path.relpath(BAK_DIR, ROOT)}.")
print("No MODEL_CACHE_V bump needed — the studio panel loads liveries directly.")
