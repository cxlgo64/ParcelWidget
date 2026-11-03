# Parcel Widget

A tiny always-on-top macOS desktop widget that finds tracking numbers in your Gmail and checks their latest status on [parcelsapp.com](https://parcelsapp.com) every hour.

![preview](docs/preview.png)

## Features
- Scans Gmail (read-only, via IMAP + app password) for **UPS, FedEx, USPS and Amazon** tracking numbers
- Reads the latest tracking event from parcelsapp.com with a real browser (Playwright)
- Shows the first 3 active shipments; expand to see all
- Delivered shipments turn green; click **✓ Got it** to archive
- Collapses to a single line when there are no packages
- Screen-size presets (13" / 14" / 15" / 16" / external), pin on top, English / 中文
- If parcelsapp blocks lookups, switch browser: Chrome, Edge, Brave, Chromium, Firefox or WebKit
- Optional animated **skin**: a character stands behind the panel's corner as if holding it, and reacts to what happens

## Install
Requires macOS and Python 3.9+.

```bash
git clone https://github.com/<your-username>/ParcelWidget.git
cd ParcelWidget
chmod +x *.command
./install.command      # creates .venv, installs deps + Chromium, starts at login
```

Then open ⚙ in the widget and enter your Gmail address and an
[app password](https://myaccount.google.com/apppasswords) (2-Step Verification must be on).

- Start manually: `./start.command`
- Remove auto-start: `./uninstall_autostart.command`

## Skins
A skin is a folder in `ui/skins/<id>/` with a sprite sheet and a `skin.json` describing it:

```json
{
  "name": "My Character", "sheet": "sheet.png", "thumb": "thumb.png",
  "cell": [192, 208],          // size of one frame in the sheet
  "display_height": 116,       // on-screen height (before the screen-size zoom)
  "hand_y": 0.62,              // panel bottom sits at this fraction of her height
  "overlap": 0.36,             // how far she tucks behind the panel corner
  "anims": { "idle": {"row": 0, "frames": [0], "fps": 4, "loop": true}, ... }
}
```

Animations the widget uses: `idle`, `blink`, `fidget`, `walk_left`, `walk_right`, `wave`, `jump`,
`doze`, `sleep`, `wake`, `cheer`, `think`, `shy`, `look_left`, `look_right`, `look_around`
(missing ones are simply skipped).

| When | She… |
|---|---|
| Idle | blinks, fidgets, looks around, peeks at the panel |
| Mouse over the panel | turns to read it with you |
| Refreshing | thinks |
| New package / delivered | cheers / jumps + cheers, with a speech bubble |
| Click her | waves, jumps or gets shy, and gives a summary |
| Dragging the window | runs in the drag direction |
| 5 min without mouse activity | dozes off; move the mouse to wake her |

> Only commit skin artwork you have the rights to share.

## Privacy
- Your Gmail app password is stored in the **macOS Keychain**, never in a file.
- Shipments, settings and logs live in `~/Library/Application Support/ParcelWidget/`, outside this repo.

## Recognized tracking numbers
| Carrier | Pattern |
|---|---|
| UPS | `1Z` + 16 characters |
| Amazon | `TBA` + 12 digits |
| USPS | 22/26 digits starting with 92–95, or `XX123456789US` |
| FedEx | 12/15/20/22 digits (only if the email mentions FedEx) |

Many Amazon emails only contain a "Track package" button with no number. Add those manually with ＋.

## Troubleshooting
- **"Blocked" / "No data"**: pick another browser in ⚙, or untick "Run the browser in the background".
- **Debug one number** (quit the widget first):
  `.venv/bin/python debug_track.py 1Z999AA10123456784 --browser firefox`
- **Logs**: `~/Library/Application Support/ParcelWidget/widget.log`
- **Tests**: `.venv/bin/python -m pytest test_parser.py`

## Project layout
| File | What it does |
|---|---|
| `app.py` | Window, background scheduler, JS ↔ Python API |
| `mail_scanner.py` | Gmail IMAP scan |
| `tracking_parser.py` | Tracking-number regexes, delivered detection |
| `tracker.py` | parcelsapp lookup via Playwright |
| `db.py` | SQLite storage |
| `ui/index.html` | The widget UI |

## License
MIT
