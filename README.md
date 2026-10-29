# OptiMouse

Mouse-pointer accessibility settings for **Omarchy / Hyprland**, with a black-and-mint GTK interface.

## One-line installation

Paste this command into your Omarchy terminal:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main/install.sh)"
```

Once installed, open **OptiMouse** from the application menu.

## Features

- Adjust pointer size from 16 to 128 pixels.
- Choose a custom cursor colour (based on a recoloured installed XCursor theme).
- Follow the currently active desktop cursor style.
- Enable shake-to-find, which enlarges the pointer briefly when shaken.
- Restore default settings.
- Save cursor settings and enable/disable a user-level systemd helper.

## Compatibility and limitations

Designed for Arch-based Omarchy with Hyprland and GTK3. The app applies the current theme and size using `hyprctl setcursor`. XCursor recolouring requires an installed Adwaita or another supported cursor set. Some apps may require restarting to display changes.

**Follow theme** reads the cursor style at the time you press Apply; it does not automatically track future theme changes. The shake helper uses `hyprctl cursorpos` and is experimental; behaviour can vary by Hyprland version. Where Omarchy uses a Lua-generated Hyprland configuration instead of a `hyprland.conf`, startup persistence may require additional configuration. The installer does not overwrite Lua configurations.

This is an initial release, not yet tested on a live Omarchy session.

## Manual launch

```bash
~/.local/share/optimouse/optimouse.py
```

## Uninstall

```bash
systemctl --user disable --now optimouse-shake.service
rm -f ~/.local/share/applications/optimouse.desktop ~/.config/systemd/user/optimouse-shake.service
rm -rf ~/.local/share/optimouse ~/.config/optimouse ~/.local/share/icons/OptiMouse-Custom
systemctl --user daemon-reload
```

If present, remove the OptiMouse source line from `~/.config/hypr/hyprland.conf` and optionally delete `~/.config/hypr/optimouse.conf`.
