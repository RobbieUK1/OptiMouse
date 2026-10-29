"""Regression tests for recolouring animated and transparent XCursor files.

All expected pixels use the pre-optimisation reference implementation.
Runs with standard-library Python only.
"""
import importlib.util
import random
import struct
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("optimouse",ROOT/"optimouse.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def original_tint(raw, rgb):
    data=bytearray(raw)
    if len(data)<16 or data[:4]!=b'Xcur':
        return raw
    _,_,n=struct.unpack_from('<III',data,4)
    if n>10000:
        return raw
    tr,tg,tb=rgb
    for i in range(n):
        off=16+i*12
        if off+12>len(data):
            break
        typ,_,pos=struct.unpack_from('<III',data,off)
        if typ!=0xfffd0002 or pos+36>len(data):
            continue
        header,chunk_typ,_,_,width,height,_,_,_=struct.unpack_from('<IIIIIIIII',data,pos)
        if chunk_typ!=typ or width*height>4_000_000:
            continue
        start=pos+header
        if header<36 or start+width*height*4>len(data):
            continue
        for j in range(start,start+width*height*4,4):
            b,g,r,a=data[j:j+4]
            if a==0:
                continue
            lum=(int(r)*299+int(g)*587+int(b)*114)//1000
            w=min(1,max(0,(lum-35))/220)
            data[j]=round(b*(1-w)+tb*w)
            data[j+1]=round(g*(1-w)+tg*w)
            data[j+2]=round(r*(1-w)+tr*w)
    return bytes(data)


def xcursor(frames):
    # Xcursor header: magic, header length, version, TOC count.
    head=struct.pack('<4sIII',b'Xcur',16,0x00010000,len(frames))
    toc=[]
    chunks=[]
    position=16+12*len(frames)
    for (width,height,pixels,delay) in frames:
        assert len(pixels)==width*height*4
        chunks.append(struct.pack('<9I',36,0xfffd0002,width,1,width,height,0,0,delay)+pixels)
        toc.append(struct.pack('<III',0xfffd0002,width,position))
        position+=len(chunks[-1])
    return head+b''.join(toc)+b''.join(chunks)


class RecolourTests(unittest.TestCase):
    def test_bgra_exactness_and_animation(self):
        random.seed(917)
        palette=[bytes((random.randrange(256),random.randrange(256),
                        random.randrange(256),random.choice((0,8,127,128,255))))
                 for _ in range(48)]
        palettes=[
            [b'\x00\x00\x00\xff',b'\xff\xff\xff\xff',
             b'\x80\x80\x80\x80',b'\x17\x23\x99\x00'],
            palette,
        ]
        for chosen in palettes:
            frame1=b''.join(random.choice(chosen) for _ in range(120*120))
            frame2=b''.join(random.choice(chosen) for _ in range(96*96))
            raw=xcursor([(120,120,frame1,100),(96,96,frame2,90)])
            for colour in [(113,250,204),(220,32,144),(0,0,0),(255,255,255)]:
                with self.subTest(palette=len(chosen),colour=colour):
                    assert app.tint_xcursor(raw,colour)==original_tint(raw,colour)
                    assert raw.startswith(b'Xcur')

    def test_non_cursor_pass_through(self):
        for raw in (b'',b'not a cursor',b'Xcur',b'Xcur'+b'\x00'*16):
            self.assertEqual(app.tint_xcursor(raw,(12,128,220)),original_tint(raw,(12,128,220)))

    def test_header_preserved(self):
        raw=xcursor([(4,4,b'\x64\x80\xc8\xff'*16,200)])
        output=app.tint_xcursor(raw,(50,140,200))
        self.assertEqual(output[:64],raw[:64])
        self.assertNotEqual(output[64:],raw[64:])


if __name__=="__main__":
    unittest.main()
