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


def _frames(raw):
    """Return valid XCursor image frames in TOC order, or an empty list."""
    if len(raw) < 16 or raw[:4] != b'Xcur':
        return []
    header, _, count = struct.unpack_from('<III', raw, 4)
    if header != 16 or not 0 < count <= MAX_IMAGES or 16 + count * 12 > len(raw):
        return []
    frames = []
    for index in range(count):
        kind, nominal, offset = struct.unpack_from('<III', raw, 16 + index * 12)
        if kind != IMAGE_TYPE:
            continue
        if offset < 16 + 12 * count or offset + 36 > len(raw):
            return []
        (chunk_header, chunk_type, subtype, frame_version, w, h,
         xhot, yhot, delay) = struct.unpack_from('<9I', raw, offset)
        start = offset + chunk_header
        if (chunk_type != IMAGE_TYPE or subtype != nominal
                or chunk_header < 36 or frame_version != 1
                or not w or not h or w * h > MAX_PIXELS
                or xhot >= w or yhot >= h
                or start + w * h * 4 > len(raw)):
            return []
        frames.append((nominal, w, h, xhot, yhot, delay,
                       memoryview(raw)[start:start + w * h * 4]))
    return frames


def _visible_height(pixels, width, height, threshold=16):
    """Height of the drawn shape, ignoring transparent cursor margins."""
    first = height
    last = -1
    for y in range(height):
        row = y * width * 4
        for x in range(width):
            if pixels[row + x * 4 + 3] >= threshold:
                first = min(first, y)
                last = y
                break
    return max(0, last - first + 1)


def _reference_coverage(directory, desired):
    """How much of nominal cursor size the visible arrow actually occupies."""
    for name in ('left_ptr', 'default', 'arrow'):
        path = directory / name
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        frames = _frames(raw)
        if not frames:
            continue
        nominal = min({f[0] for f in frames},
                      key=lambda size: (abs(size - desired), -size))
        chosen = next(f for f in frames if f[0] == nominal)
        drawn = _visible_height(chosen[6], chosen[1], chosen[2])
        if drawn:
            # Avoid pathological image files growing unreasonably large.
            return max(0.5, min(2.0, drawn / nominal))
    return 1.0


def scale_cursor_file(raw, desired, coverage=1.0):
    """Build images whose visible arrow height tracks the slider number.

    Each generated file contains only images marked with the requested XCursor
    nominal size. Source cursor files remain untouched. Existing animation
    frames are preserved, with proportionately scaled hotspots and delays.
    """
    desired = int(desired)
    if not 8 <= desired <= 256:
        return raw
    frames = _frames(raw)
    if not frames:
        return raw
    nearest = min({f[0] for f in frames},
                  key=lambda size: (abs(size - desired), -size))
    ratio = desired / (nearest * coverage)
    new_chunks = []
    for nominal, w, h, xhot, yhot, delay, src in frames:
        if nominal != nearest:
            continue
        new_w = max(1, round(w * ratio))
        new_h = max(1, round(h * ratio))
        if (new_w * new_h > MAX_PIXELS or new_w > 2048 or new_h > 2048):
            return raw
        resized = bytearray(new_w * new_h * 4)
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
        header = struct.pack('<9I', 36, IMAGE_TYPE, desired, 1,
                             new_w, new_h, new_x, new_y, delay)
        new_chunks.append(header + bytes(resized))
    if not new_chunks:
        return raw

    count = len(new_chunks)
    position = 16 + count * 12
    toc = []
    for chunk in new_chunks:
        toc.append(struct.pack('<III', IMAGE_TYPE, desired, position))
        position += len(chunk)
    version = struct.unpack_from('<I', raw, 8)[0]
    return (struct.pack('<4sIII', b'Xcur', 16, version, count)
            + b''.join(toc) + b''.join(new_chunks))


def cursor_visible_height(theme, nominal_size, icons):
    """Measure alpha-bounded arrow height in the generated cursor artwork."""
    folder = Path(icons) / theme / 'cursors'
    for name in ('left_ptr', 'default', 'arrow'):
        path = folder / name
        if not path.is_file():
            continue
        try:
            frames = _frames(path.read_bytes())
        except OSError:
            continue
        nearest = sorted(frames, key=lambda frame:
                         (abs(frame[0] - nominal_size), -frame[0]))
        if nearest:
            frame = nearest[0]
            drawn = _visible_height(frame[6], frame[1], frame[2])
            if drawn:
                return drawn
    return None


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
    output_name = 'OptiMouse-VisualSized-' + name + '-' + str(size)
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
    coverage = _reference_coverage(source, size)
    for entry in items:
        output = destination / entry.name
        output.unlink(missing_ok=True)
        if entry.is_symlink():
            link = os.readlink(entry)
            if not os.path.isabs(link):
                output.symlink_to(link)
            else:
                output.write_bytes(scale_cursor_file(entry.resolve().read_bytes(), size, coverage))
        elif entry.is_file():
            output.write_bytes(scale_cursor_file(entry.read_bytes(), size, coverage))
    (target / 'index.theme').write_text(
        '[Icon Theme]\nName=OptiMouse Visible Sized ' + str(size) +
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
