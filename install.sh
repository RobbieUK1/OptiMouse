#!/usr/bin/env bash
set -euo pipefail
BASE="https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main"
if ! command -v python3 >/dev/null || ! python3 -c 'import gi; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null; then
  echo 'Installing GTK3 Python bindings…'
  sudo pacman -S --needed python python-gobject gtk3
fi
mkdir -p "$HOME/.local/share/optimouse" "$HOME/.local/share/applications" "$HOME/.config/systemd/user" "$HOME/.config/hypr"
if [[ -f "${BASH_SOURCE[0]}" && "${BASH_SOURCE[0]}" != /dev/fd/* && -f "$(dirname "${BASH_SOURCE[0]}")/optimouse.py" ]]; then
  install -m755 "$(dirname "${BASH_SOURCE[0]}")/optimouse.py" "$HOME/.local/share/optimouse/optimouse.py"
else
  curl --fail --location --show-error --silent "$BASE/optimouse.py" -o "$HOME/.local/share/optimouse/optimouse.py"
  chmod 755 "$HOME/.local/share/optimouse/optimouse.py"
fi
cat > "$HOME/.local/share/applications/optimouse.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OptiMouse
Comment=Pointer size, colour and shake-to-find for Omarchy
Exec=$HOME/.local/share/optimouse/optimouse.py
Icon=input-mouse
Terminal=false
Categories=Settings;Accessibility;
StartupNotify=true
EOF
cat > "$HOME/.config/systemd/user/optimouse-shake.service" <<EOF
[Unit]
Description=OptiMouse shake-to-find pointer helper
After=graphical-session.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 $HOME/.local/share/optimouse/optimouse.py --shake-daemon
Restart=on-failure
RestartSec=3
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload || true
if [ -f "$HOME/.config/hypr/hyprland.conf" ]; then
  if ! grep -qF 'source = ~/.config/hypr/optimouse.conf' "$HOME/.config/hypr/hyprland.conf"; then
    printf '\n# OptiMouse settings\nsource = ~/.config/hypr/optimouse.conf\n' >> "$HOME/.config/hypr/hyprland.conf"
  fi
else
  echo 'Note: hyprland.conf not found; live Apply works, but session persistence may need manual Hyprland integration.'
fi
if [ ! -f "$HOME/.config/hypr/optimouse.conf" ]; then
  printf '# OptiMouse settings (generated when Apply is pressed)\n' > "$HOME/.config/hypr/optimouse.conf"
fi
printf '\nOptiMouse installed. Find it in the application launcher, or run:\n%s\n' "$HOME/.local/share/optimouse/optimouse.py"
