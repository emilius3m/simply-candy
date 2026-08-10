# 🫧 Simply Candy

**Reverse-engineered local control system & Multi-platform Flutter App for Candy BWM 149PH7 (and Bianca / simply-Fi series) washing machines.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Flutter 3.12+](https://img.shields.io/badge/flutter-3.12+-02569B.svg)](https://flutter.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Simply Candy** enables direct local network (LAN) control, monitoring, and program selection for Candy Bianca series smart washing machines (specifically model **BWM 149PH7** and compatible variants), bypassing the Candy Cloud infrastructure during daily operation.

The project provides both a **Python CLI / REST API suite** and a **cross-platform Flutter App** (Android, iOS, Windows, macOS, Linux, Web).

---

## 📸 Screenshots & Demo

| Flutter Mobile / Desktop App | FastAPI Local Web UI |
| :---: | :---: |
| ![Flutter App Screenshot](flutter_app/screenshot.png) | *Local Web UI served at `http://localhost:8000`* |

---

## 🌟 Key Features

- 🔒 **Direct Local HTTP Control**: Communicates directly over WiFi with the washing machine via HTTP (`http-read.json`, `http-write.json`) using 16-byte XOR encrypted payloads.
- 🔑 **Automatic Key Discovery**: Multi-tier XOR key extraction and derivation with local key caching (`candy_key.cache`).
- ☁️ **Cloud Catalog Import (CIAM OAuth2)**: Secure OAuth2 + PKCE authentication flow against Candy's Salesforce Cloud to fetch official washing program definitions and option bitmasks (`OptMsk1`, `OptMsk2`).
- 🛡️ **Safety & Fail-Safe Design**:
  - `--dry-run` mode enabled by default to prevent accidental physical cycle starts during testing.
  - Parameter validation (temperature, spin speed, soil level, option masks) enforced against catalog constraints.
  - Atomic writing for `programs.json` with `.bak` restore fallback.
- 📱 **Cross-Platform Flutter Application**:
  - Subnet scanner (`/24`) for automatic local IP discovery.
  - Custom-painted realistic washer UI with animated rotating drum, glass reflections, and dynamic water level.
  - Retro neon green LCD display showing remaining cycle time.
  - Preset manager for favorite custom wash cycles.
- 🐍 **Python CLI & Web REST API**:
  - CLI for status reading, program starting, and cycle stopping (`candy_sendprogram.py`).
  - Single-file FastAPI web server (`candy_web.py`) with responsive HTML dashboard.

---

## 📐 System Architecture

```
                      [ Candy Salesforce Cloud ]
                                  ▲
                                  │ (OAuth2 CIAM / Simply-Fi REST API)
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                        Python Ecosystem                         │
 │                                                                 │
 │   [ candy_ciam.py ] ──► [ candy_cloud.py ] ──► [ catalog ]      │
 │                                                      │          │
 │   [ candy_programs.py ] ◄────────────────────────────┘          │
 │            │                                                    │
 │            ▼                                                    │
 │   [ candy_sendprogram.py ] (XOR 16-byte Cipher + Payload Gen)   │
 │         ▲             ▲                                         │
 │         │             │                                         │
 │    (CLI Engine)  [ candy_web.py ] (FastAPI Web & REST API)      │
 └─────────┼─────────────┼─────────────────────────────────────────┘
           │             │
           ▼             ▼
   [ Direct Local HTTP Protocol ] ◄─── [ Flutter Cross-Platform App ]
           │                                 (Dart Port of Core,
           │                                 Subnet Scan, Custom UI)
           ▼
[ Candy BWM 149PH7 Washing Machine (WiFi LAN @ 192.168.1.xxx) ]
```

---

## 🚀 Quick Start — Python (CLI & Web UI)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/emilius3m/simply-candy.git
cd simply-candy

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Import Program Catalog from Cloud

Run the import script once to download and normalize the official program catalog for your machine:

```bash
python candy_import_programs.py
```

> **Secure OAuth Flow**: The script opens the official Candy login page (`id.candy-home.com`) in your default browser. Your credentials are never entered into the terminal. Once logged in, copy the redirect URL (`candy://...`) and paste it into the terminal prompt.

### 3. Using the CLI

```bash
# List all imported wash programs
python candy_sendprogram.py list

# Read current live machine status over LAN
python candy_sendprogram.py status --ip 192.168.1.50

# Simulate starting a program (Dry-Run mode, safe for testing)
python candy_sendprogram.py start --program "Cotone" --temp 60 --spin 1000 --dry-run

# Start a program for real
python candy_sendprogram.py start --program "Cotone" --temp 60 --spin 1000 --no-dry-run

# Stop an active cycle
python candy_sendprogram.py stop
```

### 4. Running the Local Web UI (FastAPI)

```bash
python candy_web.py
```
Open your browser at `http://localhost:8000` to access the interactive web dashboard.

---

## 📱 Quick Start — Flutter App (`flutter_app/`)

The cross-platform Flutter mobile and desktop app is located in the `flutter_app/` directory.

### Build and Run

```bash
cd flutter_app

# Get Flutter packages
flutter pub get

# Run on Desktop (Windows / macOS / Linux) or Device / Emulator (Android / iOS)
flutter run

# Build Android APK
flutter build apk --release

# Build Windows Executable
flutter build windows
```

### App Features
1. **Status**: Live monitoring tab displaying the front washer panel, LED indicators, cycle stage, remaining time, and a **Stop Wash** button.
2. **Start**: Visual program catalog with search, parameter tuning (temperature, spin speed, soil level, extra options), and **Save as Favorite**.
3. **Settings**: Automatic LAN IP subnet scanner (`/24`), manual IP setup, and step-by-step cloud OAuth catalog import.

---

## 🔬 Protocol & Reverse Engineering Details

The Candy BWM 149PH7 washing machine communicates using unauthenticated, XOR-encrypted HTTP requests with a 16-byte fixed key.

- **Read Status**: `GET http://<ip>/http-read.json?encrypted=1`
- **Write Command**: `GET http://<ip>/http-write.json?encrypted=1&data=<hex>`
- **18-Parameter Command Format**:  
  `Write=1&StSt=1&DelVl=0&PrNm=...&PrCode=...&PrStr=...&TmpTgt=...&SLevTgt=...&SpdTgt=...&OptMsk1=...&OptMsk2=...&Lang=1&Stm=...&Dry=...&ED=0&RecipeId=0&StartCheckUp=0&DispTestOn=1`

For full reverse-engineering notes, Android APK decompilation details, and option mask specifications, see [`docs/articles/candy-bwm-149ph7-medium-it.md`](docs/articles/candy-bwm-149ph7-medium-it.md).

---

## 🧪 Testing

Run the `pytest` suite to verify program parsing, payload building, OAuth flow, and API endpoints:

```bash
pip install -r requirements-dev.txt
pytest
```

---

## 🔒 Security & Sensitive Data

- `candy_key.cache`: Contains the local device XOR key derived from your machine.
- `candy://` callback URL: Contains temporary tokens generated during OAuth login. **Do not share these tokens or cache files in public GitHub issues.**

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
