# OptiMouse for Omarchy

OptiMouse is a black-and-mint GTK application for controlling mouse-pointer appearance and shake-to-find on **Omarchy / Hyprland 0.56**.

## Install or update (single command)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/RobbieUK1/OptiMouse/main/install.sh)"
```

Close OptiMouse before updating. Launch **OptiMouse** from the Omarchy application menu after installation.

## Controls

- **Normal pointer size (16–128 px), experimental in v0.2.7:** For XCursor-based themes, OptiMouse now builds a new theme containing **actual raster frames at the selected nominal size** (not merely a size-setting request). The generator retains existing cursor shapes, animation timings, the original source frames and proportionally adjusted click hotspots. The artwork is cached and prepared in the background when moving the size slider, and is only applied when you click **Apply settings**. The raster enlargement currently uses nearest-neighbour scaling, so large images may look pixelated. Themes that contain **only hyprcursor** assets cannot yet be resized this way, and clients that provide their own cursor surfaces may ignore the requested size. **Live resizing is not yet verified on the user's desktop.** GTK3/GTK4 `settings.ini` and GSettings also receive the size, following the approach of [taxin-404's Cursor Style plugin](https://github.com/taxin-404/oma-cursor-style). OptiMouse still keeps its Omarchy toggle persistence separate from `hyprland.lua`; in Follow Theme mode the chosen size may need reapplying after a desktop theme change or new session.
- **Colour picker:** Always controls the enlarged shake pointer's outline. With **Follow Omarchy desktop cursor style** switched off, it also generates a recoloured XCursor theme for the normal pointer. In v0.2.4, clicking **Choose…** opens an explicitly parented, modal GTK colour dialog centred over OptiMouse, rather than the automatically created GTK ColorButton popup that could jump to the top-left on Hyprland. Cancel leaves the existing selection unchanged.
- **Follow Omarchy cursor style:** Attempts to select the currently installed session cursor theme rather than an OptiMouse-generated colour theme. Theme changes made later by other desktop tools are not automatically detected by the GTK app.
- **Shake to find:** Enable the switch and click Apply. The integrated Quickshell service draws a **temporary, smooth vector pointer overlay** (32–256 px) that grows with shaking, holds briefly, and shrinks. Its *outline* always follows the selected OptiMouse colour, with a contrast-aware black/white body. It uses a cursor bridge and no repeated `hyprctl setcursor` calls during animation.
- **Shake sensitivity:** Light, Medium, Hard.
- **Preview enlarged pointer:** Triggers the overlay's grow/hold/shrink animation independently of shake detection, to help determine whether the service is working.
- **Preload colour without applying (v0.2.6):** When you choose a custom colour, OptiMouse generates its cursor theme on a background thread and displays **Preparing…** then **Ready**. It does **not** call Hyprland, change the pointer or save the setting until **Apply settings** is clicked. Apply reuses the completed theme; if preparation is still running, Apply safely waits for it, avoiding duplicate generation. The existing 32-bit colour optimisation and completed-theme cache remain in place.
- **Apply feedback:** A prominent `Apply time: X.XX s` label beside the Apply button, with a breakdown for Theme, Save, Hyprland, GTK and Preview phases. This helps pinpoint slow operations without modifying Shake to Find. The application version is shown in the title. You can check the installed version with `~/.local/share/optimouse/optimouse.py --version`.

**Important:** Normal pointer size and shake overlay maximum size are *different controls*. The newly generated normal-cursor sizes are experimental and must be tested on a live Hyprland session. The shake overlay remains the proven visual enlargement solution and has not been modified.

## Integration

The installer creates:
- `~/.local/share/optimouse/optimouse.py` (GTK app)
- `~/.local/share/optimouse/cursor_resizer.py` (standard-library XCursor raster sizing)
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
