#!/usr/bin/env bash
# Install OptiMouse and its Quickshell shake overlay, without changing Omarchy's main config.
set -euo pipefail
BASE="https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main"
# Use a fresh query for each install to avoid stale raw GitHub CDN responses.
CACHE_BUST="$(date +%s%N)"
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
curl -fsSL "$BASE/optimouse.py?install=$CACHE_BUST" -o "$STAGING/optimouse.py"
python3 -m py_compile "$STAGING/optimouse.py" || { echo "Python syntax check failed; old installation untouched." >&2; exit 1; }
mkdir -p "$STAGING/plugin"
for file in manifest.json Service.qml CursorArrow.qml cursor-bridge.py LICENSE; do
  curl -fsSL "$BASE/plugin/$file?install=$CACHE_BUST" -o "$STAGING/plugin/$file"
done
python3 -m py_compile "$STAGING/plugin/cursor-bridge.py"
python3 -m json.tool "$STAGING/plugin/manifest.json" >/dev/null

mkdir -p "$APP" "$HOME/.config/omarchy/plugins" "$HOME/.local/share/applications"
mkdir -p "$HOME/.config/optimouse"
if [[ ! -e "$HOME/.config/optimouse/settings.json" ]]; then
  printf '%s\n' '{"size":32,"color":"#71FACC","follow_theme":true,"shake":false,"shake_scale":2.2,"shake_max":160,"sensitivity":2.5}' > "$HOME/.config/optimouse/settings.json"
fi
# Preserve user cursor preferences; only application and plugin files are updated.
if [[ -f "$APP/optimouse.py" ]]; then
  cp -p "$APP/optimouse.py" "$APP/optimouse.py.previous"
fi
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
if command -v omarchy >/dev/null && command -v omarchy-shell >/dev/null; then
  if ! omarchy plugin validate "$APP/plugin"; then
    echo "ERROR: Omarchy rejected the shake plugin manifest." >&2
    exit 1
  fi

  # Plugin discovery is asynchronous: the shell may not know this ID yet.
  omarchy-shell shell rescanPlugins >/dev/null || true
  discovered=0
  for (( attempt=0; attempt<40; attempt++ )); do
    if omarchy plugin list --json 2>/dev/null | jq -e --arg id "$PLUGIN_ID" \
        'any(.[]; .id == $id)' >/dev/null 2>&1; then
      discovered=1
      break
    fi
    sleep 0.05
  done
  if (( ! discovered )); then
    echo "ERROR: Omarchy did not discover the shake plugin; check the plugin directory and shell logs." >&2
    exit 1
  fi

  # 'omarchy plugin enable' does not accept --yes; use the exact supported form.
  if ! omarchy plugin enable "$PLUGIN_ID"; then
    echo "ERROR: Omarchy could not enable the shake plugin." >&2
    exit 1
  fi

  if ! omarchy plugin list --json | jq -e --arg id "$PLUGIN_ID" \
      'any(.[]; .id == $id and .enabled == true)' >/dev/null; then
    echo "ERROR: Plugin was discovered but is not enabled." >&2
    exit 1
  fi

  echo "Shake plugin confirmed enabled; restarting Omarchy shell to activate the service…"
  if ! omarchy restart shell; then
    echo "Warning: shell restart failed. Run 'omarchy restart shell' manually." >&2
  fi
else
  echo "ERROR: Omarchy shell/plugin command is unavailable; shake overlay cannot start." >&2
  exit 1
fi

BRIDGE_PID="$HOME/.local/state/optimouse/bridge.pid"
active_bridge() {
  [[ -f "$BRIDGE_PID" ]] || return 1
  local pid
  pid=$(cat "$BRIDGE_PID" 2>/dev/null) || return 1
  [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q "cursor-bridge.py"
}
for i in 1 2 3 4 5; do
  if active_bridge; then
    echo "Shake overlay process running."
    break
  fi
  sleep 0.5
done
if ! active_bridge; then
  echo "Warning: shake overlay did not start. Run 'omarchy plugin list' and check the shell logs." >&2
fi

echo
echo "OptiMouse installed. Open it from your application menu."
echo "Application: $APP/optimouse.py"
echo "Shake overlay: $PLUGIN_LINK"
