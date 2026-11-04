"""Make a widget skin (animated sprite sheet) with an image-generation API.

Steps
  1. base character: one full-body, front-facing picture (from the description, and the
     reference image if given)
  2. one picture per animation: a row of N poses of that same character (the base picture is
     passed as the reference so every row looks like the same character)
  3. remove the flat green background, cut each row into single poses, scale them to the same
     size and stand them on the same baseline in 192x208 cells
  4. walk_left / look_left are mirrored from walk_right / look_right; look_around is put
     together from both
  5. write sheet.png + skin.json + thumb.png into ui/skins/<id>/

Raw generations are kept in ui/skins/<id>/_work/ so a single row can be redone, or the sheet
re-assembled after hand edits, without paying for everything again (see __main__.py).
"""
import concurrent.futures
import io
import json
import os
import re
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .providers import get_provider

CELL = (192, 208)                   # same as the bundled whale-maid skin
STYLE = ("cute chibi anime style, about 2.5 heads tall, full body, clean outlines, "
         "soft cel shading, game sprite")
BG = ("Flat solid pure green (#00FF00) background everywhere. No ground, no shadow, no text, "
      "no numbers, no labels, no borders, no grid lines.")

# Rows that get generated. frames = pose descriptions, left to right.
ROWS = [
    ("idle", ["standing facing the viewer, gentle smile, arms relaxed",
              "same pose, eyes half closed",
              "same pose, eyes fully closed (blinking)",
              "standing, weight shifted to one leg, hands clasped in front",
              "standing, head tilted slightly, hands clasped in front"]),
    ("walk_right", ["walking toward the RIGHT side of the image (side view facing right), left foot forward",
                    "walking right, feet passing, body slightly lower",
                    "walking right, right foot forward",
                    "walking right, feet passing, body slightly higher",
                    "walking right, left foot forward, arms swinging",
                    "walking right, feet passing, arms swinging back"]),
    ("wave", ["standing facing the viewer, smiling",
              "raising one hand to wave",
              "waving, hand tilted outward, big smile",
              "waving, hand tilted inward, big smile"]),
    ("jump", ["crouching, ready to jump",
              "springing upward, arms raised",
              "in mid-air, legs tucked, very happy",
              "coming down, arms out for balance",
              "landing, knees bent"]),
    ("sleep", ["standing, sleepy half-closed eyes, yawning",
               "standing, head nodding down, eyes closed",
               "asleep standing up, head tilted, eyes closed, a small 'z' above",
               "asleep standing up, head drooped further, eyes closed",
               "asleep standing up, mouth slightly open, eyes closed",
               "suddenly awake, eyes wide open, startled"]),
    ("cheer", ["very happy, big smile",
               "both arms raised high, cheering",
               "hopping with joy, arms up",
               "eyes closed with a huge smile, fists pumped",
               "clapping hands happily"]),
    ("think", ["hand on chin, thinking",
               "looking up, finger on cheek, thinking",
               "eyes closed, pondering, hand on chin",
               "head tilted, puzzled"]),
    ("shy", ["blushing, hands on cheeks",
             "blushing, looking away to the side",
             "blushing, covering face with both hands",
             "blushing, fidgeting fingers, shy smile"]),
    ("look_right", ["facing the viewer",
                    "head turned slightly toward the RIGHT side of the image",
                    "head and body turned toward the RIGHT side of the image (three-quarter view)",
                    "looking fully toward the RIGHT side of the image (side view)"]),
]
ROW_NAMES = [r[0] for r in ROWS]

# final sheet rows: name -> how it's made
SHEET_ROWS = ["idle", "walk_right", "walk_left", "wave", "jump", "sleep", "cheer", "think", "shy",
              "look_right", "look_left", "look_around"]

