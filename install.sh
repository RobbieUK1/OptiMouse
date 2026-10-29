#!/usr/bin/env bash
# Install OptiMouse and its Quickshell shake overlay, without changing Omarchy's main config.
set -euo pipefail
BASE="https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main"
APP="$HOME/.local/share/optimouse"
PLUGIN_ID="io.github.robbieuk1.optimouse-shake"
PLUGIN_LINK="$HOME/.config/omarchy/plugins/$PLUGIN_ID"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

command -v curl >/dev/null || { echo "Missing curl" >&2; exit 1; }
command -v hyprctl >/dev/null || { echo "Hyprland is required" >&2; exit 1; }
if ! command -v python3 >/dev/null || ! python3 -c 'import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null; then
  echo 'Installing Python GTK3 bindings…'
  sudo pacman -S --needed python python-gobject gtk3
fi

echo "Downloading OptiMouse and shake overlay…"
curl -fsSL "$BASE/optimouse.py" -o "$STAGING/optimouse.py"
python3 -m py_compile "$STAGING/optimouse.py" || { echo "Python syntax check failed; old installation untouched." >&2; exit 1; }
mkdir -p "$STAGING/plugin"
for file in manifest.json Service.qml CursorArrow.qml cursor-bridge.py LICENSE; do
  curl -fsSL "$BASE/plugin/$file" -o "$STAGING/plugin/$file"
done
python3 -m py_compile "$STAGING/plugin/cursor-bridge.py"
python3 -m json.tool "$STAGING/plugin/manifest.json" >/dev/null

mkdir -p "$APP" "$HOME/.config/omarchy/plugins" "$HOME/.local/share/applications"
# Preserve user cursor preferences; only application and plugin files are updated.
install -m755 "$STAGING/optimouse.py" "$APP/optimouse.py"
mkdir -p "$APP/plugin"
for file in manifest.json Service.qml CursorArrow.qml LICENSE; do
  install -m644 "$STAGING/plugin/$file" "$APP/plugin/$file"
done
install -m755 "$STAGING/plugin/cursor-bridge.py" "$APP/plugin/cursor-bridge.py"

cat > "$HOME/.local/share/applications/optimouse.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OptiMouse
Comment=Pointer colour, size and shake to find for Omarchy
Exec=$APP/optimouse.py
Icon=input-mouse
Terminal=false
Categories=Settings;Accessibility;
StartupNotify=true
EOF

# Disable the discontinued polling helper, which cannot draw the pointer on 0.56.
if command -v systemctl >/dev/null; then
  systemctl --user disable --now optimouse-shake.service >/dev/null 2>&1 || true
fi

if [[ ! -e "$PLUGIN_LINK" && ! -L "$PLUGIN_LINK" ]]; then
  ln -s "$APP/plugin" "$PLUGIN_LINK"
elif [[ -L "$PLUGIN_LINK" && "$(readlink "$PLUGIN_LINK")" == "$APP/plugin" ]]; then
  :
else
  echo "Warning: $PLUGIN_LINK exists and points elsewhere. Shake overlay not replaced." >&2
fi

if command -v omarchy-shell >/dev/null; then
  omarchy-shell shell rescanPlugins || echo "Warning: shell plugin rescan failed." >&2
fi
if command -v omarchy >/dev/null; then
  omarchy plugin enable "$PLUGIN_ID" || echo "Warning: shake overlay could not be enabled; the settings app is installed." >&2
else
  echo "Warning: Omarchy plugin command unavailable; shake overlay needs to be enabled manually." >&2
fi

echo
echo "OptiMouse installed. Open it from your application menu."
echo "Application: $APP/optimouse.py"
echo "Shake overlay: $PLUGIN_LINK"
