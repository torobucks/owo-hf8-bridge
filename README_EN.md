---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 56ee4d762339c717a466c7eb939f0e32_5f076272c9db11f18533525400638852
    ReservedCode1: jCohyGuBZGAkMax3xfct3pgCuO5dbUmT0guNsNtNdrEV1nNQgL0KmUSdXJ9rYDX65aI4VFk8emn5QrAul2R4/Us3iimsGuvDzd2gqCsMOD6eK6Fnp2SiY1yaG6b3PcJkVVTjEKJSIzjW8UmaxiELShCgSbDIYnF9jZbgmZamnRd/dIDd50A30/ESQms=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 56ee4d762339c717a466c7eb939f0e32_5f076272c9db11f18533525400638852
    ReservedCode2: jCohyGuBZGAkMax3xfct3pgCuO5dbUmT0guNsNtNdrEV1nNQgL0KmUSdXJ9rYDX65aI4VFk8emn5QrAul2R4/Us3iimsGuvDzd2gqCsMOD6eK6Fnp2SiY1yaG6b3PcJkVVTjEKJSIzjW8UmaxiELShCgSbDIYnF9jZbgmZamnRd/dIDd50A30/ESQms=
---

# OWO -> HF8 Bridge

Convert **OWO haptic vest** game feedback into **Next Level Racing HF8** seat vibration. Games that only support OWO can drive the HF8 seat motors without any game modification.

This project listens for OWO SENSATION text packets over UDP, parses the 10 contact-point intensities, remaps them to the HF8's 8 vibration motors, and sends commands over a USB serial port. An **event-driven strategy** is built in to fix the classic problems of "muddy background vibration" and "impact without punch".

---

## Features

- Zero intrusion: no game modification, no OWO official driver required — just listen on UDP 54020
- Dual-device ready: HF8 seat via USB serial (default COM4 @ 115200 8N1.5)
- Event-driven output: delta trigger, sustained hold, impact full-blast, exponential decay, idle zeroing
- Plug & play: Windows single-file executable `owo_to_hf8.exe` — no Python needed
- Fully tunable CLI: deadzone, event threshold, hold threshold, decay, scale, etc.

---

## How It Works

### 1. OWO UDP 54020 Text Protocol

Games / OWO skins send text packets over UDP to port `54020`. Two kinds of interactions matter:

**Handshake / heartbeat**:
- On receiving `ping` text -> reply `okay`
- On receiving text containing `*auth*` -> reply `pong`

**SENSATION packet**:

```
{id}*SENSATION*{speed},{dir},{intensity},0,0,0,|{c%p,...}*{tail}
```

- `speed` / `dir` / `intensity`: header fields — speed, direction, overall intensity (0-100)
- `c%p,...`: contact list, where `c` is the contact number (0-9) and `p` is the intensity percentage (0-100)
- Example: `12345*SENSATION*80,90,70,0,0,0,|0%100,1%100,6%60*0`

The bridge parses contact intensities, converts them through the mapping table, and drives the HF8.

### 2. HF8 Serial Protocol (115200 8N1.5)

The HF8 receives commands over a virtual serial port with **115200 baud, 8 data bits, no parity, 1.5 stop bits**:

| Command | Description |
|---|---|
| `P` (CR) | Query status; HF8 replies `E<scale>,A<mode>` |
| `M<M><I>` (CR) | Set motor `M` (0-7) intensity `I` (0-255); no separator, terminated by CR |

On startup the bridge sends `P` to probe and reads the response to confirm the seat is alive.

### 3. Contact -> Motor Mapping

The 10 OWO contacts (0-9) map to the 8 HF8 motors (M0-M7):

| OWO Contact | Location | HF8 Motor | Location |
|---|---|---|---|
| 0 | Right Chest | M6 | Right Shoulder |
| 1 | Left Chest | M7 | Left Shoulder |
| 2 | Right Abdomen | M0 | Right Thigh |
| 3 | Left Abdomen | M1 | Left Thigh |
| 6 | Right Back | M4 | Right Back |
| 7 | Left Back | M5 | Left Back |
| 8 | Right Waist | M2 | Right Hip (seat) |
| 9 | Left Waist | M3 | Left Hip (seat) |

> Contacts 4 (right arm) and 5 (left arm) have no corresponding motors and are ignored by default.

---

## Event-Driven Output Strategy

Core idea: **no drive for stable background, full intensity for sudden events, exponential decay for afterglow**.

