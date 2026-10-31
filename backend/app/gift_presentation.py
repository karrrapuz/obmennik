"""Display-only backgrounds. Never collectible attributes or financial inputs."""
import re

_FIELDS = ('centerColor', 'edgeColor', 'patternColor', 'textColor')
_PALETTES = (
    ('#b2aea7', '#88847e', '#3d382d', '#e9e7e2'),
    ('#adb070', '#6b7d54', '#39501b', '#d3e6bb'),
    ('#ca70c6', '#9662d4', '#620fb4', '#ebceff'),
    ('#44826b', '#2f6369', '#002624', '#b7e6d3'),
    ('#58b4c8', '#538bc2', '#07609b', '#cde8fd'),
    ('#e7a75a', '#c5675f', '#ad0e00', '#ffe4d7'),
    ('#da896b', '#c4654f', '#891200', '#ffd9d2'),
    ('#5c6985', '#354057', '#030a18', '#bfcce0'),
)


def decorative_presentation(collection_id):
    if (not isinstance(collection_id, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', collection_id)
            or int(collection_id) > 2**63 - 1):
        return None
    seed = 0
    for char in collection_id:
        seed = (seed * 31 + ord(char)) & 0xffffffff
    return {'kind': 'decorative', 'backdrop': dict(zip(_FIELDS, _PALETTES[seed % len(_PALETTES)]))}
