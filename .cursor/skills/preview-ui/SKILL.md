---
name: preview-ui
description: >-
  Grabs a PNG of the PyQt6 kiosk on Windows for visual check. Use after changing
  UI, widgets, palettes, stylesheet.css, or any user-visible layout. Never
  QT_QPA_PLATFORM=offscreen; never browser tools.
---

# Preview UI

This is a PyQt6 kiosk, not a browser app. After UI or CSS changes, screenshot and **Read the PNG**. Do not skip.

## Steps

1. Use `app/.venv` (Python 3.10 + `requirements.txt`). Create if missing, from `app/`:

   `py -3.10 -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

2. Never set `QT_QPA_PLATFORM=offscreen`. Fonts tofu or garble. Leave the default Windows Qt plugin.

3. Run the grabber with the venv interpreter (do not copy it into `app/`):

   `app/.venv/Scripts/python.exe .cursor/skills/preview-ui/scripts/grab.py`

4. Read `%TEMP%\carla_interface_preview.png` with the Read tool.

5. `oscsend` / `aplaymidi` / `arecordmidi` already no-op on failure — Carla is not required.

Human launch from `app/`: `.\.venv\Scripts\python.exe main.py`. Ctrl+C quits.
