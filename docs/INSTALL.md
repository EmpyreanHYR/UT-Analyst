# UT-Analyst Installation

## Requirements

- Python 3.10 or newer
- PyQt5, PyQtGraph, NumPy, SciPy
- SQLite is included with Python

## Development Installation

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python main.py
```

The first launch creates a local administrator account. Passwords are stored with
PBKDF2-HMAC-SHA256 and are never written in plain text.

## Data Directory

Runtime data is stored under `data/`:

- `data/ut_analyst.db`: users, sessions, defects, reports, and audit events
- `data/sessions/<session-id>/frames_*.npz`: compressed waveform chunks

Back up the complete `data/` directory before upgrading or moving the
application.

## Build

```powershell
python -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

The packaged application is written to `dist/UT-Analyst/`.
