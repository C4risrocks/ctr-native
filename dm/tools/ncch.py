# Copyright (c) 2026 ctr-native contributors — MIT license.
"""NCSD / NCCH / ExeFS / SMDH container parsing, from public documentation.

Reference: https://www.3dbrew.org/wiki/NCCH · https://www.3dbrew.org/wiki/ExeFS
https://www.3dbrew.org/wiki/SMDH · https://problemkaputt.de/gbatek-3ds-files-ncch-format.htm
The ExeFS section table layout follows Citra's ncch_container.cpp (section offsets
in bytes, section data relative to the end of the 0x200-byte ExeFS header), which
is what retail files use. Nothing of any game is defined here: this module reads
headers only, on bounded ranges, so a damaged or hostile file cannot make it read
wildly (the tests in dm/tests cover the same inputs).
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

MEDIA_UNIT = 0x200
NCCH_HEADER_SIZE = 0x200
EXEFS_HEADER_SIZE = 0x200
SMDH_SIZE = 0x36C0
SMDH_TITLE_BLOCK_OFFSET = 0x8
TITLE_ENTRY_STRIDE = 0x200
SHORT_TITLE_LEN = 0x40  # u16 units per field
LONG_TITLE_LEN = 0x80
SMDH_LONG_ICON_OFFSET = 0x24C0
SMDH_LONG_ICON_BYTES = 0x1200  # 48x48 u16
SMDH_SHORT_ICON_OFFSET = 0x2040
SMDH_SHORT_ICON_BYTES = 0x480  # 24x24 u16
ICON_TILES = 8
ICON_WIDTH, ICON_HEIGHT = 48, 48

MAX_READ = 0x100_0000  # 16 MiB per single read keeps bounded ranges bounded

LANG_KEYS = ("ja", "en", "fr", "de", "it", "es", "zh-Hans", "ko", "nl", "pt", "ru", "zh-Hant")

CARD_IMAGE_SUFFIXES = {".3ds", ".3dz", ".cci"}
CIA_SUFFIX = ".cia"

# The ENCStatus flogs bit meanings for the NCCH flags byte (0x18F of the partition):
FLAG_FIXED_KEY = 0x01
FLAG_NO_MOUNT_ROMFS = 0x02
FLAG_NO_CRYPTO = 0x04
FLAG_NEW_KEY_Y = 0x20


class ContainerError(Exception):
    """A file that is not a readable, understood 3DS container."""


class EncryptedPartition(ContainerError):
    """NCCH partition needs keys to be read (boot9 / a keys file provides them)."""


@dataclass(frozen=True)
class GameFile:
    """One candidate game file on disk, plus how it was recognised."""

    path: Path
    kind: str  # "card image" | "cia" | "unknown" | "unrecognised"


@dataclass(frozen=True)
class PartitionInfo:
    """Parsed header of one NCCH partition (CXI or CFA) inside a card image."""

    index: int
    base: int  # byte offset of the partition in the file
    size: int
    magic_ok: bool
    product_code: str
    program_id: int
    content_platform: int
    flag_byte: int
    exefs_offset: int
    exefs_size: int
    romfs_offset: int
    romfs_size: int

    @property
    def fixed_key(self) -> bool:
        return bool(self.flag_byte & FLAG_FIXED_KEY)

    @property
    def no_mount_romfs(self) -> bool:
        return bool(self.flag_byte & FLAG_NO_MOUNT_ROMFS)

    @property
    def no_crypto(self) -> bool:
        return bool(self.flag_byte & FLAG_NO_CRYPTO)

    @property
    def new_key_y(self) -> bool:
        return bool(self.flag_byte & FLAG_NEW_KEY_Y)

    @property
    def encrypted(self) -> bool:
        """True when reading section data needs a derived key (survives neither FixedKey nor NoCrypto)."""
        return not (self.fixed_key or self.no_crypto)


@dataclass
class Smdh:
    """Parsed SMDH (the icon): titles per language, region lockout, flags."""

    titles: dict[int, tuple[str, str, str]] = field(default_factory=dict)
    regions: list[int] = field(default_factory=list)
    visible: bool = True
    uses_savedata: bool = False
    autosave: bool = False
    n3ds_exclusive: bool = False
    large_icon: bytes = b""
    small_icon: bytes = b""


def find_game_files(path: Path) -> Iterator[GameFile]:
    """A folder gathers its game files (card images first, CIAs after); a file yields itself.

    Quietly skip the AppleDouble files macOS writes on exFAT drives, .DS_Store, and
    folders; the caller decides what `unknown` and `unrecognised` mean (survey, skip...).
    """
    if path.is_file():
        yield classify(path)
        return
    if not path.is_dir():
        raise ContainerError(f"{path} is not a file or a folder")
    cards, cias, unknown = [], [], []
    for entry in sorted(path.iterdir(), key=lambda p: p.name):
        if entry.name.startswith("._") or entry.name == ".DS_Store" or entry.is_dir():
            continue
        if not entry.is_file():
            continue
        game_file = classify(entry)
        if game_file.kind == "card image":
            cards.append(game_file)
        elif game_file.kind == "cia":
            cias.append(game_file)
        elif entry.suffix.lower() in CARD_IMAGE_SUFFIXES | {CIA_SUFFIX}:
            unknown.append(GameFile(entry, "unrecognised"))
    yield from cards
    yield from cias
    # Documents nothing for the rest (like nxnative skips non-container files).


def classify(path: Path) -> GameFile:
    suffix = path.suffix.lower()
    if suffix == CIA_SUFFIX:
        header = _read_exact(path, 0, 4)
        kind = "cia" if header == b"\x00\x20\x20\x20" else "unrecognised"
        return GameFile(path, kind)
    if suffix in CARD_IMAGE_SUFFIXES or not suffix:
        header = _read_exact(path, 0x100, 4)
        if header == b"NCSD":
            return GameFile(path, "card image")
        if suffix in CARD_IMAGE_SUFFIXES:
            return GameFile(path, "unrecognised")
    return GameFile(path, "unknown")


def parse_card_image(path: Path) -> tuple[str, PartitionInfo, int]:
    """Parse a card image: (title id, the application NCCH (CXI) of partition 0, media size).

    Only partition 0 is parsed: retail games are executable there, and its
    decoded offsets decide every later read.
    """
    header = _read_exact(path, 0, 0x200)
    if len(header) < 0x160 or header[0x100:0x104] != b"NCSD":
        raise ContainerError(f"{path.name}: not an NCSD card image")
    media_units = struct.unpack_from("<I", header, 0x104)[0]
    part_offset, part_size = struct.unpack_from("<II", header, 0x120)
    base, size = part_offset * MEDIA_UNIT, part_size * MEDIA_UNIT
    partition = parse_ncch_header(path, base, size)
    title_id = f"{partition.program_id & 0xFFFF_FFFF_FFFF_FFFF:016x}"
    return title_id, partition, media_units


def parse_ncch_header(path: Path, base: int, size: int) -> PartitionInfo:
    header = _read_exact(path, base, NCCH_HEADER_SIZE)
    if len(header) < 0x1B8:
        raise ContainerError(f"{path.name}: truncated NCCH header")
    product_code = header[0x150:0x160].decode("ascii", errors="replace").rstrip("\x00 \t\r\n")
    return PartitionInfo(
        index=0,
        base=base,
        size=size,
        magic_ok=header[0x100:0x104] == b"NCCH",
        product_code=product_code,
        program_id=struct.unpack_from("<Q", header, 0x118)[0],
        content_platform=header[0x18C],
        flag_byte=header[0x18F],
        exefs_offset=struct.unpack_from("<I", header, 0x1A0)[0],
        exefs_size=struct.unpack_from("<I", header, 0x1A4)[0],
        romfs_offset=struct.unpack_from("<I", header, 0x1B0)[0],
        romfs_size=struct.unpack_from("<I", header, 0x1B4)[0],
    )


def read_exefrs_file(
    path: Path,
    partition: PartitionInfo,
    name: str,
    decrypt: Callable[[int, bytes], bytes] | None = None,
) -> bytes:
    """Read one file out of the ExeFS of a partition (icon, .code, banner, logo...).

    `decrypt(offset_in_partition, data)` is applied when the partition is encrypted
    and the caller provides it (decrypt.py's work; the parser stays byte-honest).
    Raises EncryptedPartition when no decryptor is available.
    """
    if not partition.magic_ok:
        raise ContainerError(f"{path.name}: partition header is not NCCH")
    if partition.encrypted and decrypt is None:
        raise EncryptedPartition(
            f"{path.name}: ExeFS is encrypted ({'FixedKey' if partition.fixed_key else 'standard crypto'})"
            " and no decryption was provided (--boot9 or a keys file)"
        )
    if partition.exefs_offset * MEDIA_UNIT + partition.exefs_size * MEDIA_UNIT > partition.size:
        raise ContainerError("ExeFS exceeds partition bounds")
    exefs_base = partition.base + partition.exefs_offset * MEDIA_UNIT
    header = _read_exact(path, exefs_base, EXEFS_HEADER_SIZE)
    if len(header) < EXEFS_HEADER_SIZE:
        raise ContainerError(f"{path.name}: truncated ExeFS header")
    if partition.encrypted:
        header = (decrypt or (lambda offset, data: data))(partition.exefs_offset * MEDIA_UNIT, header)
    for section_number in range(8):
        entry = header[section_number * 16 : (section_number + 1) * 16]
        sec_name = entry[:8].decode("ascii", errors="replace").rstrip("\x00")
        sec_offset, sec_size = struct.unpack_from("<II", entry, 8)
        if sec_name != name:
            continue
        if EXEFS_HEADER_SIZE + sec_offset + sec_size > partition.exefs_size * MEDIA_UNIT:
            raise ContainerError("ExeFS section exceeds region bounds")
        file_base = partition.exefs_offset * MEDIA_UNIT + EXEFS_HEADER_SIZE + sec_offset
        data = _read_exact(path, partition.base + file_base, sec_size)
        if len(data) < sec_size:
            raise ContainerError(f"{path.name}: truncated ExeFS section {name!r}")
        if partition.encrypted:
            data = (decrypt or (lambda offset, blob: blob))(file_base, data)
        return data
    raise ContainerError(f"{path.name}: no ExeFS section named {name!r}")


def parse_smdh(smdh: bytes) -> Smdh:
    """Parse an SMDH icon file (titles per language, regions, flags, raw icons)."""
    if len(smdh) < 4 or smdh[:4] != b"SMDH":
        raise ContainerError("not an SMDH (bad magic)")
    if len(smdh) < SMDH_SIZE:
        raise ContainerError("truncated SMDH")
    out = Smdh()
    for language in range(12):
        start = SMDH_TITLE_BLOCK_OFFSET + language * TITLE_ENTRY_STRIDE
        entry = smdh[start : start + TITLE_ENTRY_STRIDE]
        short = _utf16(entry, 0, SHORT_TITLE_LEN)
        long_title = _utf16(entry, SHORT_TITLE_LEN, SHORT_TITLE_LEN + LONG_TITLE_LEN)
        publisher = _utf16(entry, SHORT_TITLE_LEN + LONG_TITLE_LEN, TITLE_ENTRY_STRIDE // 2)
        if short or long_title or publisher:
            out.titles[language] = (short, long_title, publisher)
    region_lockout = struct.unpack_from("<I", smdh, 0x2018)[0]
    for number in range(7):
        if region_lockout & (1 << number):
            out.regions.append(number)
    flags = struct.unpack_from("<I", smdh, 0x2028)[0]
    out.visible = bool(flags & 0x0001)
    out.autosave = bool(flags & 0x0010)
    out.uses_savedata = bool(flags & 0x0080)
    out.n3ds_exclusive = bool(flags & 0x1000)
    out.large_icon = smdh[SMDH_LONG_ICON_OFFSET : SMDH_LONG_ICON_OFFSET + SMDH_LONG_ICON_BYTES]
    out.small_icon = smdh[SMDH_SHORT_ICON_OFFSET : SMDH_SHORT_ICON_OFFSET + SMDH_SHORT_ICON_BYTES]
    return out


def available_languages(smdh: Smdh) -> list[str]:
    """Languages the SMDH carries titles for, in SMDH order."""
    return [LANG_KEYS[lang] for lang in sorted(smdh.titles)]


def _morton_walk(side: int) -> Iterator[tuple[int, int]]:
    """Morton z-order walk over coordinates in [0, side) (the recursive 8x8 base per 3dbrew).

    `side` is the power of two the walk spans; callers pass the grid rounded up
    (a 6x6 icon grid walks 8x8, entries past the grid are skipped by the caller).
    """

    def unfold(index: int) -> tuple[int, int]:
        x = y = 0
        for bit in range(side.bit_length() - 1):
            x |= ((index >> (bit * 2)) & 1) << bit
            y |= ((index >> (bit * 2 + 1)) & 1) << bit
        return x, y

    return (unfold(i) for i in range(side * side))


def icon_rgba(icon: bytes, width: int = ICON_WIDTH, height: int = ICON_HEIGHT) -> list[tuple[int, int, int, int]]:
    """CTR tiled 16-bit icon data -> RGBA pixels (RGB565, the retail standard).

    Verified against retail icons (the SMDH large icon): the outer tile grid is
    row-major, and each 8x8 tile holds its pixels in Morton z-order (the layout
    Citra's game list decodes; 3dbrew's "recursive" note predates retail).
    """
    pixel_walk = list(_morton_walk(ICON_TILES))
    grid_x, grid_y = (width + ICON_TILES - 1) // ICON_TILES, (height + ICON_TILES - 1) // ICON_TILES
    pixels: list[tuple[int, int, int, int]] = [(0, 0, 0, 255)] * (width * height)
    data_index = 0
    for tile_y in range(grid_y):
        for tile_x in range(grid_x):
            if data_index + 2 * ICON_TILES * ICON_TILES > len(icon):
                break
            tile = icon[data_index : data_index + 2 * ICON_TILES * ICON_TILES]
            data_index += 2 * ICON_TILES * ICON_TILES
            for tile_pixel, (px, py) in enumerate(pixel_walk):
                raw = struct.unpack_from("<H", tile, tile_pixel * 2)[0]
                r, g, b = (raw >> 11) & 31, (raw >> 5) & 63, raw & 31
                x, y = tile_x * ICON_TILES + px, tile_y * ICON_TILES + py
                if x < width and y < height:
                    pixels[y * width + x] = (r * 255 // 31, g * 255 // 63, b * 255 // 31, 255)
    return pixels


def write_png(pixels: list[tuple[int, int, int, int]], width: int, height: int, path: Path) -> None:
    """A minimal RGBA PNG writer (zlib is standard library; no dependencies)."""
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        with_crc = len(data).to_bytes(4, "big") + tag + data
        return with_crc + zlib.crc32(tag + data).to_bytes(4, "big")

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        for (r, g, b, a) in pixels[y * width : (y + 1) * width]:
            raw += bytes((r, g, b, a))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _utf16(entry: bytes, start_u16: int, end_u16: int) -> str:
    text = entry[start_u16 * 2 : end_u16 * 2].decode("utf-16-le", errors="replace")
    return text.rstrip("\x00").rstrip()


def _read_exact(path: Path, offset: int, length: int) -> bytes:
    if length > MAX_READ:
        raise ContainerError(f"{path.name}: refusing a single read of {length:#x} bytes")
    with open(path, "rb", buffering=0) as file:
        file.seek(offset)
        return file.read(length)