# animations: name -> (sheet row, frame indices into that row, fps, flags)
ANIMS = {
    "idle":        ("idle", [0], 4, {"loop": True}),
    "blink":       ("idle", [0, 1, 2, 1, 0], 14, {}),
    "fidget":      ("idle", [3, 4, 3, 0], 6, {}),
    "walk_right":  ("walk_right", [0, 1, 2, 3, 4, 5], 10, {"loop": True}),
    "walk_left":   ("walk_left", [0, 1, 2, 3, 4, 5], 10, {"loop": True}),
    "wave":        ("wave", [0, 1, 2, 3, 2, 3, 2, 1, 0], 8, {}),
    "jump":        ("jump", [0, 1, 2, 3, 4, 0], 10, {}),
    "doze":        ("sleep", [0, 1, 2], 3, {}),
    "sleep":       ("sleep", [2, 3, 4, 3], 1.5, {"loop": True}),
    "wake":        ("sleep", [5, 5, 0], 6, {}),
    "cheer":       ("cheer", [0, 1, 2, 1, 2, 3, 4, 0], 8, {}),
    "think":       ("think", [0, 1, 2, 3, 2, 1], 3, {"loop": True}),
    "shy":         ("shy", [0, 1, 2, 3, 0], 6, {}),
    "look_right":  ("look_right", [0, 1, 2, 3], 12, {"hold": True}),
    "look_left":   ("look_left", [0, 1, 2, 3], 12, {"hold": True}),
    # look_around row = front, left x3, right x3
    "look_around": ("look_around", [0, 1, 2, 3, 3, 2, 1, 0, 4, 5, 6, 6, 5, 4, 0], 6, {}),
}


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- prompts
def base_prompt(desc, has_ref):
    if has_ref:
        return ("Redraw the character from the reference image as a %s. Keep the same face, hair, outfit "
                "and colors. %s Standing upright facing the viewer, arms relaxed, whole body visible from "
                "head to feet with some margin, centered, only one character. %s" % (STYLE, desc or "", BG))
    return ("A single original character: %s. %s. Standing upright facing the viewer, arms relaxed, whole "
            "body visible from head to feet with some margin, centered, only one character. %s"
            % (desc, STYLE, BG))


def row_prompt(poses, desc, has_ref):
    who = ("the character in the reference image (exactly the same face, hair, outfit, colors and "
           "proportions)" if has_ref else "this character: %s" % desc)
    listing = " ".join("%d) %s." % (i + 1, p) for i, p in enumerate(poses))
    return ("Sprite sheet of %s, %s. Draw exactly %d full-body poses side by side in ONE horizontal row, "
            "left to right, all the same size, feet on the same baseline, wide empty gaps between poses, "
            "nothing overlapping or cut off. Poses: %s %s" % (who, STYLE, len(poses), listing, BG))


# ---------------------------------------------------------------- image processing
def _open(b):
    im = Image.open(io.BytesIO(b) if isinstance(b, (bytes, bytearray)) else b)
    return im.convert("RGBA")


