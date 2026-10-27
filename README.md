# dsh-mint-budgie

Mint Budgie is a desktop-only pet for DeepSeek Harness (dsh). It floats above
other windows, shows the current project and activity only while the agent is
working, and does not render a second pet inside the dsh window.

English | [简体中文](README.zh.md)

## Features

- Drag the pet across every monitor on the Windows virtual desktop.
- Single-click or double-click to play the supplied head-tilt pose.
- Double-click restores the task bubble and opens or focuses dsh.
- Right-click for settings or to hide the pet.
- Size and opacity support sliders, numeric input and reset; both persist.
- The Codex-style task bubble stays fixed at 284x65 and scrolls long activity
  text horizontally. Idle shows no bubble and no "idle" label.
- Torso and feet stay on one baseline across animation frames, so gestures do
  not make the bird jump in size.

## Status mapping

| Source signal | Pet row | Label |
| --- | --- | --- |
| any agent is `running` or the session has an open turn | `running` | Running |
| `approval/request` open | `waiting` | Waiting |
| `agent/error` within 4 s | `failed` | Failed |
| otherwise | `idle` | no bubble |

`Agent.status` itself is only `idle | running`; the waiting and failed rows come
from the two transient Host events above.

## Architecture

The dsh Host writes `desktop/state.json`; `desktop/pet-window.pyw` polls it and
renders the desktop window with tkinter + Pillow. The Host may start the pet,
but the pet process survives a Host restart. `desktop/setup-startup.ps1` can
also install a login shortcut that launches the pet independently.

The process uses a per-monitor DPI-aware context so mixed-scale monitors keep
consistent sprite and window coordinates. The pet reads
`desktop/settings.json`; the right-click settings panel writes back to it.

The packaged `desktop/mint-budgie.exe` is used first, so Windows users do not
need Python. If the executable is unavailable, Pillow and tkinter are required
and Python is resolved from `DSH_PET_PYTHON`, then `pyw.exe`, `pythonw.exe`,
`py.exe`, and `python.exe` on `PATH`.

## Install

From the DSH plugin market, search for `dsh-mint-budgie` and install it, then
restart dsh. Or install the public npm package:

```powershell
dsh plugin --profile desktop add dsh-mint-budgie
```

Python dependencies:

```powershell
py -m pip install Pillow
```

Windows is currently the only supported platform.

## Files

- `index.js` - Host state polling, persistence and desktop-process bridge
- `client.js` - compatibility shim; intentionally registers no in-window pet
- `desktop/pet-window.pyw` - standalone desktop overlay
- `assets/spritesheet.png` - working/status sheet read by the desktop overlay
- `assets/poses/head-tilt_<frame>.png` - aligned click gesture frames

## Disabling

Remove `dsh-mint-budgie` from `dsh.profile.bundles` in the active profile's
`package.json`, then restart dsh.
