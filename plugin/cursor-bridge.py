#!/usr/bin/env python3
"""I/O bridge between the Big Cursor service and Hyprland's request socket.

stdout: "<x> <y>" each time the pointer moves, and "colors <fill> <stroke>"
        after a "colors" request.
stdin:  "cursor hide" / "cursor show" lines, which hide or show the real
        compositor cursor while the service draws the enlarged one, and
        "colors", which samples the current cursor theme's arrow colors.

Hyprland closes the request socket after every reply, which makes a QML
Socket log a warning per sample; one long-lived process keeps that quiet.
If the shell exits while the cursor is hidden, the bridge shows it again.
"""

import collections
import os
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / '.local/state/optimouse'
PID_FILE = STATE_DIR / 'bridge.pid'

FAST_INTERVAL = 0.008  # while the pointer is moving
IDLE_INTERVAL = 0.05  # after it has been still for IDLE_AFTER seconds
IDLE_AFTER = 1.0

COMMANDS = {
    "cursor hide": "/eval hl.config({ cursor = { invisible = true } })",
    "cursor show": "/eval hl.config({ cursor = { invisible = false } })",
}

COLOR_COMMAND = "colors"
IMAGE_TYPE = 0xFFFD0002  # Xcursor image chunk
ARROW_NAMES = ("left_ptr", "default", "top_left_arrow", "arrow")


def socket_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    signature = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    return os.path.join(runtime, "hypr", signature, ".socket.sock")


def request(path, command):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(1)
        connection.connect(path)
        connection.sendall(command.encode())
        chunks = []
        while chunk := connection.recv(4096):
            chunks.append(chunk)
    return b"".join(chunks).decode(errors="replace")


# The cursor theme name Hyprland uses comes from the session env; the desktop
# setting covers themes applied with `hyprctl setcursor` (as Omarchy's cursor
# theming plugins do). Hyprland's own current theme cannot be queried.
def icon_dirs():
    home = os.path.expanduser("~")
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [os.path.join(data_home, "icons"), os.path.join(home, ".icons")]
    return dirs + [os.path.join(base, "icons") for base in data_dirs.split(":") if base]


def theme_name():
    for variable in ("HYPRCURSOR_THEME", "XCURSOR_THEME"):
        value = os.environ.get(variable)
        if value:
            return value
    try:
        completed = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "cursor-theme"],
            capture_output=True, text=True, timeout=2)
        name = completed.stdout.strip().strip("'")
    except (OSError, subprocess.SubprocessError):
        name = ""
    return name or "default"


def inherited_themes(name):
    for directory in icon_dirs():
        try:
            with open(os.path.join(directory, name, "index.theme"),
                      encoding="utf-8", errors="replace") as file:
                for line in file:
                    key, _, value = line.partition("=")
                    if key.strip() == "Inherits":
                        return [theme.strip() for theme in value.split(",") if theme.strip()]
        except OSError:
            continue
    return []


def cursor_file(name, seen=()):
    for directory in icon_dirs():
        for arrow in ARROW_NAMES:
            path = os.path.join(directory, name, "cursors", arrow)
            if os.path.isfile(path):
                return os.path.realpath(path)
    if name not in seen:
        for inherited in inherited_themes(name):
            path = cursor_file(inherited, seen + (name,))
            if path:
                return path
    return None


def arrow_images(path):
    with open(path, "rb") as file:
        data = file.read()
    magic, header, _, count = struct.unpack_from("<4I", data, 0)
    if magic != 0x72756358:  # "Xcur"
        return []
    images = []
    for index in range(count):
        kind, _, position = struct.unpack_from("<3I", data, header + index * 12)
        if kind != IMAGE_TYPE:
            continue
        header_size, _, _, _, width, height, _, _, _ = struct.unpack_from(
            "<9I", data, position)
        pixels = struct.unpack_from("<%dI" % (width * height), data, position + header_size)
        images.append((width * height, pixels))
    return images


# The two most common opaque colors of the arrow are its fill and its outline,
# whatever the theme's palette. Hyprcursor-only themes ship no Xcursor images,
# so they fall back to the arrow's built-in black and white.
def cursor_colors():
    path = cursor_file(theme_name())
    if not path:
        return None
    try:
        images = arrow_images(path)
    except (OSError, struct.error):
        return None
    if not images:
        return None
    _, pixels = max(images)
    counts = collections.Counter(
        (pixel >> 16 & 255, pixel >> 8 & 255, pixel & 255)
        for pixel in pixels if pixel >> 24 > 200)
    if not counts:
        return None
    colors = [color for color, _ in counts.most_common(2)]
    fill, stroke = colors[0], colors[-1]
    return "#%02x%02x%02x" % fill, "#%02x%02x%02x" % stroke


def main():
    # Give the settings application positive evidence that the overlay bridge
    # has actually started. A plugin directory existing is not proof of this.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()) + "\n")
    path = socket_path()
    stdin = sys.stdin.fileno()
    pending = b""
    hidden = False
    last_position = None
    last_move = 0.0
    next_poll = 0.0

    try:
        while True:
            now = time.monotonic()
            interval = FAST_INTERVAL if now - last_move < IDLE_AFTER else IDLE_INTERVAL
            ready, _, _ = select.select([stdin], [], [], max(0.0, next_poll - now))

            if ready:
                data = os.read(stdin, 4096)
                if not data:
                    return  # The shell went away.
                pending += data
                *lines, pending = pending.split(b"\n")
                commands = [line.decode(errors="replace").strip() for line in lines]
                commands = [command for command in commands
                            if command in COMMANDS or command == COLOR_COMMAND]
                for command in commands:
                    if command == COLOR_COMMAND:
                        colors = cursor_colors()
                        if colors:
                            print(COLOR_COMMAND, *colors, flush=True)
                    else:
                        try:
                            request(path, COMMANDS[command])
                            hidden = command == "cursor hide"
                        except OSError:
                            pass
                continue

            next_poll = now + interval
            try:
                x, y = (int(value) for value in request(path, "/cursorpos").split(","))
            except (OSError, ValueError):
                continue

            if (x, y) != last_position:
                last_position = (x, y)
                last_move = now
                print(x, y, flush=True)
    finally:
        if hidden:
            try:
                request(path, COMMANDS["cursor show"])
            except OSError:
                pass
        try:
            if PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
