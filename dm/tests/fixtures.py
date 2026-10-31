# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Synthetic 3DS container fixtures, built from the public format docs.

No game file ever enters the tests: this module manufactures card images
(NCSD wrapping one NCCH CXI) with chosen flags, an ExeFS carrying a
manufactured SMDH, and optionally RSA-free plaintext regions so parsers and
decryption paths exercise on honest bytes.
"""

from __future__ import annotations

import struct
from pathlib import Path

MEDIA_UNIT = 0x200
FLAG_NO_CRYPTO = 0x04
FLAG_FIXED_KEY = 0x01


def build_smdh(
    short: str = "Test Game",
    long_title: str = "Test Game: The Long Title",
    publisher: str = "TestPub",
    language: int = 1,  # English
    regions: tuple[int, ...] = (1,),  # North America
    large_icon: bytes | None = None,
) -> bytes:
    smdh = bytearray(0x36C0)
    smdh[:4] = b"SMDH"
    struct.pack_into("<H", smdh, 4, 0x0313)
    base = 8 + language * 0x200
    smdh[base : base + 0x80] = short.encode("utf-16-le").ljust(0x80, b"\x00")
    smdh[base + 0x80 : base + 0x180] = long_title.encode("utf-16-le").ljust(0x100, b"\x00")
    smdh[base + 0x180 : base + 0x200] = publisher.encode("utf-16-le").ljust(0x80, b"\x00")
    mask = 0
    for number in regions:
        mask |= 1 << number
    struct.pack_into("<I", smdh, 0x2018, mask)
    flag_value = 0x0001 | 0x0080  # visible | uses_savedata
    struct.pack_into("<I", smdh, 0x2028, flag_value)
    icon = large_icon or synthetic_icon(48)
    struct.pack_into("<H", smdh, 0x24C0, 0)  # placeholder overwritten below
    smdh[0x24C0 : 0x24C0 + 0x1200] = icon
    return bytes(smdh)


def synthetic_icon(size: int = 48, rgb_stripe: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """A tiled RGB565 icon in the 3dbrew layout, built independently of the parser:
    outer 8x8 tiles in grid z-order (8-span walk), pixels z-ordered inside each
    tile. Band colors change every 12 columns so specific pixels are checkable.
    """
    def unfold(index: int, bits: int) -> tuple[int, int]:
        x = y = 0
        for bit in range(bits):
            x |= ((index >> (bit * 2)) & 1) << bit
            y |= ((index >> (bit * 2 + 1)) & 1) << bit
        return x, y

    def color_at(x: int, y: int) -> int:
        band = (x // 12) % 3
        red, green, blue = (rgb_stripe if band == 0 else (0, 255, 0) if band == 1 else (0, 0, 255))
        return ((red >> 3) << 11) | ((green >> 2) << 5) | blue >> 3

    data = bytearray(size * size * 2)
    grid = (size + 7) // 8
    position = 0
    for ty in range(grid):          # outer tiles row-major
        for tx in range(grid):
            for inner in range(64):
                px, py = unfold(inner, 3)
                struct.pack_into("<H", data, position * 2, color_at(tx * 8 + px, ty * 8 + py))
                position += 1
    return bytes(data)


def build_cxi_partition(
    product_code: str = "CTR-P-TSTM",
    program_id: int = 0x00040000000EC300,
    smdh: bytes | None = None,
    flag_byte: int = FLAG_NO_CRYPTO,
    version: int = 2,
    partition_id: int | None = None,
    code: bytes = b"ARM11 fake code bytes",
) -> bytes:
    """One NCCH (CXI): header, ExHeader region filled, ExeFS with .code and icon."""
    smdh_bytes = smdh or build_smdh()
    exheader = bytearray(0x800)  # region identical to plaintext: NoCrypto paths mostly
    struct.pack_into("<H", exheader, 0x0, 0x3131)
    exe_header = bytearray(0x200)
    sections = [(".code", len(code)), ("icon", len(smdh_bytes))]
    # Section data for retail: offsets in bytes, relative to header end.
    data_offsets = []
    position = 0
    for _n_section, (_name, size) in enumerate(sections):
        data_offsets.append(position)
        position += size
        position = (position + 15) & ~15
    for index, (name, size) in enumerate(sections):
        struct.pack_into("<8sII", exe_header, index * 16, name.encode(), data_offsets[index], size)

    exefs_size = 0x200 + position
    exefs = bytearray(exefs_size)
    exefs[0:0x200] = exe_header
    offset = 0x200
    exefs[offset : offset + len(code)] = code
    offset += len(code)
    offset = (offset + 15) & ~15
    exefs[offset : offset + len(smdh_bytes)] = smdh_bytes

    exefs += bytes((-len(exefs)) % MEDIA_UNIT)
    # Partition layout: header (0x200) + exheader (0x800) + plain region 0x200 + exefs.
    plain = bytes(0x200)
    partition_size = 0x200 + len(exheader) + len(plain) + len(exefs_size_bytes := exefs)  # noqa: F841
    partition = bytearray(0x200)
    partition[0x100:0x104] = b"NCCH"
    part_size_units = len(exheader) + len(plain) + len(exefs) + 0x200
    struct.pack_into("<I", partition, 0x104, part_size_units // MEDIA_UNIT)
    pid = partition_id if partition_id is not None else program_id
    struct.pack_into("<Q", partition, 0x108, pid)
    struct.pack_into("<Q", partition, 0x110, pid)  # (placeholder; program id at 0x118)
    struct.pack_into("<Q", partition, 0x118, program_id)
    struct.pack_into("<H", partition, 0x112, version)
    partition[0x150:0x160] = product_code.encode().ljust(16, b"\x00")
    struct.pack_into("<I", partition, 0x180, 0x400)
    partition[0x188 + 4] = 1  # content platform CTR
    partition[0x188 + 5] = 3  # form type: executable with romfs
    partition[0x188 + 7] = flag_byte
    # Physical exheader includes its access descriptor: 0x800 bytes.
    # The header field reports 0x400; plain is at unit 5, ExeFS at unit 6.
    struct.pack_into("<I", partition, 0x190, 5)  # plain offset
    struct.pack_into("<I", partition, 0x194, len(plain) // MEDIA_UNIT)
    struct.pack_into("<I", partition, 0x1A0, 6)  # exefs offset (media units)
    struct.pack_into("<I", partition, 0x1A4, len(exefs) // MEDIA_UNIT)
    struct.pack_into("<I", partition, 0x1A8, 1)  # hash region 0x200 bytes
    body = bytearray()
    body += partition
    body += exheader
    body += plain
    body += exefs
    return bytes(body)


def build_card_image(partition: bytes | bytearray, out: Path) -> Path:
    """Wrap one CXI into an NCSD card image with the partition at media unit 2."""
    media_count = (0x400 + len(partition)) // MEDIA_UNIT
    if (0x400 + len(partition)) % MEDIA_UNIT:
        media_count += 1
    card = bytearray(media_count * MEDIA_UNIT)
    card[0x100:0x104] = b"NCSD"
    struct.pack_into("<I", card, 0x104, media_count)
    struct.pack_into("<II", card, 0x120, 2, (len(partition) + MEDIA_UNIT - 1) // MEDIA_UNIT)
    card[0x400 : 0x400 + len(partition)] = partition
    out.write_bytes(bytes(card))
    return out


def encrypted_partition(*, fixed: bool = False, shuffled: bool = False, version: int = 2) -> tuple[bytes, bytes]:
    """Manufacture encrypted NCCH and its exact expected plaintext, no game data.

    Two synthetic keyX values are 00..0F and 20..2F; keyY is 10..1F.
    Normal keys below are worked key-scrambler vectors for those test inputs.
    Encryption uses an independent AES implementation, not decrypt.py.
    """
    import hashlib

    clear = bytearray(build_cxi_partition(flag_byte=FLAG_FIXED_KEY if fixed else 0, version=version))
    clear[:16] = bytes(range(16, 32))
    clear[0x18B] = 0 if fixed else 1
    clear[0xC00 + 0x200 + 21:0xC00 + 0x200 + 32] = bytes(range(0xA0, 0xAB))
    if shuffled:
        first, second = bytes(clear[0xC00:0xC10]), bytes(clear[0xC10:0xC20])
        clear[0xC00:0xC10], clear[0xC10:0xC20] = second, first
    for index in range(10):
        offset, length = struct.unpack_from("<II", clear, 0xC00 + index * 16 + 8)
        if length:
            digest_offset = 0xC00 + 0x1E0 - index * 32
            file_data = clear[0xE00 + offset:0xE00 + offset + length]
            clear[digest_offset:digest_offset + 32] = hashlib.sha256(file_data).digest()
    clear[0x1C0:0x1E0] = hashlib.sha256(clear[0xC00:0xE00]).digest()
    romfs_offset = len(clear)
    romfs = bytes(range(256)) * 4
    clear += romfs
    struct.pack_into("<III", clear, 0x1B0, romfs_offset // MEDIA_UNIT, 2, 2)
    struct.pack_into("<I", clear, 0x104, len(clear) // MEDIA_UNIT)
    clear[0x1E0:0x200] = hashlib.sha256(romfs).digest()
    encrypted = bytearray(clear)
    menu = bytes(16) if fixed else bytes.fromhex("09c4bdce56980781e4e4ff89099d4162")
    content = bytes(16) if fixed else bytes.fromhex("4a04fe0e96d847c225253fc949dd81a2")
    partition_id = int.from_bytes(clear[0x108:0x110], "little")

    def transform(start: int, length: int, key: bytes, region_start: int, magic: int) -> None:
        counter = (partition_id << 64) | (magic << 56 if version in (0, 2) else region_start)
        counter += (start - region_start) // 16
        encrypted[start:start + length] = synthetic_aes_ctr(key, counter.to_bytes(16, "big"),
                                                           bytes(clear[start:start + length]))

    transform(0x200, 0x800, menu, 0x200, 1)
    exefs_size = int.from_bytes(clear[0x1A4:0x1A8], "little") * MEDIA_UNIT
    transform(0xC00, exefs_size, menu, 0xC00, 2)
    for index in range(10):
        entry = clear[0xC00 + index * 16:0xC10 + index * 16]
        offset, length = struct.unpack_from("<II", entry, 8)
        if length:
            key = menu if entry[:8].rstrip(b"\0") in (b"icon", b"banner") else content
            transform(0xE00 + offset, length, key, 0xC00, 2)
    transform(romfs_offset, len(romfs), content, romfs_offset, 3)
    clear[0x18F] |= FLAG_NO_CRYPTO
    return bytes(encrypted), bytes(clear)


def synthetic_aes_ctr(key: bytes, counter: bytes, payload: bytes) -> bytes:
    """AES for synthetic fixture generation, with no dependency on the code under test."""
    try:
        # Optional dependency; OpenSSL is the independent fallback below.
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # type: ignore[reportMissingImports]
    except ModuleNotFoundError:
        import subprocess

        return subprocess.run(["/usr/bin/openssl", "enc", "-aes-128-ctr", "-K", key.hex(),
                               "-iv", counter.hex()], input=payload, capture_output=True, check=True).stdout
    encryptor = Cipher(algorithms.AES(key), modes.CTR(counter)).encryptor()
    return encryptor.update(payload) + encryptor.finalize()
