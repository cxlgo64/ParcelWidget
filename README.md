# Parcel Widget

> **macOS** (11+, Apple Silicon or Intel) and **Windows** (10 version 2004+ / 11). The Windows version does
> the same jobs with Windows' own parts: see [Windows](#windows).

A little animated character on your desktop who does small jobs for you and reports in a comic speech balloon.
Her first jobs: finding tracking numbers in your Gmail and checking them on [parcelsapp.com](https://parcelsapp.com),
and a CPU / memory / network monitor drawn as candlestick charts.

![preview](docs/preview.png)

## How it works
1. **At launch** she runs each job once and reports in her speech balloon (step by step while it runs:
   reading Gmail, asking parcelsapp, what changed). Confirm each report with its button.
   Every check is remembered (time + result, `memory.json`): if the widget restarts before the next
   scheduled check is due, she shows the last result instead of checking again.
2. **Then she goes idle** and the jobs keep running on their own schedule. Parcels are checked
   every 90 minutes from 09:00 to 19:00 (changeable); the balloon only pops up again when something changes.
   Nothing runs while the Mac sleeps. When it wakes up she checks once, quietly, unless the last check
   is still current. If the network isn't back yet she retries up to 3 times, 3 minutes apart.
3. **Idle**: hover over her for a button per job (📦 packages, 📊 system monitor, 👉 poke).
   Click her to poke her; drag her to move her.
4. **Right-click her** (or click the menu bar icon) for the menu: one submenu per job, Show Widget,
   Settings…, Quit. Everything detailed is in the **Settings** window.

## Features
- 📦 **Parcels**: scans Gmail (read-only, IMAP + app password) for **UPS, FedEx, USPS and Amazon** tracking numbers,
  reads the latest event from parcelsapp.com with a real browser (Playwright); delivered ones get a **✓ Got it** button.
  Add a number right in her balloon (hover → 📦, or menu → Parcels → Add Tracking Number…);
  archived ones, the schedule, Gmail and browser are in Settings → Parcels
- ✉️ **Mail**: a first look at your inboxes, sorted into important (replies, real people, colleagues, codes,
  "action needed"), the rest, and what you can skip (job alerts, ads, newsletters, no-reply mail), plus your own
  "always important / always skip" rules. Apple Mail is read through the Mail app; **Outlook** (the New Outlook
  shares nothing with other apps) is read from Microsoft after an optional sign-in with a code, shown in her
  balloon. Read only: nothing is moved, deleted or marked read. Nothing starts until you open ✉️ Mail once;
  after that she looks every 30 min and only speaks up about new important unread mail. The Microsoft sign-in
  never pops up by itself: when it's needed (or has to be renewed) she waits until you open ✉️ Mail.
  Outlook needs a Microsoft app ID once (Settings → ✉️ Mail explains how)
- 🤖 **Claude Code** (Settings → 🤖 Claude, off until you turn it on): when Claude finishes she tells you how it
  went (the project and Claude's summary); when Claude needs you she says so. Permission requests (run a
  command, edit a file, ...) get Allow / Always allow / Deny buttons in her balloon, and Claude's multiple-choice
  questions can be answered there too. "In Claude", or no answer in time, leaves it to Claude's own window. It
  works through Claude Code hooks: turning it on adds `claude_hook.py` to `~/.claude/settings.json` (a backup of
  the file is kept), turning it off removes it; the hook does nothing while the widget isn't running
- ✨ **Claude小姐 (Miss Claude)**: her orange starburst button opens a chat in her balloon. What you type runs as
  a Claude Code task (the `claude` command line, signed in as you) in the project folder you pick; you see what
  Claude is doing, then the answer. Follow-ups continue the same conversation; "New chat" starts over, "Stop"
  ends a run. Permission requests from these runs come to her balloon too (with 🤖 Claude watching turned on)
- 🌀 **Codex**: the same chat, run by OpenAI's Codex (`codex exec`, signed in as you with the model and settings
  of `~/.codex/config.toml`; the command line inside the ChatGPT app is found by itself). Codex can't ask for
  permission in such a run, so it works in its sandbox: it may change files in the folder you picked, nowhere
  else, and has no network. `"codex": {"sandbox": "read-only"}` in `config.json` makes it look-only.
