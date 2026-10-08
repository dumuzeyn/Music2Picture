"""Verify both engines, actual editable controls and notices inside the EXE."""
import argparse
import types

from PyInstaller.archive.readers import CArchiveReader
import pefile


def strings(code):
    if isinstance(code,types.CodeType):
        yield code.co_name
        yield from code.co_names
        for item in code.co_consts:
            yield from strings(item)
    elif isinstance(code,str):
        yield code
    elif isinstance(code,(tuple,list)):
        for item in code:
            yield from strings(item)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe')
    args=parser.parse_args()
    archive=CArchiveReader(args.exe)
    embedded=archive.open_embedded_archive('PYZ.pyz')
    assert {'music2picture_v1.core','music2picture_v1.renderer','music2picture_v2.renderer',
            'm2p_controls','m2p_selftest','m2p_id3'} <= set(embedded.toc)
    controls=set(strings(embedded.extract('m2p_controls')))
    assert {'M2Pv1','M2Pv2','sunset','ocean','neon','forest','mono','custom','2.1.0'} <= controls
    classic=set(strings(embedded.extract('music2picture_v1.core')))
    assert 'remove_classic_pixel_grain' in classic
    modern=set(strings(embedded.extract('music2picture_v2.renderer')))
    assert {'contour-character-v5','composition','palette_positions'} <= modern
    names={name.replace('\\','/') for name in archive.toc}
    for path in ('licenses/python/LICENSE.txt','licenses/numpy/LICENSE.txt','licenses/pillow/LICENSE.txt',
                 'licenses/tk/license.terms','licenses/pyinstaller/COPYING.txt'):
        assert path in names,path
    assert not any(name.endswith('ffmpeg.exe') for name in names)
    with pefile.PE(args.exe) as executable:
        assert executable.FILE_HEADER.Machine==0x8664,'Not an x64 build'
        assert executable.OPTIONAL_HEADER.Subsystem==2,'Not a GUI build'
    print('Verified x64 GUI, both engines, editable palettes, cleanup and license notices.')


if __name__=='__main__':
    main()
