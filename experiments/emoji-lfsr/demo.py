"""Build a synthetic test font and verify its GSUB with system HarfBuzz.

Run: python demo.py
Requires fontTools and libharfbuzz.so.0. Output is a test font, not Noto.
"""
import ctypes as C
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent
GLYPHS = ['.notdef', 'space', 'person', 'runner', 'state0', 'state1',
          'person.light', 'person.dark', 'runner.light', 'runner.dark']


def build():
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(GLYPHS)
    fb.setupCharacterMap({32: 'space', 0x1F9D1: 'person', 0x1F3C3: 'runner'})
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in GLYPHS})
    fb.setupHorizontalMetrics({name: (1000, 0) for name in GLYPHS})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'LFSR Test', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    addOpenTypeFeatures(fb.font, str(ROOT / 'demo.fea'))
    target = ROOT / 'demo.ttf'
    fb.save(target)
    return target


class Info(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                ('codepoint', 'mask', 'cluster', 'var1', 'var2')]


def shape(path, text):
    hb = C.CDLL('libharfbuzz.so.0')
    def bind(name, result, *args):
        fn = getattr(hb, name)
        fn.restype, fn.argtypes = result, list(args)
        return fn
    ptr = C.c_void_p
    blob = bind('hb_blob_create_from_file_or_fail', ptr, C.c_char_p)(str(path).encode())
    assert blob
    face = bind('hb_face_create', ptr, ptr, C.c_uint)(blob, 0)
    font = bind('hb_font_create', ptr, ptr)(face)
    bind('hb_ot_font_set_funcs', None, ptr)(font)
    buf = bind('hb_buffer_create', ptr)()
    data = text.encode()
    bind('hb_buffer_add_utf8', None, ptr, C.c_char_p, C.c_int, C.c_uint, C.c_int)(
        buf, data, len(data), 0, len(data))
    bind('hb_buffer_guess_segment_properties', None, ptr)(buf)
    bind('hb_shape', None, ptr, ptr, ptr, C.c_uint)(font, buf, None, 0)
    size = C.c_uint()
    infos = bind('hb_buffer_get_glyph_infos', C.POINTER(Info), ptr,
                 C.POINTER(C.c_uint))(buf, C.byref(size))
    result = [GLYPHS[infos[i].codepoint] for i in range(size.value)]
    for kind, obj in [('buffer', buf), ('font', font), ('face', face), ('blob', blob)]:
        bind('hb_' + kind + '_destroy', None, ptr)(obj)
    return result


def expected(text):
    history, result = [], []
    for ch in text:
        if ch == ' ':
            history = []
            result.append('space')
            continue
        bit = history[-3] ^ history[-1] if len(history) >= 3 else 1
        history.append(bit)
        base = {'🧑': 'person', '🏃': 'runner'}[ch]
        result.append(base + ('.dark' if bit else '.light'))
    return result


if __name__ == '__main__':
    path = build()
    for text in ['🧑' * 30, '🧑🏃' * 15, '🧑🏃🧑 🏃🧑🏃🧑🏃', '🧑', '🏃🧑']:
        actual = shape(path, text)
        assert actual == expected(text), (text, actual, expected(text))
    print('PASS: repeated bases, mixed bases, boundaries, and short runs')
    print('Mixed run:', ' '.join(shape(path, '🧑🏃' * 7)))
