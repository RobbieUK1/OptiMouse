# OptiMouse for Omarchy

OptiMouse is a black-and-mint GTK application for controlling mouse-pointer appearance and shake-to-find on **Omarchy / Hyprland 0.56**.

## Install or update (single command)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main/install.sh)"
```

Close OptiMouse before updating. Launch **OptiMouse** from the Omarchy application menu after installation.

## Controls

- **Normal pointer size (16–128 px):** Applies Hyprland's cursor size; the visible dimensions of a normal cursor may still be limited by the installed XCursor/Hyprcursor theme and any application's own cursor. After Apply, OptiMouse requests the existing Shake Preview animation through its running Quickshell service, since that is the only refresh path confirmed to redraw the new cursor immediately on the target machine. A short enlargement animation will play after applying settings; it doesn't move the pointer between monitors.
- **Colour picker:** Always controls the enlarged shake pointer's outline. With **Follow Omarchy desktop cursor style** switched off, it also generates a recoloured XCursor theme for the normal pointer.
- **Follow Omarchy cursor style:** Attempts to select the currently installed session cursor theme rather than an OptiMouse-generated colour theme. Theme changes made later by other desktop tools are not automatically detected by the GTK app.
- **Shake to find:** Enable the switch and click Apply. The integrated Quickshell service draws a **temporary, smooth vector pointer overlay** (32–256 px) that grows with shaking, holds briefly, and shrinks. Its *outline* always follows the selected OptiMouse colour, with a contrast-aware black/white body. It uses a cursor bridge and no repeated `hyprctl setcursor` calls during animation.
- **Shake sensitivity:** Light, Medium, Hard.
- **Preview enlarged pointer:** Triggers the overlay's grow/hold/shrink animation independently of shake detection, to help determine whether the service is working.
- **Apply feedback:** In-window progress and results. No modal success dialogue.

**Important:** Normal pointer size and shake overlay maximum size are *different controls*. The overlay provides reliable visual enlargement even where the native cursor theme cannot provide a large raster arrow.

## Integration

The installer creates:
- `~/.local/share/optimouse/optimouse.py` (GTK app)
- `~/.local/share/optimouse/plugin/` (Quickshell shake overlay)
- `~/.config/omarchy/plugins/io.github.robbieuk1.optimouse-shake` (plugin symlink)
- `~/.local/share/applications/optimouse.desktop` (application menu entry)
- `~/.config/optimouse/settings.json` (settings; preserved across upgrades)

Note: OptiMouse no longer issues a separate hide/show pair from the GTK app to refresh the normal cursor, because that approach did not resolve the delayed colour change. Instead Apply sends the same `preview_token` request as the confirmed-working Preview button. If the overlay is unavailable, Apply still saves normal cursor settings; the user can retry Preview later.

The cursor persistence file is `~/.local/state/omarchy/toggles/hypr/zz-optimouse.lua`, following the approach used by [oxhenri.mouse](https://github.com/Dev-Herni/oxhenri.mouse). It doesn't edit Omarchy's main Hyprland config or Omarchroma's files.

The old `optimouse-shake.service` polling helper is disabled by the installer. The new plugin receives pointer positions over a Hyprland Unix socket and draws the overlay through Quickshell.

If another mouse-settings plugin applies different cursor overrides after OptiMouse, the latest setting may take precedence. Omarchroma chiefly synchronizes application colour schemes and doesn't appear to set cursor size itself.

## Troubleshooting

```bash
~/.local/share/optimouse/optimouse.py --diagnose
omarchy plugin list
```

If Preview does not animate, first check that `io.github.robbieuk1.optimouse-shake` is enabled. Depending on shell version, the Quickshell service may need a shell restart:

```bash
omarchy restart shell
```

## Verification

A GitHub Actions workflow checks Python syntax, installer syntax and plugin manifest/wiring. The overlay and cursor appearance still require a live Omarchy desktop test.

## Credits

The Quickshell overlay files are adapted from [Gabriel Rocha's Omarchy Big Cursor plugin](https://github.com/gabrielforster/omarchy-big-cursor), licensed MIT. The adapted service, bridge and vector cursor retain its MIT licence in `plugin/LICENSE`.

The shake algorithm was also compared with [Big Cursor for Windows](https://github.com/RobbieUK1/big-cursor-windows), which itself ports the original Omarchy behaviour.

The cursor persistence approach was informed by [oxhenri.mouse](https://github.com/Dev-Herni/oxhenri.mouse), MIT licensed.

## Upgrade recovery

Before replacing an existing app, the installer saves a copy as `optimouse.py.previous` when that file exists. If an update fails, restore it with:

```bash
cp ~/.local/share/optimouse/optimouse.py.previous ~/.local/share/optimouse/optimouse.py
```