- 🐙 **GitHub**: your repositories (latest push first: private or public, language, stars, open issues and
  pull requests, whether checks passed), your unread notifications, and the copies on this Mac (uncommitted
  files, commits not pushed). Asked through the GitHub command line (`gh`), signed in as you: the widget never
  sees your token. Forks, archived repositories, background checks and where to look for copies: Settings → 🐙 GitHub.
- 📊 **System monitor**: CPU, memory, download and upload as candlestick charts (5 s – 1 min per candle,
  red-up or green-up colors)
- 🔌 **USB**: lists what's plugged in over USB and the driver running each device (bundle, version, kext or
  DriverKit), then checks online whether the driver is current. Apple's drivers come with macOS, so she asks
  Software Update whether a newer macOS is out; for other vendors' drivers she looks the vendor up in the public
  USB ID database and searches the web (a version number found there is a hint, with the links to check it).
  Nothing is updated for you. A **USB printer** that isn't in the printer list: AirPrint printers need no driver;
  otherwise she looks for its driver on the Mac, then in Apple's printer driver catalog (matched by model),
  and downloads it from Apple to `~/Downloads/Printer Drivers` (you install it). Plugged-in devices are noticed within 30 s
- 🖨 **Printers & AirPrint** (Settings → 🖨 Printers): the printer list grouped by physical printer. One click
  sets a printer up with AirPrint (no driver: macOS asks the printer what it can do) - network printers by
  address or found nearby, USB printers too. The same printer is often in the list two or three times (a generic
  driver, an entry gone offline); she keeps the AirPrint one and removes the others when you confirm. macOS may
  ask for your password to change the printer list.
- **More than one copy**, like accounts: opening the app while it's already open asks whether to go to the open
  one or open another. Each copy has its own settings, Gmail and parcels (copy 2, 3, ... live in
  `Profiles/<n>` in the data folder; the menu bar shows `#2`, ...). With none open, the one used last starts.
- 👉 **Poke**: a random move and a line
- Animated **skins**, and **custom skins** an image AI draws from your description or picture
- Screen-size presets, keep on top, English / 中文, lives in the **menu bar** (no Dock icon)

## Windows
Everything above works on Windows too; where macOS and Windows differ, she uses the Windows way:

