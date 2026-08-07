# Fwitter

Fwitter is a desktop social application built with Python and PySide6. It supports user accounts, posts, images,
animated images (e.g. GIF, WEBP), likes, comments, profiles, and direct messages. Firebase provides authentication and
Firestore database, while Supabase handles media storage and server-side edge functions.
The application supports compilation via Nuitka.

## Setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux or macOS, install from `requirements_linux.txt` instead.

## Run

```powershell
python main_window.py
```

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```
