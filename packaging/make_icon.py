"""Make the app icon from the bundled skin's first idle frame: packaging/icon.icns on macOS
(needs iconutil), packaging/icon.ico on Windows; icon.png on both."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SKIN = os.path.join(HERE, "..", "ui", "skins", "whale-maid")


def main():
    meta = json.load(open(os.path.join(SKIN, "skin.json"), encoding="utf-8"))
    cw, ch = meta["cell"]
    a = meta["anims"]["idle"]
    sheet = Image.open(os.path.join(SKIN, meta["sheet"])).convert("RGBA")
    col = a["frames"][0]
    frame = sheet.crop((col * cw, a["row"] * ch, (col + 1) * cw, (a["row"] + 1) * ch))
    frame = frame.crop(frame.getbbox())

    S = 1024
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    pad = 100
    # macOS-style rounded square, white with the balloon's blue frame
    d.rounded_rectangle((pad, pad, S - pad, S - pad), radius=185, fill=(255, 255, 255, 255),
                        outline=(47, 128, 237, 255), width=26)
    icon.alpha_composite(bg)
    box = S - 2 * pad - 90
    frame.thumbnail((box, box), Image.LANCZOS)
    icon.alpha_composite(frame, ((S - frame.width) // 2, (S - frame.height) // 2 + 10))

    icon.save(os.path.join(HERE, "icon.png"))
    if sys.platform != "darwin":
        out = os.path.join(HERE, "icon.ico")
        icon.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print("wrote", out)
        return

    tmp = tempfile.mkdtemp()
    iconset = os.path.join(tmp, "icon.iconset")
    os.makedirs(iconset)
    for size in (16, 32, 128, 256, 512):
        icon.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, "icon_%dx%d.png" % (size, size)))
        icon.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(iconset, "icon_%dx%d@2x.png" % (size, size)))
    out = os.path.join(HERE, "icon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    shutil.rmtree(tmp)
    print("wrote", out)


if __name__ == "__main__":
    main()