| | macOS | Windows |
|---|---|---|
| Where she lives | menu bar icon, no Dock icon | **tray icon** near the clock, no taskbar button. Left-click it: show / hide her; right-click it (or her): the menu |
| 📦 Parcels | Google Chrome by default | **Microsoft Edge** by default (it's on every PC); Chrome, Brave, Firefox… in Settings |
| ✉️ Mail on this computer | Apple Mail | the **classic Outlook** desktop app (it has to be open). The new Outlook and the Windows Mail app don't answer other programs: use the Microsoft sign-in for those |
| Saved passwords | encrypted file, Touch ID | encrypted file (Windows data protection: only your Windows account on this PC can open it), **Windows Hello** (fingerprint, face or PIN) |
| 🤖 Claude Code hook | `/usr/bin/python3 claude_hook.py`, a private socket | `ParcelWidgetHook.exe` next to the app (from source: your Python), a port on this PC only with a password |
| ✨ Claude小姐 / 🌀 Codex | `claude` / `codex` command lines | the same (`claude`, `npm install -g @openai/codex`); what you type is handed over on standard input |
| 🐙 GitHub | `brew install gh` | `winget install GitHub.cli` |
| 🔌 USB devices and drivers | ioreg; Apple's drivers update with macOS (Software Update) | the registry; Windows' drivers update with **Windows Update**, which she asks - driver updates waiting there are marked on the device |
| A USB printer that isn't set up | AirPrint, or Apple's driver downloaded for you | Windows adds it by itself (plug and play); if it didn't: the maker's driver links and a button to Settings › Printers & scanners |
| 🖨 Printers | one-click AirPrint (CUPS) | one-click **driverless** setup of network printers (Microsoft IPP Class Driver, `Add-Printer -IppURL`), found nearby or by address; duplicates, default, test page |
| More than one copy, sleep / wake, skins, 📊 monitor, 👉 poke | ✓ | ✓ |
| Data folder | `~/Library/Application Support/ParcelWidget` | `%APPDATA%\ParcelWidget` |

Needs the **WebView2 runtime** (part of Windows 11 and of current Windows 10) and, from source, **Python 3.10 - 3.13**
with the .NET Framework 4.8 that Windows already has.

## Install
### Windows
**From source** (needs [Python](https://www.python.org/downloads/windows/), "Add python.exe to PATH" ticked):
```bat
git clone https://github.com/cxlgo64/ParcelWidget.git
cd ParcelWidget
install.bat
```
`install.bat` creates `.venv`, installs what she needs, makes her start when you sign in and starts her.
Start by hand: `start.bat`. No more auto-start: `uninstall_autostart.bat`.

**Build the app** (a folder with `Parcel Widget.exe`, zipped; no Python needed to run it):
```bat
packaging\build_win.bat
```
-> `dist\ParcelWidget-<version>-Windows-x64.zip`. Unzip it anywhere and run `Parcel Widget.exe` (Windows may say
"Windows protected your PC" the first time, because the app isn't signed: More info → Run anyway).
To start it when you sign in: press Win+R, type `shell:startup`, and put a shortcut to `Parcel Widget.exe` there
(add ` --autostart` to the shortcut's target and she stays quiet if she's already open).

### macOS, option A: the app (DMG)
1. Download `ParcelWidget-<version>-macOS-arm64.dmg` from [Releases](https://github.com/cxlgo64/ParcelWidget/releases)
   (Apple Silicon; on an Intel Mac build it yourself, see below).
2. Open it and drag **Parcel Widget** into **Applications**.
3. The app isn't signed by Apple, so the first time: right-click it → **Open** → **Open**
   (or System Settings → Privacy & Security → **Open Anyway**).
4. She appears on your desktop and a parcel icon appears in the menu bar. Right-click her → **Settings…** →
   📦 Parcels to connect Gmail with an [app password](https://myaccount.google.com/apppasswords)
   (2-Step Verification must be on).

Parcel lookups use your installed **Google Chrome** by default (change it in Settings → Parcels).
To start it at login: System Settings → General → Login Items → ＋ → Parcel Widget.

### macOS, option B: from source
Requires Python 3.9+.

```bash
git clone https://github.com/cxlgo64/ParcelWidget.git
cd ParcelWidget
chmod +x *.command
./install.command      # creates .venv, installs deps + Chromium, starts at login
```

- Start manually: `./start.command`
- Remove auto-start: `./uninstall_autostart.command`

### macOS: build the DMG yourself
```bash
./packaging/build_mac.sh     # -> dist/ParcelWidget-<version>-macOS-<arch>.dmg
```

## Skins
A skin is a folder in `ui/skins/<id>/` with a sprite sheet and a `skin.json` describing it:

```json
{
  "name": "My Character", "sheet": "sheet.png", "thumb": "thumb.png",
  "cell": [192, 208],          // size of one frame in the sheet
  "display_height": 116,       // base on-screen height (x1.25, then the screen-size zoom)
  "anims": { "idle": {"row": 0, "frames": [0], "fps": 4, "loop": true}, ... }
}
```

Animations the widget uses: `idle`, `blink`, `fidget`, `walk_left`, `walk_right`, `wave`, `jump`,
`doze`, `sleep`, `wake`, `cheer`, `think`, `shy`, `look_left`, `look_right`, `look_around`
(missing ones are simply skipped).

| When | She… |
|---|---|
| Idle | blinks, fidgets, looks around |
| Mouse on her balloon | turns to read it with you |
| A job is running | thinks |
| A report arrives | delivered: jumps + cheers; new package: cheers; a failure: shy |
| Click her (poke) | waves, jumps, cheers or gets shy, and says something |
| Dragging the window | runs in the drag direction |
| 5 min without mouse activity | dozes off; move the mouse to wake her |

> Only commit skin artwork you have the rights to share.

### Custom skins (image AI)
Settings → **🎨 Custom skin** (or ＋ next to the characters in Settings → General): give a name, a description
and optionally a reference picture, pick an image AI and enter its API key (saved encrypted, see below).
About 10 image requests make a base character plus one row of poses per animation; the widget removes the
green background, cuts and aligns the poses and switches to the new skin.

| Provider | Key | Reference picture |
|---|---|---|
| OpenAI gpt-image (or any OpenAI-compatible endpoint) | API key | ✓ |
| Google Gemini image | API key | ✓ |
| Qwen (Alibaba Model Studio) | DashScope API key | ✓ |
| MiniMax image-01 | API key | ✓ |
| Tencent Hunyuan | `SecretId:SecretKey` | – |
| Stability AI | API key | style only |
| Replicate / fal.ai | token / key | ✓ (depends on model) |

Model names and endpoints can be changed under "Advanced". From the command line:
`.venv/bin/python -m skinmaker --help` (make, redo some rows, reassemble, preview).
With Claude Code, the `make-skin` skill in `.claude/skills/` knows how to make, check, fix and tune skins.

## Privacy
- Your Gmail app password and image AI keys are saved **encrypted** in `secrets.vault` (AES-256 + HMAC,
  with a key tied to this Mac's hardware, so the file is useless anywhere else). She asks for **Touch ID**
  (or your Mac password) once per launch before using them; turn that off in Settings → General.
  The fingerprint is a lock inside the widget: a program running as you on this Mac could still
  decrypt the file. Older versions kept them in the Keychain; they're moved over on first use (the Keychain
  may ask one last time) and the Keychain items are left as they were.
- Mail: subjects, senders and previews stay in memory; on disk she keeps only hashed message ids (so old mail
  isn't announced again). Sorting is done on the Mac with simple rules, nothing is sent anywhere. The Microsoft
  sign-in asks only for `Mail.Read` and `User.Read` (read mail, your address); it's kept as a refresh token in
  the encrypted vault. Settings → ✉️ Mail → Sign out removes it.
- Claude Code: the hook talks only to the widget, over a socket in the data folder that only you can open.
  Claude's summaries and questions stay in her balloon until confirmed; nothing is saved or sent anywhere.
- GitHub: asked through `gh` (which keeps its own sign-in); repositories and notifications stay in her balloon,
  nothing is saved. Local copies are only read with `git status`, never changed or fetched.
- Shipments, settings and logs live in `~/Library/Application Support/ParcelWidget/` (Windows:
  `%APPDATA%\ParcelWidget\`), outside this repo.
- Windows: the vault is encrypted with Windows' data protection (DPAPI) for your Windows account, and she asks
  for Windows Hello instead of Touch ID (if Hello isn't set up on the PC, she doesn't ask). The Claude Code hook
  reaches her through a port that only accepts connections from this PC, and has to show a password kept in
  your data folder. The USB check asks Windows Update what's waiting; nothing is downloaded or installed.
- The USB check sends vendor and product names (not serial numbers) to DuckDuckGo to search for drivers,
  and downloads driver lists and printer drivers only from Apple's servers (and linux-usb.org's ID list).

## Recognized tracking numbers
| Carrier | Pattern |
|---|---|
| UPS | `1Z` + 16 characters |
| Amazon | `TBA` + 12 digits |
| USPS | 22/26 digits starting with 92–95, or `XX123456789US` |
| FedEx | 12/15/20/22 digits (only if the email mentions FedEx) |

Many Amazon emails only contain a "Track package" button with no number. Add those in her balloon (hover over her → 📦).

## Troubleshooting
- **"Blocked" / "No data"**: pick another browser in Settings → Parcels, or untick "Run the browser in the background".
- **Debug one number** (quit the widget first):
  `.venv/bin/python debug_track.py 1Z999AA10123456784 --browser firefox`
- **Logs**: Settings → 📝 Log (live, filter by checks / errors), or `~/Library/Application Support/ParcelWidget/widget.log`
  (Windows: `%APPDATA%\ParcelWidget\widget.log`; from source use `.venv\Scripts\python.exe` where this page says `.venv/bin/python`)
- **Windows, she has a solid background instead of a see-through one**: update the WebView2 runtime (Microsoft Edge
  updates it), and pywebview (`.venv\Scripts\pip install -U pywebview`)
- **Windows, no tray icon**: it may be hidden behind the `^` arrow near the clock; drag it out to keep it visible
- **Tests**: `.venv/bin/python -m pytest test_parser.py`

## Project layout
| File | What it does |
|---|---|
| `app.py` | Windows, scheduler loop, JS ↔ Python API |
| `core.py` | Paths, config, log, passwords, skins, size presets |
| `plat.py` | The small differences between macOS and Windows: opening things, file locks, PowerShell |
| `vault.py` | Saved passwords and API keys: encrypted file, unlocked with Touch ID / Windows Hello |
| `power.py` | Sleep / wake of the computer |
| `mailread.py` | Reading the inbox: Apple Mail (JavaScript for Automation) or the classic Outlook on Windows (PowerShell), Outlook through Microsoft (Graph, device code sign-in), the first sort |
| `claude_hook.py` | Claude Code hook: hands Claude's events to her over a local socket, returns your answer |
| `features/` | The character's jobs: `parcels.py`, `mail.py`, `claude.py`, `codex.py` (both chats: `chat.py`), `sysmon.py`, `usb.py`, `poke.py` (how to add one: `features/__init__.py`) |
| `usbscan.py` | USB devices, their drivers and the printers (macOS: ioreg, kmutil, CUPS) |
| `usbscan_win.py` | USB devices and their drivers (Windows: the registry, the configuration manager) |
| `instance.py` | Which copy this is: one already open → go to it or open another; each copy's data folder |
| `airprint.py` | The printer list grouped by printer, one-click AirPrint, duplicates (macOS: CUPS lpadmin, ipptool) |
| `winprint.py` | The same for Windows: driverless setup (IPP class driver), finding printers nearby (mDNS), duplicates |
| `driverinfo.py` | Online lookups for the USB check: USB IDs, Software Update / Windows Update, web search, Apple's printer drivers |
| `reports.py` | Reports shown in her balloon until confirmed |
| `menus.py` | The menu as data (menu bar icon and right-click) |
| `menubar.py` | macOS menu bar icon, right-click menu |
| `wintray.py` | Windows tray icon, right-click menu |
| `mail_scanner.py` | Gmail IMAP scan |
| `tracking_parser.py` | Tracking-number regexes, delivered detection |
| `tracker.py` | parcelsapp lookup via Playwright |
| `db.py` | SQLite storage |
| `skinmaker/` | Custom skin generation: image providers + sprite sheet pipeline |
| `ui/index.html` | The character, her balloon and hover buttons; each job's page side (`FEATURES`) |
| `ui/settings.html` | The settings window |
| `ui/i18n.js` | English / 中文 strings |
| `packaging/` | Building the macOS app + DMG and the Windows app + zip (PyInstaller) |
| `install.bat`, `start.bat`, `uninstall_autostart.bat` | Windows: install from source, start, stop starting at sign-in (the `.command` files are the macOS ones) |

## License
MIT
