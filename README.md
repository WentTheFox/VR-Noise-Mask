# VR Noise Mask

A tiny pink-noise generator that plays on your VR headset's audio output to
mask idle DAC / coil whine (seen on the Valve Index when a GPU's DisplayPort
audio is idle). It runs only while your VR session does: [Envision] launches it
with the XR service and stops it when the service stops. A small Plasma widget
controls the volume.

The noise is continuous, not gated on silence, so turning it up makes the whine
progressively less audible rather than switching it off.

## Requirements

- Linux with PipeWire (uses `pactl`) — Windows device selection is implemented
  but untested
- Python 3 with `numpy` and `pyaudio` (Arch: `python-numpy python-pyaudio`)
- [Envision] to launch it; KDE Plasma 6 for the widget (optional)

## Install

```sh
./install.sh
```

This creates, for the current user only:

- `~/.local/bin/vr-noise-mask`: launcher pointing at this checkout
- `~/.local/share/applications/vr-noise-mask.desktop`: Envision XR plugin entry
- the Plasma widget (via `kpackagetool6`, if available)

Then enable **VR Noise Mask** in Envision → Preferences → Plugins and add the
widget to a panel or desktop. Move the checkout and re-run `./install.sh`.

## Usage

The widget has an on/off switch and a volume slider, and shows whether the
generator is running and playing. The same controls are available from the CLI:

```sh
vr-noise-mask get                     # config + runtime state, as JSON
vr-noise-mask set --volume 20         # 0-50
vr-noise-mask set --enabled off
vr-noise-mask set --device Valve_Index_Headset
vr-noise-mask run                     # run in the foreground (Envision does this)
```

A running generator picks up changes within about a second.

## Configuration

`~/.config/vr-noise-mask/config.json`:

| Key            | Default | Meaning                                              |
|----------------|---------|------------------------------------------------------|
| `volume_pct`   | `10`    | 0–50. A dB scale (0% silent, 100% = 0 dBFS), not linear amplitude |
| `device_match` | `index` | Case-insensitive substring of the PipeWire sink name or description |
| `enabled`      | `true`  |                                                      |

The generator waits for a sink matching `device_match` to appear (headset
powered on) and plays on it only while it exists.

## How it works

PortAudio opens PipeWire's `pulse` device, then `pactl move-sink-input` moves
the stream to the matching sink, the same as `paplay --device=`. Opening the
raw ALSA device instead would fight PipeWire for the card. The widget is plain
QML that shells out to `vr-noise-mask get` / `set`; the generator publishes its
state in `$XDG_RUNTIME_DIR/vr-noise-mask.json`.

## License

MIT

[Envision]: https://gitlab.com/gabmus/envision
