"""Build an XCursor theme containing a real raster image at a requested size.

Hyprland can select a cursor image at the requested nominal size but cannot
invent missing raster sizes. This module adds a scaled image size to each cursor
file while preserving the source frames, animation timing and mouse hotspots.
It never changes a live cursor; callers invoke hyprctl only after preparation.
"""
import hashlib
import json
import os
import re
import struct
import tempfile
from pathlib import Path

IMAGE_TYPE = 0xFFFD0002
MAX_IMAGES = 4096
MAX_PIXELS = 4_000_000


def scale_cursor_file(raw, desired):
    """Append exact-size raster frames, keeping all original XCursor chunks."""
    desired = int(desired)
    if not 8 <= desired <= 256 or len(raw) < 16 or raw[:4] != b'Xcur':
        return raw
    header, version, count = struct.unpack_from('<III', raw, 4)
    if header != 16 or not 0 < count <= MAX_IMAGES or 16 + count * 12 > len(raw):
        return raw

    entries = []
    sizes = set()
    for i in range(count):
        kind, nominal, offset = struct.unpack_from('<III', raw, 16 + i * 12)
        if offset < 16 + 12 * count or offset + 16 > len(raw):
            return raw
        entries.append((kind, nominal, offset))
        if kind == IMAGE_TYPE:
            sizes.add(nominal)
    if not sizes or desired in sizes:
        return raw
    nearest = min(sizes, key=lambda n: (abs(n - desired), -n))
    if not nearest:
        return raw

    extras = []
    for kind, nominal, offset in entries:
        if kind != IMAGE_TYPE or nominal != nearest or offset + 36 > len(raw):
            continue
        (chunk_header, chunk_type, subtype, frame_version, w, h, xhot, yhot,
         delay) = struct.unpack_from('<9I', raw, offset)
        begin = offset + chunk_header
        if (chunk_type != IMAGE_TYPE or subtype != nearest
                or frame_version != 1 or chunk_header < 36 or w == 0 or h == 0
                or w * h > MAX_PIXELS or begin + w * h * 4 > len(raw)):
            continue
        ratio = desired / nearest
        new_w = max(1, round(w * ratio))
        new_h = max(1, round(h * ratio))
        if new_w * new_h > MAX_PIXELS or new_w > 2048 or new_h > 2048:
            continue
        src = memoryview(raw)[begin:begin + w * h * 4]
        resized = bytearray(new_w * new_h * 4)
        # Nearest-neighbour preserves existing alpha and pixel colours.
        # Preparation is backgrounded; no third-party image dependency.
        for y in range(new_h):
            sy = min(h - 1, (y * h) // new_h)
            dst_row = y * new_w * 4
            src_row = sy * w * 4
            for x in range(new_w):
                sx = min(w - 1, (x * w) // new_w)
                so = src_row + sx * 4
                do = dst_row + x * 4
                resized[do:do + 4] = src[so:so + 4]
        new_x = min(new_w - 1, max(0, round(xhot * ratio)))
        new_y = min(new_h - 1, max(0, round(yhot * ratio)))
        extra_header = struct.pack('<9I', 36, IMAGE_TYPE, desired, frame_version,
                                   new_w, new_h, new_x, new_y, delay)
        extras.append(extra_header + bytes(resized))
    if not extras:
        return raw

    shift = 12 * len(extras)
    toc = [struct.pack('<III', kind, nominal, offset + shift)
           for kind, nominal, offset in entries]
    position = len(raw) + shift
    for chunk in extras:
        toc.append(struct.pack('<III', IMAGE_TYPE, desired, position))
        position += len(chunk)
    return (raw[:8] + struct.pack('<II', version, count + len(extras))
            + b''.join(toc) + raw[16 + count * 12:] + b''.join(extras))


def find_xcursor_theme(name, icon_dirs):
    if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,128}', name or ''):
        return None
    for root in icon_dirs:
        directory = Path(root) / name / 'cursors'
        if directory.is_dir() and any(directory.iterdir()):
            return directory
    return None


def sized_theme(name, size, icons, icon_dirs):
    """Return (theme_name, resized). Leave unsupported hyprcursor-only themes intact."""
    size = max(16, min(128, int(size)))
    source = find_xcursor_theme(name, icon_dirs)
    if source is None:
        return name, False
    output_name = 'OptiMouse-Sized-' + name + '-' + str(size)
    target = Path(icons) / output_name
    destination = target / 'cursors'
    marker = target / '.optimouse-size-cache.json'
    items = sorted(source.iterdir(), key=lambda p: p.name)
    signature = hashlib.sha256(json.dumps([
        (p.name, p.stat().st_size, p.stat().st_mtime_ns) if p.exists()
        else (p.name, 'broken') for p in items
    ], separators=(',', ':')).encode()).hexdigest()
    try:
        metadata = json.loads(marker.read_text())
        if (metadata.get('source') == str(source)
                and metadata.get('signature') == signature
                and metadata.get('size') == size
                and (target / 'index.theme').is_file()
                and all((destination / p.name).exists() or
                        (destination / p.name).is_symlink() for p in items)):
            return output_name, True
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    destination.mkdir(parents=True, exist_ok=True)
    marker.unlink(missing_ok=True)
    for entry in items:
        output = destination / entry.name
        output.unlink(missing_ok=True)
        if entry.is_symlink():
            link = os.readlink(entry)
            if not os.path.isabs(link):
                output.symlink_to(link)
            else:
                output.write_bytes(scale_cursor_file(entry.resolve().read_bytes(), size))
        elif entry.is_file():
            output.write_bytes(scale_cursor_file(entry.read_bytes(), size))
    (target / 'index.theme').write_text(
        '[Icon Theme]\nName=OptiMouse Sized ' + str(size) +
        '\nComment=Pre-rendered cursor size from ' + name +
        '\nInherits=' + name + '\n')
    fd, tmp = tempfile.mkstemp(prefix='.optimouse-size-', dir=target)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump({'source':str(source),'size':size,'signature':signature}, handle)
            handle.write('\n')
        os.replace(tmp, marker)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return output_name, True
