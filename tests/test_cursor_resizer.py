"""Tests for real raster cursor sizes, hotspots, animations and caching."""
import struct
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
import importlib.util

spec=importlib.util.spec_from_file_location(
    "cursor_resizer",Path(__file__).resolve().parents[1]/"cursor_resizer.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def cursor(nominal, width=3, height=4, hotspot=(1,2), delay=80):
    pixels=bytes([23,47,85,255])*width*height
    return (struct.pack('<4sIII',b'Xcur',16,0x10000,1)
            +struct.pack('<III',mod.IMAGE_TYPE,nominal,28)
            +struct.pack('<9I',36,mod.IMAGE_TYPE,nominal,1,width,height,
                         hotspot[0],hotspot[1],delay)+pixels)


def entries(raw):
    n=struct.unpack_from('<I',raw,12)[0]
    return [struct.unpack_from('<III',raw,16+12*i) for i in range(n)]


class ResizeTests(unittest.TestCase):
    def test_generates_true_nominal_size_scaled_hotspot_and_pixels(self):
        original=cursor(24)
        scaled=mod.scale_cursor_file(original,96)
        self.assertEqual(len(entries(scaled)),2)
        kind,size,position=entries(scaled)[1]
        self.assertEqual((kind,size),(mod.IMAGE_TYPE,96))
        head=struct.unpack_from('<9I',scaled,position)
        self.assertEqual(head,(36,mod.IMAGE_TYPE,96,1,12,16,4,8,80))
        self.assertEqual(scaled[position+36:position+40],bytes([23,47,85,255]))
        self.assertEqual(scaled[position+36:],bytes([23,47,85,255])*12*16)
        # Original frames are preserved byte-for-byte except their TOC shift.
        self.assertEqual(scaled[40:40+len(original)-28],original[28:])

    def test_preserves_animation_frames(self):
        a=cursor(32)
        # two animation chunks in one original cursor
        frame1=a[28:]
        frame2=bytearray(frame1)
        struct.pack_into('<I',frame2,32,160)
        original=(struct.pack('<4sIII',b'Xcur',16,0x10000,2)
                  +struct.pack('<III',mod.IMAGE_TYPE,32,40)
                  +struct.pack('<III',mod.IMAGE_TYPE,32,40+len(frame1))
                  +frame1+frame2)
        result=mod.scale_cursor_file(original,128)
        self.assertEqual(len(entries(result)),4)
        self.assertEqual([x[1] for x in entries(result)],[32,32,128,128])
        self.assertEqual([struct.unpack_from('<I',result,pos+32)[0]
                          for _,_,pos in entries(result)[2:]],[80,160])

    def test_reuses_cached_size_theme_and_relative_aliases(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"source"/"Fancy"/"cursors"
            src.mkdir(parents=True)
            (src/"left_ptr").write_bytes(cursor(24))
            (src/"default").symlink_to("left_ptr")
            icons=root/"icons"
            name,generated=mod.sized_theme("Fancy",96,icons,(root/"source",))
            self.assertTrue(generated)
            self.assertEqual(name,"OptiMouse-Sized-Fancy-96")
            target=icons/name/"cursors"
            self.assertEqual(len(entries((target/"left_ptr").read_bytes())),2)
            self.assertTrue((target/"default").is_symlink())
            t=(target/"left_ptr").stat().st_mtime_ns
            name2,generated2=mod.sized_theme("Fancy",96,icons,(root/"source",))
            self.assertEqual((name2,generated2),(name,True))
            self.assertEqual((target/"left_ptr").stat().st_mtime_ns,t)
            (src/"left_ptr").write_bytes(cursor(48))
            mod.sized_theme("Fancy",96,icons,(root/"source",))
            sizes=[entry[1] for entry in entries((target/"left_ptr").read_bytes())]
            self.assertEqual(sizes,[48,96])

    def test_hyprcursor_only_theme_is_left_alone(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(mod.sized_theme("HyprOnly",96,Path(tmp)/"icons",(tmp,)),
                             ("HyprOnly",False))

    def test_non_cursor_and_existing_size_unchanged(self):
        self.assertEqual(mod.scale_cursor_file(b"bad",96),b"bad")
        raw=cursor(96)
        self.assertEqual(mod.scale_cursor_file(raw,96),raw)


if __name__=="__main__":
    unittest.main()
