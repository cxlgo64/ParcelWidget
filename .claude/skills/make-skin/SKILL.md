---
name: make-skin
description: Make, fix or import an animated character skin for Parcel Widget (ui/skins/<id>/ with sheet.png + skin.json + thumb.png). Use when the user wants a new skin from a description or picture, wants to regenerate or repair poses of a generated skin, wants to tune a skin's on-screen size, or has a ready-made sprite sheet to turn into a skin.
---

# Making Parcel Widget skins

A skin is a folder `ui/skins/<id>/`:
- `sheet.png`: sprite sheet, one animation per row, transparent background, all cells the same size
- `skin.json`: cell size, on-screen size and which frames each animation uses (format in README.md, "Skins")
- `thumb.png`: 48x52 picker icon
- `_work/`: only for generated skins: `job.json` (name, description, provider, model), `ref.png`, `base.png`, `row_<anim>.png` raw generations, `preview.png`. Git-ignored.

The widget uses these animations (missing ones are skipped): `idle blink fidget walk_left walk_right wave jump doze sleep wake cheer think shy look_left look_right look_around`. `look_left`/`look_right` must `hold` the last frame; `idle`, `sleep`, `think`, `walk_*` loop.

All commands run from the repo root with the project venv: `.venv/bin/python -m skinmaker ...`

## 1. New skin from a description / picture

```bash
.venv/bin/python -m skinmaker providers            # which providers have a key
.venv/bin/python -m skinmaker make --name "Cat Courier" \
  --desc "orange tabby cat girl, courier uniform, small red cap, parcel bag" \
  [--ref path/to/picture.png] [--provider openai|gemini|qwen|minimax|hunyuan|stability|replicate|fal] \
  [--model ...] [--base-url ...]
```

- Ask the user which provider to use if more than one has a key; default is `openai`.
- Keys come from the macOS Keychain (saved in the widget's Settings → Custom skin tab) or env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `DASHSCOPE_API_KEY`, `MINIMAX_API_KEY`, `TENCENTCLOUD_SECRET_ID`/`_KEY`, `STABILITY_API_KEY`, `REPLICATE_API_TOKEN`, `FAL_KEY`). Never print, log or commit a key; if one is missing, ask the user to enter it in the widget (right-click her → Settings… → 🎨 Custom skin) or export it themselves.
- One run is about 10 image requests (base + 9 rows, run in parallel) and takes minutes: run it in the background.
- A good description names: species/hair, outfit, colors, one or two props. The pipeline adds the chibi style, poses and green background itself.
- Kimi/Moonshot has no image-generation API; Hunyuan cannot use a reference picture.

## 2. Check the result

Always look before telling the user it's done:
```bash
.venv/bin/python -m skinmaker preview <id>    # writes ui/skins/<id>/_work/preview.png
```
Read the preview image and check every row:
- same character in every row (face, hair, outfit, colors)
- the right number of poses, none cut off or merged (two bodies in one cell, a limb from the neighbour)
- no green left around outlines; nothing extra (text, numbers, ground, shadows)
- walk_right faces right; look_right turns toward the right
- character roughly the same size in every row

Also open the raw `_work/row_<anim>.png` for any row that looks wrong: the command prints "asked for N poses, found M" when cutting went wrong.

## 3. Fix problems

| Problem | Fix |
|---|---|
| A row is off-model, wrong direction, wrong pose count, has text | `.venv/bin/python -m skinmaker redo <id> --rows walk_right,shy` (regenerates only those rows with `base.png` as reference, then reassembles) |
| The whole character is wrong | `make` again with a better `--desc` (or a `--ref`), or regenerate `base.png` by running `make` with `--id <id>` |
| Poses touch, so cutting splits them badly | Edit `_work/row_<anim>.png` (e.g. with Pillow: paint the gap with the background green), then `assemble <id>` |
| Green fringe / holes in the character | Tune `remove_background` thresholds (`lo`, `hi`) in `skinmaker/pipeline.py`, then `assemble <id>` |
| Character too small/big in one row | Usually a stray detached element; check the raw row. `to_cells` scales each row by its median pose height |
| A provider call fails | The error text is in the output; check model name / endpoint (they change: override with `--model` / `--base-url`) |

`assemble` keeps hand-edited `name`, `name_zh`, `display_height`, `hand_y`, `overlap` from the existing skin.json.

## 4. Tune her size

In `skin.json`, `display_height` is her base on-screen height in px (default 116); the widget shows her
1.25x that, times the screen-size zoom. Her speech balloon opens beside her head on the free side.
(`hand_y` / `overlap` are left over from when she held a panel and are no longer used.)
The widget picks up changes when the skin is re-selected (Settings → General) or the widget restarts.

## 5. Import a ready-made sprite sheet (how the bundled whale-maid was made)

When the user already has a sheet (e.g. drawn elsewhere):
1. Read the image and find the grid: sheet size ÷ columns/rows = cell size (whale-maid: 1536x2288, 8x11, cell 192x208). Check the background is transparent; if it's a flat color, key it out with `skinmaker.pipeline.remove_background`.
2. Look at each row and decide which animation it is and which frames to use (a row can serve several animations, e.g. idle/blink/fidget all in row 0; frame lists may repeat or reverse frames).
3. Copy it to `ui/skins/<id>/sheet.png`, write `skin.json` like `ui/skins/whale-maid/skin.json`, and make `thumb.png` (crop the first idle frame to its content, fit in 48x52).
4. `.venv/bin/python -m skinmaker preview <id>` to check the rows/labels line up.

Only commit artwork the user has the rights to share.
