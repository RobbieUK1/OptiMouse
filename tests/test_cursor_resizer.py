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
        self.assertEqual(len(entries(scaled)),1)
        kind,size,position=entries(scaled)[0]
        self.assertEqual((kind,size),(mod.IMAGE_TYPE,96))
        head=struct.unpack_from('<9I',scaled,position)
        self.assertEqual(head,(36,mod.IMAGE_TYPE,96,1,12,16,4,8,80))
        self.assertEqual(scaled[position+36:position+40],bytes([23,47,85,255]))
        self.assertEqual(scaled[position+36:],bytes([23,47,85,255])*12*16)
        # The generated theme contains only its requested nominal size;
        # the original source file remains unchanged.
        self.assertEqual(original,cursor(24))

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
        self.assertEqual(len(entries(result)),2)
        self.assertEqual([x[1] for x in entries(result)],[128,128])
        self.assertEqual([struct.unpack_from('<I',result,pos+32)[0]
                          for _,_,pos in entries(result)],[80,160])

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
            self.assertEqual(name,"OptiMouse-VisualSized-Fancy-96")
            target=icons/name/"cursors"
            self.assertEqual(len(entries((target/"left_ptr").read_bytes())),1)
            self.assertTrue((target/"default").is_symlink())
            t=(target/"left_ptr").stat().st_mtime_ns
            name2,generated2=mod.sized_theme("Fancy",96,icons,(root/"source",))
            self.assertEqual((name2,generated2),(name,True))
            self.assertEqual((target/"left_ptr").stat().st_mtime_ns,t)
            (src/"left_ptr").write_bytes(cursor(48))
            mod.sized_theme("Fancy",96,icons,(root/"source",))
            sizes=[entry[1] for entry in entries((target/"left_ptr").read_bytes())]
            self.assertEqual(sizes,[96])

    def test_visible_arrow_height_matches_requested_size(self):
        # A 24px nominal frame whose visible image covers only 20 rows.
        # Nominal dimensions and actual drawn height are different.
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"source"/"Fancy"/"cursors"
            src.mkdir(parents=True)
            buf=bytearray(24*24*4)
            for y in range(2,22):
                for x in range(4,20):
                    offset=(y*24+x)*4
                    buf[offset:offset+4]=bytes((80,120,170,255))
            raw=(struct.pack('<4sIII',b'Xcur',16,0x10000,1)
                 +struct.pack('<III',mod.IMAGE_TYPE,24,28)
                 +struct.pack('<9I',36,mod.IMAGE_TYPE,24,1,
                              24,24,5,3,72)+bytes(buf))
            (src/"left_ptr").write_bytes(raw)
            icons=root/"icons"
            for desired in (24,32,64,96,128):
                name,generated=mod.sized_theme("Fancy",desired,icons,
                                                (root/"source",))
                self.assertTrue(generated)
                height=mod.cursor_visible_height(name,desired,icons)
                self.assertIsNotNone(height)
                self.assertLessEqual(abs(height-desired),2,
                                     f"requested {desired} but got visible {height}")
                result=(icons/name/"cursors"/"left_ptr").read_bytes()
                self.assertEqual([t[1] for t in entries(result)],[desired])
                _,_,offset=entries(result)[0]
                _,_,_,_,w,h,xhot,yhot,_=struct.unpack_from('<9I',result,offset)
                self.assertLess(xhot,w)
                self.assertLess(yhot,h)
            self.assertEqual((src/"left_ptr").read_bytes(),raw)

    def test_hyprcursor_only_theme_is_left_alone(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(mod.sized_theme("HyprOnly",96,Path(tmp)/"icons",(tmp,)),
                             ("HyprOnly",False))

    def test_non_cursor_and_existing_size_unchanged(self):
        self.assertEqual(mod.scale_cursor_file(b"bad",96),b"bad")
        raw=cursor(96)
        self.assertEqual([e[1] for e in entries(mod.scale_cursor_file(raw,96))],[96])


if __name__=="__main__":
    unittest.main()
