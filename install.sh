#!/bin/sh
# Installs the launcher, the Envision plugin entry and the Plasma widget for
# the current user. Safe to re-run.
set -eu

repo=$(cd "$(dirname "$0")" && pwd)
bin="$HOME/.local/bin/vr-noise-mask"
desktop="$HOME/.local/share/applications/vr-noise-mask.desktop"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"

cat > "$bin" <<EOF
#!/bin/sh
PYTHONPATH="$repo\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m vr_noise_mask "\$@"
EOF
chmod +x "$bin"

cat > "$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VR Noise Mask
Comment=Masks headset DAC whine with pink noise
Exec=$bin run
Icon=$repo/vr_noise_mask/assets/icon.svg
Terminal=false
NoDisplay=true
Categories=Utility;
X-XR-Plugin=true
X-XR-Plugin-Exec=$bin run
X-XR-Plugin-Comment=Pink-noise masking for the headset audio output
EOF

if command -v kpackagetool6 >/dev/null; then
    kpackagetool6 -t Plasma/Applet -u "$repo/plasmoid" 2>/dev/null \
        || kpackagetool6 -t Plasma/Applet -i "$repo/plasmoid"
else
    echo "kpackagetool6 not found; skipping the Plasma widget" >&2
fi

echo "Installed. Enable \"VR Noise Mask\" in Envision > Preferences > Plugins,"
echo "then add the \"VR Noise Mask\" widget to a panel or the desktop."