def remove_background(im):
    """Make the flat background transparent. Uses the image's own alpha if it has one."""
    a = np.asarray(im.convert("RGBA")).astype(np.int16)
    if (a[..., 3] < 16).mean() > 0.05:
        return im.convert("RGBA")  # already transparent
    rgb = a[..., :3]
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    d = np.sqrt(((rgb - bg) ** 2).sum(-1))
    lo, hi = 38.0, 95.0

    # background = near-bg pixels connected to the border...
    near = Image.fromarray(((d < hi) * 255).astype(np.uint8), "L")
    h, w = d.shape
    px = near.load()
    pts = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
          [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    for p in pts:
        if px[p] == 255:
            ImageDraw.floodfill(near, p, 128)
    region = np.asarray(near) == 128
    # ...plus, for a green screen, enclosed pockets of that green (e.g. between arm and body)
    g = bg
    if g[1] > 150 and g[0] < 130 and g[2] < 130:
        region |= d < lo + 10

    alpha = np.where(region, np.clip((d - lo) / (hi - lo), 0, 1), 1.0)
    # despill: pull the background color out of semi-transparent edge pixels
    edge = np.asarray(Image.fromarray((region * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    out = rgb.astype(np.float32)
    al = np.clip(alpha, 0.05, 1)[..., None]
    unmixed = (out - (1 - al) * bg) / al
    out = np.where((edge & (alpha < 1))[..., None], unmixed, out)
    if g[1] > 150 and g[0] < 130 and g[2] < 130:  # green spill on the outline
        r_, g_, b_ = out[..., 0], out[..., 1], out[..., 2]
        spill = edge & (g_ > np.maximum(r_, b_))
        out[..., 1] = np.where(spill, np.maximum(r_, b_), g_)
    res = np.dstack([np.clip(out, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(res, "RGBA")


def find_sprites(im, expected=None):
    """Split a row of poses into single sprites by empty vertical gaps. Returns RGBA crops, left to right."""
    a = np.asarray(im)[..., 3] > 40
    cols = a.sum(0) > 1
    segs, x = [], 0
    w = len(cols)
    while x < w:
        if cols[x]:
            x0 = x
            while x < w and cols[x]:
                x += 1
            segs.append([x0, x])
        else:
            x += 1
    # join pieces separated by tiny gaps
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < 4:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    if not merged:
        return []
    areas = [a[:, s0:s1].sum() for s0, s1 in merged]
    big = max(areas)
    keep = [(s, ar) for s, ar in zip(merged, areas) if ar > big * 0.01]
    # small detached bits (a "z", a sparkle, a loose hand) join their nearest neighbour
    med = float(np.median([ar for _, ar in keep]))
    while len(keep) > 1:
        i = min(range(len(keep)), key=lambda k: keep[k][1])
        if keep[i][1] >= med * 0.15:
            break
        (s0, s1), ar = keep.pop(i)
        j = min(range(len(keep)), key=lambda k: min(abs(keep[k][0][0] - s1), abs(s0 - keep[k][0][1])))
        (t0, t1), tar = keep[j]
        keep[j] = ([min(s0, t0), max(s1, t1)], tar + ar)
    if expected and len(keep) > expected:  # extra drawings: keep the biggest, in order
        top = sorted(range(len(keep)), key=lambda k: -keep[k][1])[:expected]
        keep = [keep[k] for k in sorted(top)]
    if expected and len(keep) < expected:  # poses touch each other: split the too-wide pieces
        keep = _split_touching(a, keep, expected)
    out = []
    for (s0, s1), _ in keep:
        y0, y1 = _main_run(a[:, s0:s1].sum(1))
        out.append(im.crop((s0, y0, s1, y1)))
    return out


def _main_run(rowsum, gap=8):
    """Vertical extent of the body: the heaviest run of occupied rows, so a floating "z" or
    sparkle far above the head doesn't count toward the sprite's height."""
    occ = np.where(rowsum > 0)[0]
    runs, start = [], occ[0]
    for p, q in zip(occ[:-1], occ[1:]):
        if q - p > gap:
            runs.append((start, p + 1))
            start = q
    runs.append((start, occ[-1] + 1))
    y0, y1 = max(runs, key=lambda r: rowsum[r[0]:r[1]].sum())
    return int(y0), int(y1)


def _split_touching(mask, keep, expected):
    """Cut wide pieces that hold several touching poses at the thinnest columns."""
    colsum = mask.sum(0)
    segs = [list(s) for s, _ in keep]
    for _ in range(expected):
        if len(segs) >= expected:
            break
        widths = [s1 - s0 for s0, s1 in segs]
        total = sum(widths)
        typical = total / expected
        i = max(range(len(segs)), key=lambda k: widths[k])
        k = min(expected - len(segs) + 1, int(round(widths[i] / typical)))
        if k < 2:
            break
        s0, s1 = segs[i]
        step = (s1 - s0) / k
        cuts = []
        for j in range(1, k):
            ideal = int(s0 + j * step)
            r = max(2, int(step * 0.3))
            lo, hi = max(s0 + 1, ideal - r), min(s1 - 1, ideal + r)
            cuts.append(lo + int(np.argmin(colsum[lo:hi])) if hi > lo else ideal)
        edges = [s0] + cuts + [s1]
        segs[i:i + 1] = [[edges[j], edges[j + 1]] for j in range(k)]
    return [(s, mask[:, s[0]:s[1]].sum()) for s in segs]


def to_cells(sprites, cell=CELL):
    """Scale a row of sprites by one common factor and stand them in cells (bottom-aligned,
    centred on their mass so walking doesn't wobble)."""
    if not sprites:
        return []
    cw, ch = cell
    ref_h = float(np.median([s.height for s in sprites]))
    scale = ch * 0.90 / ref_h
    for s in sprites:
        scale = min(scale, cw * 0.97 / s.width, ch * 0.98 / s.height)
    cells = []
    for s in sprites:
        sw, sh = max(1, round(s.width * scale)), max(1, round(s.height * scale))
        r = s.resize((sw, sh), Image.LANCZOS)
        al = np.asarray(r)[..., 3].astype(float)
        cx = (al.sum(0) * np.arange(sw)).sum() / max(al.sum(), 1)
        c = Image.new("RGBA", cell, (0, 0, 0, 0))
        x = int(round(cw / 2 - cx))
        x = max(0, min(cw - sw, x))
        c.alpha_composite(r, (x, ch - 3 - sh))
        cells.append(c)
    return cells


def mirror(cells):
    return [ImageOps.mirror(c) for c in cells]


# ---------------------------------------------------------------- assembling
def assemble(skin_dir, log=print):
    """(Re)build sheet.png, skin.json, thumb.png from the raw images in _work/.
    Hand-tuned fields in an existing skin.json (name, display_height, hand_y, overlap) are kept."""
    work = os.path.join(skin_dir, "_work")
    job = _read_json(os.path.join(work, "job.json"))
    rows = {}
    for name, poses in ROWS:
        p = os.path.join(work, "row_%s.png" % name)
        if not os.path.exists(p):
            log("row %s: missing, skipped" % name)
            continue
        sprites = find_sprites(remove_background(_open(p)), expected=len(poses))
        if len(sprites) != len(poses):
            log("row %s: asked for %d poses, found %d" % (name, len(poses), len(sprites)))
        if sprites:
            rows[name] = to_cells(sprites)
    if "idle" not in rows:
        raise RuntimeError("the idle row is missing or empty, can't build a skin")
    if "walk_right" in rows:
        rows["walk_left"] = mirror(rows["walk_right"])
    if "look_right" in rows:
        rows["look_left"] = mirror(rows["look_right"])
        lr, ll = rows["look_right"], rows["look_left"]
        rows["look_around"] = [lr[0]] + ll[1:4] + lr[1:4]

    order = [r for r in SHEET_ROWS if r in rows]
    ncols = max(len(rows[r]) for r in order)
    cw, ch = CELL
    sheet = Image.new("RGBA", (ncols * cw, len(order) * ch), (0, 0, 0, 0))
    for ri, r in enumerate(order):
        for ci, c in enumerate(rows[r]):
            sheet.alpha_composite(c, (ci * cw, ri * ch))
    sheet.save(os.path.join(skin_dir, "sheet.png"), optimize=True)

    anims = {}
    for name, (row, frames, fps, flags) in ANIMS.items():
        if row not in rows:
            continue
        n = len(rows[row])
        a = {"row": order.index(row), "frames": [min(f, n - 1) for f in frames], "fps": fps}
        a.update(flags)
        anims[name] = a

    # thumbnail from the first idle frame
    first = rows["idle"][0]
    t = first.crop(first.getbbox() or (0, 0, cw, ch))
    t.thumbnail((48, 52), Image.LANCZOS)
    thumb = Image.new("RGBA", (48, 52), (0, 0, 0, 0))
    thumb.alpha_composite(t, ((48 - t.width) // 2, 52 - t.height))
    thumb.save(os.path.join(skin_dir, "thumb.png"))

    old = _read_json(os.path.join(skin_dir, "skin.json"))
    meta = {
        "name": old.get("name") or job.get("name") or os.path.basename(skin_dir),
        "name_zh": old.get("name_zh") or job.get("name") or "",
        "sheet": "sheet.png", "thumb": "thumb.png", "cell": list(CELL),
        "display_height": old.get("display_height", 116),
        "hand_y": old.get("hand_y", 0.62),
        "overlap": old.get("overlap", 0.36),
        "custom": True,
        "generated": {k: job.get(k) for k in ("provider", "model", "created")},
        "anims": anims,
    }
    with open(os.path.join(skin_dir, "skin.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log("built %s: %d rows, %d animations" % (skin_dir, len(order), len(anims)))
    return meta


def preview(skin_dir, out_path=None):
    """A labelled contact sheet of the finished skin on a checkerboard, for checking by eye."""
    meta = _read_json(os.path.join(skin_dir, "skin.json"))
    sheet = _open(os.path.join(skin_dir, meta.get("sheet", "sheet.png")))
    cw, ch = meta["cell"]
    rows_used = {}
    for name, a in meta["anims"].items():
        rows_used.setdefault(a["row"], []).append(name)
    label_w = 150
    img = Image.new("RGBA", (sheet.width + label_w, sheet.height), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, sheet.height, 16):
        for x in range(label_w, img.width, 16):
            if (x // 16 + y // 16) % 2:
                d.rectangle((x, y, x + 15, y + 15), fill=(225, 225, 225, 255))
    img.alpha_composite(sheet, (label_w, 0))
    for r in range(sheet.height // ch):
        d.line((0, r * ch, img.width, r * ch), fill=(180, 180, 180, 255))
        d.text((6, r * ch + 6), "row %d\n%s" % (r, "\n".join(rows_used.get(r, []))), fill=(0, 0, 0, 255))
    out_path = out_path or os.path.join(skin_dir, "_work", "preview.png")
    img.convert("RGB").save(out_path)
    return out_path


# ---------------------------------------------------------------- generation
def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "custom-%d" % int(time.time())


def _read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _call(provider, prompt, key, ref, aspect, model, base_url, log, tries=2):
    for i in range(tries):
        try:
            return provider.generate(prompt, key, ref=ref, aspect=aspect, model=model or None,
                                     base_url=base_url or None)
        except Exception as e:
            log("  attempt %d failed: %s" % (i + 1, e))
            if i == tries - 1:
                raise


def generate_rows(skin_dir, names, provider_id, key, model=None, base_url=None, log=print,
                  progress=lambda done, total, label: None, should_stop=lambda: False, done0=0, total=None):
    """Generate the given rows into _work/, in parallel. Returns {name: error} for rows that failed."""
    work = os.path.join(skin_dir, "_work")
    job = _read_json(os.path.join(work, "job.json"))
    p = get_provider(provider_id)
    base_path = os.path.join(work, "base.png")
    ref = None
    if p.supports_ref and os.path.exists(base_path):
        with open(base_path, "rb") as f:
            ref = _png_bytes(f.read())
    desc = job.get("desc", "")
    total = total or len(names)
    poses = dict(ROWS)
    failed, done = {}, done0

    def one(name):
        if should_stop():
            raise Cancelled()
        data = _call(p, row_prompt(poses[name], desc, bool(ref)), key, ref, "16:9", model, base_url, log)
        with open(os.path.join(work, "row_%s.png" % name), "wb") as f:
            f.write(_png_bytes(data))
        return name

    with concurrent.futures.ThreadPoolExecutor(max_workers=p.max_parallel) as ex:
        futs = {ex.submit(one, n): n for n in names}
        for fut in concurrent.futures.as_completed(futs):
            n = futs[fut]
            try:
                fut.result()
                log("row %s done" % n)
            except Cancelled:
                failed[n] = "cancelled"
            except Exception as e:
                failed[n] = str(e)[:200]
                log("row %s failed: %s" % (n, e))
            done += 1
            progress(done, total, n)
    if should_stop():
        raise Cancelled()
    return failed


def make_skin(skins_root, name, desc, provider_id, key, ref_bytes=None, model=None, base_url=None,
              skin_id=None, log=print, progress=lambda done, total, label: None, should_stop=lambda: False):
    """Full run: base character + every row + assemble. Returns (skin_id, failed_rows)."""
    p = get_provider(provider_id)
    if not key:
        raise RuntimeError("no API key for %s" % p.name)
    if not (desc or ref_bytes):
        raise RuntimeError("describe the character or give a reference image")
    sid = skin_id or slugify(name)
    base_sid, k = sid, 2
    while os.path.exists(os.path.join(skins_root, sid)) and not skin_id:
        sid, k = "%s-%d" % (base_sid, k), k + 1
    skin_dir = os.path.join(skins_root, sid)
    work = os.path.join(skin_dir, "_work")
    os.makedirs(work, exist_ok=True)
    job = {"name": name or sid, "desc": desc or "", "provider": provider_id, "model": model or "",
           "base_url": base_url or "", "created": time.strftime("%Y-%m-%d %H:%M"), "has_ref": bool(ref_bytes)}
    with open(os.path.join(work, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2, ensure_ascii=False)

    total = 1 + len(ROWS) + 1
    progress(0, total, "base")
    ref = None
    if ref_bytes:
        ref = _png_bytes(ref_bytes)
        with open(os.path.join(work, "ref.png"), "wb") as f:
            f.write(ref)
        if not p.supports_ref:
            log("%s can't use a reference image; using the description only" % p.name)
            ref = None
    log("generating base character with %s" % p.name)
    base = _call(p, base_prompt(desc, bool(ref)), key, ref, "1:1", model, base_url, log)
    with open(os.path.join(work, "base.png"), "wb") as f:
        f.write(_png_bytes(base))
    if should_stop():
        raise Cancelled()
    progress(1, total, "base")

    failed = generate_rows(skin_dir, ROW_NAMES, provider_id, key, model, base_url, log, progress,
                           should_stop, done0=1, total=total)
    if "idle" in failed:
        raise RuntimeError("the idle row failed: %s" % failed["idle"])
    progress(total - 1, total, "assemble")
    assemble(skin_dir, log)
    progress(total, total, "done")
    return sid, failed


def _png_bytes(data):
    """Normalise whatever the provider returned (jpeg/webp/png) to PNG bytes."""
    im = Image.open(io.BytesIO(data))
    if im.format == "PNG":
        return data
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, "PNG")
    return buf.getvalue()