1. **Delta trigger** (`--event-rise 20`): an event fires when a contact's intensity **rises above this threshold** since the last packet, driving at full strength. A crash jumps intensity from 40 to 100 (rise = 60), always triggering; stable background rises near 0, so it stays quiet.
2. **Sustained hold** (`--hold-int 60`): contacts persistently above this threshold keep driving — preserves continuous sensations like high-speed bumps.
3. **Impact full-blast**: contacts at 80 or above drive at full strength for a hard "thud" on impact.
4. **Exponential decay** (`--decay 0.8`): after an event, old values decay by 0.8 per packet — about 1 second of natural afterglow, no muddiness.
5. **Idle zeroing** (`--idle-timeout 2.0`): if no SENSATION arrives for this many seconds (game paused / exited), all motors are zeroed.

---

## Installation & Usage

### Option 1: Use the prebuilt exe (recommended, no Python)

Download `owo_to_hf8.exe` and run from PowerShell / CMD:

```powershell
.\owo_to_hf8.exe
```

Defaults work out of the box: UDP listen `0.0.0.0:54020`, serial `COM4 @ 115200`. Press `Ctrl+C` to exit.

### Option 2: Run from source

Requires Python 3.8+:

```bash
pip install -r requirements.txt
python owo_to_hf8.py
```

### Command-Line Options

| Option | Default | Description |
|---|---|---|
| `--com` | `COM4` | HF8 serial port |
| `--baud` | `115200` | Serial baud rate |
| `--bind` | `0.0.0.0` | UDP bind address |
| `--port` | `54020` | UDP listen port (OWO default send port) |
| `--log` | `owo_to_hf8.log` | Log file path |
| `--scale` | `2.55` | Multiplier from contact intensity 0-100 to HF8 0-255 (2.55 = full range) |
| `--min-intensity` | `25` | Deadzone (%), contacts below this are not driven |
| `--event-rise` | `20` | Event delta threshold (%), rise above this drives at full strength |
| `--hold-int` | `60` | Hold threshold (%), contacts persistently above this keep driving |
| `--decay` | `0.8` | Decay factor, old values multiplied by this each packet after events |
| `--idle-timeout` | `2.0` | Idle zero seconds, all motors zeroed after this much silence |

Common examples:

```powershell
# Specify serial port and UDP port
.\owo_to_hf8.exe --com COM7 --port 54020

# Lower deadzone to feel light vibrations
.\owo_to_hf8.exe --min-intensity 10 --scale 2.0

# Snappier impacts: higher event threshold, faster decay
.\owo_to_hf8.exe --event-rise 30 --decay 0.7
```

### Quick Start

1. Connect the HF8 seat via USB. Note the COM port shown in Device Manager (defaults to COM4; override with `--com`).
2. Start the bridge: `.\owo_to_hf8.exe` (it sends `P` on startup and logs the seat's response).
3. Launch a game with OWO haptics enabled (OWO Skin, or a game/skin plugin that supports OWO).
4. Watch the `#SENSATION` log lines to confirm packets and intensities, then sit in the seat.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `SerialException` / no port on startup | HF8 not connected or wrong COM | Confirm the COM number in Device Manager; pass `--com`; check the USB cable |
| `P响应=b''` / `P response=b''` in log | Port is open but seat not answering | Power the seat, ensure drivers work, restart the bridge |
| No packets at all | OWO haptics disabled in game / wrong UDP port | Enable OWO output in game; confirm port 54020; check firewall |
| Data flows but seat stays silent | No mapped contacts hit / below deadzone | Watch `contacts` in the log; lower `--min-intensity`, raise `--scale` |
| Seat vibrates constantly (muddy) | Persistent background, slow decay | Raise `--event-rise`, lower `--decay` |
| Impacts lack punch | Event threshold too high or scale too low | Lower `--event-rise`, raise `--scale` up to 2.55 |
| Seat keeps vibrating after game exit | Data stopped but idle-zero not triggered | Confirm `--idle-timeout` (default 2 s); exit with `Ctrl+C` |

---

## Project Layout

```
owo-hf8-bridge/
├── owo_to_hf8.py      # Python source (all CLI options)
├── owo_to_hf8.exe     # Windows single-file executable (PyInstaller, pyserial bundled)
├── requirements.txt   # Python dependencies
├── README.md          # Chinese README
└── README_EN.md       # English README
```

### Build the exe from source

```bash
pip install pyinstaller pyserial
pyinstaller --onefile --name owo_to_hf8 --hidden-import serial \
    --hidden-import serial.tools.list_ports owo_to_hf8.py
```

---

## Disclaimer

- This is a personal open-source hobby project. It is not affiliated with or endorsed by OWO or Next Level Racing.
- Use at your own risk. Do not use vibration feedback while driving or during any dangerous activity.
- Prolonged high-frequency vibration may cause discomfort; use moderately and stop immediately if you feel unwell.
- For legal, personal entertainment use only. Not for any illegal or non-compliant purpose.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
*（内容由AI生成，仅供参考）*
