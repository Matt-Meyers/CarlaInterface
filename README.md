# Carla Interface

Touchscreen PyQt6 front-end for a fixed [Carla](https://kx.studio/Applications:Carla) rack: preset buttons, keyboard split, and octave shift. It talks to Carla over OSC (`oscsend`) and sends MIDI program changes through ALSA (`aplaymidi`).

Python **3.10**, Linux. The piano-PC overlay (autostart, JACK, Carla project) lives in [`os/`](os/) and is not required to edit the app.

## Setup

System package (Linux):

```bash
sudo apt install liblo-tools alsa-utils   # oscsend, aplaymidi, arecordmidi
```

App venv (from `app/`):

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Edit [`app/main.py`](app/main.py) to change patches, categories, and Carla rack indexes. Everything else lives under `app/carla_interface/`.

## Runtime notes

- OSC: `oscsend` to `localhost:22752` (Carla’s OSC port).
- MIDI: `aplaymidi` to ALSA `Midi Through Port-0` (bridged into Carla by a2jmidid). Pigments program changes use MIDI channels 2 (main) and 3 (split); channel 1 is the keyboard.
- `app/assets/sendosc.exe` is an unused Windows leftover; the app is Linux-only.
- XFCE autostart runs [`os/home/startup_scripts/audio/carlaInterface.sh`](os/home/startup_scripts/audio/carlaInterface.sh), which starts `~/CarlaInterface/main.py` with `~/CarlaInterface/venv`. [`deploy.ps1`](deploy.ps1) copies `app/` to that path and `os/home/` onto the user home.
