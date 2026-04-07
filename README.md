# WeChat Chat History Export

A macOS desktop tool to decrypt, browse, and export WeChat (微信) chat history from locally stored databases.

![Platform](https://img.shields.io/badge/platform-macOS-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## Overview

WeChat for Mac stores chat messages in SQLCipher-encrypted SQLite databases. This tool automates the entire process — from extracting encryption keys out of WeChat's memory, decrypting the databases, to presenting a full conversation viewer with CSV export.

### Key Features

- **One-click Decrypt** — Automatically extracts AES keys from a running WeChat process via macOS Mach API, then decrypts all message databases with SQLCipher.
- **Account Auto-detection** — Scans both legacy (`com.tencent.xinWeChat`) and new WeChat 4.x (`xwechat_files/wxid_*`) data directories.
- **Chat Viewer** — Dark-themed UI inspired by Telegram/Notion, with conversation list, message bubbles, date filtering, and pagination.
- **CSV Export** — Export a single conversation or all conversations at once to CSV files (UTF-8 with BOM for Excel compatibility).
- **Rich Message Types** — Displays text, images, voice, video, emoji, location, links/files, contact cards, voice/video calls, system messages, and recalls.
- **Decryption Cache** — Decrypted databases are cached locally (`~/.wx-chathistory/decrypted/`) so subsequent launches skip the decryption step.

## Architecture

```
main.py                   # Entry point — launches pywebview window
app/
├── api.py                # Python ↔ JS bridge (pywebview js_api)
├── models.py             # Data classes: Contact, Message, Conversation
├── db_reader.py          # SQLite reader for decrypted databases
├── decryptor.py          # SQLCipher decryption logic
├── key_extract.py        # Memory-scan C helper to extract AES keys
├── csv_exporter.py       # CSV export utility
└── web/
    ├── index.html        # Frontend markup
    ├── style.css         # Dark theme styles
    ├── app.js            # Frontend logic
    └── icon.png          # App icon
build_mac.sh              # PyInstaller build script for .app / .dmg
```

### How It Works

1. **Key Extraction** — A small C program is compiled at runtime and executed with admin privileges. It enumerates WeChat's virtual memory regions via `mach_vm_region` / `mach_vm_read`, searching for 96-character hex key patterns (`x'...'`).
2. **Salt Matching** — Each key's last 32 hex characters are a per-database salt. The tool matches salts against the first 16 bytes of each encrypted `.db` file.
3. **Decryption** — Matched databases are decrypted via the `sqlcipher` CLI using `PRAGMA key` and `sqlcipher_export`.
4. **Reading** — The `DatabaseReader` loads contacts, groups, and scans `Chat_*` / `Msg_*` tables across all decrypted message databases. WCDB zstd-compressed content is automatically decompressed.

## Prerequisites

| Requirement | Notes |
|---|---|
| **macOS** | Only macOS is supported (uses Mach API and WeChat Mac data paths) |
| **Python 3.10+** | For type hint syntax (`X \| None`) |
| **WeChat for Mac** | Must be installed and have been logged in at least once |
| **SIP Disabled** | System Integrity Protection must be disabled for memory key extraction |
| **sqlcipher** | Installed automatically via Homebrew, or run `brew install sqlcipher` |

### Disabling SIP

Key extraction requires reading WeChat's process memory, which is blocked by SIP:

1. Restart your Mac and hold the power button to enter Recovery Mode.
2. Open **Terminal** from the Utilities menu.
3. Run `csrutil disable` and restart.

## Getting Started

```bash
# Clone the repository
git clone git@github.com:YueGod/webchat_chat_history_export.git
cd webchat_chat_history_export

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Make sure WeChat is running, then launch
python main.py
```

## Usage

1. **Launch** — The app auto-detects WeChat accounts on startup.
2. **Decrypt** — If encrypted databases are found, click **"一键解密"** (One-click Decrypt). Enter your admin password when prompted.
3. **Browse** — Select a conversation from the sidebar. Use the date range filter to narrow results.
4. **Export** — Click **"导出 CSV"** to save the current conversation, or **"全部导出"** to export everything.

## Building a macOS App Bundle

```bash
# Build .app only
./build_mac.sh

# Build .app + .dmg installer
./build_mac.sh --dmg
```

The output will be in the `dist/` directory.

## Dependencies

| Package | Purpose |
|---|---|
| [pywebview](https://pywebview.flowrl.com/) | Native desktop window with embedded web UI |
| [zstandard](https://github.com/indygreg/python-zstandard) | Decompress WCDB zstd-compressed message content |
| [PyInstaller](https://pyinstaller.org/) | Bundle into standalone macOS `.app` |

Runtime dependency (auto-installed):

| Tool | Purpose |
|---|---|
| [sqlcipher](https://github.com/nickel-mern/sqlcipher) | Decrypt SQLCipher v4 databases |

## Limitations

- **macOS only** — The key extraction and data path logic are macOS-specific.
- **SIP must be disabled** — Required for process memory reading.
- **WeChat must be running** — Keys are extracted from the live process memory.
- **Media files not exported** — Only text content and metadata are extracted; images/videos/audio remain as placeholders.

## License

MIT
