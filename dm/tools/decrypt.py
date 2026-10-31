# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Card-image and NCCH decryption, from public documentation only.

Key material never enters this repository: keys come from your own `boot9`
dump (the bootrom keyX table) or a TSV keys file on your machine, exactly like
nxnative uses `-k prod.keys`. FixedKey applications (ncchflag[7] bit 0) use
the documented all-zero application key (a public debug constant), so most
card games decrypt with no secrets at all.

The product is the community-standard "decrypted" container: the layout copies
byte for byte, every partition's encrypted regions come out plaintext (ExHeader
region, the ExeFS files by their own group, the RomFS), and the copy's NCCH
headers carry NoCrypto — what the HLE host reads happily.

Output is verified: Nintendo's ExeFS/RomFS superblock hashes are signed over
the *cleartext*, so a correct decryption reproduces both hashes; a wrong key
derivation stops the build instead of producing garbage that would only fail
later inside the game.

References (facts reimplemented here, no copied code):
  https://www.3dbrew.org/wiki/NCCH  (groups, CTR schemes, slot selection)
  https://www.3dbrew.org/wiki/AES   (hardware key generator + C1)
  https://problemkaputt.de/gbatek-3ds-files-ncch-format.htm
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from .ncch import MEDIA_UNIT

# (((KeyX ROL 2) XOR KeyY) + C1) ROR 41 — the bootrom's key generator.
KEYGEN_C1 = int.from_bytes(bytes.fromhex("1FF9E9AAC5FE0408024591DC5D52768A"), "big")

# ncchflag[3] -> the AES keyslot the content group (.code/.firm, whole RomFS);
# the menu-info group (ExHeader, ExeFS header, icon, banner) always uses 0x2C.
SLOT_BY_CRYPTO_METHOD = {0x00: 0x2C, 0x01: 0x25, 0x0A: 0x18, 0x0B: 0x1B}
MENU_INFO_SLOT = 0x2C
MENU_INFO_NAMES = frozenset({"icon", "banner"})
FLAG_NO_CRYPTO = 0x04
FLAG_FIXED_KEY = 0x01

KEY_MASK = (1 << 128) - 1
BLOCK = 0x10
COPY_CHUNK = 0x10_0000  # 1 MiB

KeystreamFn = Callable[[bytes, bytes, int], bytes]


class DecryptError(Exception):
    """Keys unavailable, a rare unsupported crypto variant, or verification failed."""


def engine() -> KeystreamFn:
    """AES-128 keystream: the `cryptography` wheel if present, else openssl CLI."""
    global _engine_cache
    if _engine_cache is not None:
        return _engine_cache
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # type: ignore

        def keystream(key: bytes, counter: bytes, length: int) -> bytes:
            decryptor = Cipher(algorithms.AES(key), modes.CTR(counter)).decryptor()
            return decryptor.update(b"\x00" * length) + decryptor.finalize()

    except ModuleNotFoundError:
        import subprocess

        def keystream(key: bytes, counter: bytes, length: int) -> bytes:
            result = subprocess.run(
                ["/usr/bin/openssl", "enc", "-d", "-aes-128-ctr", "-K", key.hex(), "-iv", counter.hex()],
                input=b"\x00" * length, capture_output=True, check=True,
            )
            return result.stdout[:length]

        try:
            keystream(bytes(16), bytes(16), 16)
        except (OSError, subprocess.SubprocessError) as error:
            raise DecryptError(f"no AES engine available (pip install cryptography): {error}") from error

    _engine_cache = keystream
    return keystream


_engine_cache: KeystreamFn | None = None


@dataclass(frozen=True)
class KeySource:
    """Your own console keys, brought as paths (never committed, never bundled)."""

    boot9: Path | None = None
    keys_file: Path | None = None


@dataclass(frozen=True)
class PartitionKeys:
    """Derived group keys of one NCCH partition; nothing here is secret-relevant."""

    menu_info_key: bytes
    content_key: bytes
    partition_id: int
    version: int
    region_offsets: dict[str, int]  # exheader / exefs / romfs: bytes from partition base


def load_key_x_table(source: KeySource) -> dict[int, bytes]:
    """Bootrom keyX entries (slots 0x2C..0x2F) from a boot9 dump, or a `slot=hex` TSV."""
    if source.keys_file and source.keys_file.exists():
        table: dict[int, bytes] = {}
        for number, raw in enumerate(source.keys_file.read_text().splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            slot_text, _, key_text = line.partition("=")
            try:
                slot, key = int(slot_text.strip(), 16), bytes.fromhex(key_text.replace(" ", ""))
            except ValueError as error:
                raise DecryptError(f"{source.keys_file}:{number}: {error}") from error
            if not 0x0 <= slot <= 0x3F or len(key) != 16:
                raise DecryptError(f"{source.keys_file}:{number}: bad slot or key length")
            table[slot] = key
        if not table:
            raise DecryptError(f"{source.keys_file}: no slot=key rows found")
        return table
    if source.boot9 and source.boot9.exists():
        offset = {0x10000: 0xD9D0, 0x8000: 0x59D0}.get(source.boot9.stat().st_size)
        if offset is None:
            raise DecryptError("boot9 must be a full or protected-region dump")
        data = read_bytes(source.boot9, offset, 16)
        # 0x88D8..0x88F7: keyX for the bootrom slots 0x2C..0x2F (3dbrew key-init order).
        return {0x2C: data}
    raise DecryptError("no key source: pass --boot9 or --keys (keys never live in this repo)")


def normal_key(key_x: bytes, key_y: bytes) -> bytes:
    """The bootrom hardware key generator, as Python integers (BE 128-bit wraparound)."""
    x, y = int.from_bytes(key_x, "big"), int.from_bytes(key_y, "big")
    rolled = ((x << 2) | (x >> 126)) & KEY_MASK
    mixed = ((rolled ^ y) + KEYGEN_C1) & KEY_MASK
    rotated = ((mixed >> 41) | (mixed << 87)) & KEY_MASK  # rotate right 41 bits
    return rotated.to_bytes(16, "big")


def partition_keys(ncch_header: bytes, key_x_table: dict[int, bytes]) -> PartitionKeys:
    """Derive both group keys of one NCCH from its plaintext header."""
    if ncch_header[0x100:0x104] != b"NCCH":
        raise DecryptError("not an NCCH header")
    version = int.from_bytes(ncch_header[0x112:0x114], "little")
    crypto_method = ncch_header[0x188 + 3]
    content_slot = SLOT_BY_CRYPTO_METHOD.get(crypto_method)
    if content_slot is None:
        raise DecryptError(f"unknown NCCH crypto method 0x{crypto_method:02X} (ncchflag[3])")
    if ncch_header[0x188 + 7] & 0x20:
        # 9.6+ seeded crypto needs a per-title seed from a ticket/seed-db: rare on
        # cards, never free — tell the user instead of producing garbage.
        raise DecryptError(
            "this partition uses the seeded 9.6 crypto (new keyY):"
            " use a decrypted dump (the usual) — seed support is not included"
        )
    missing = [hex(slot) for slot in {MENU_INFO_SLOT, content_slot} if slot not in key_x_table]
    if missing:
        raise DecryptError(f"boot9/keys table has no keyX for slot(s) {missing}")
    key_y = ncch_header[:0x10]  # 3dbrew/NCCH: keyY = first 0x10 bytes of the signature
    return PartitionKeys(
        menu_info_key=normal_key(key_x_table[MENU_INFO_SLOT], key_y),
        content_key=normal_key(key_x_table[content_slot], key_y),
        partition_id=int.from_bytes(ncch_header[0x108:0x110], "little"),
        version=version,
        region_offsets={
            "exheader": 0x200,
            "exefs": int.from_bytes(ncch_header[0x1A0:0x1A4], "little") * MEDIA_UNIT,
            "romfs": int.from_bytes(ncch_header[0x1B0:0x1B4], "little") * MEDIA_UNIT,
        },
    )


def region_counter(keys: PartitionKeys, region: str) -> bytes:
    """Initial 16-byte counter of a region (both the 0/2 and the 1 scheme)."""
    if keys.version in (0, 2):
        magic = {"exheader": 1, "exefs": 2, "romfs": 3}[region]
        counter = (keys.partition_id << 64) | (magic << 56)
    elif keys.version == 1:
        counter = (keys.partition_id << 64) | (keys.region_offsets.get(region, 0) & 0xFFFFFFFF)
    else:
        raise DecryptError(f"unsupported NCCH version {keys.version}")
    return (counter & KEY_MASK).to_bytes(16, "big")


def ctr_at(initial: bytes, offset_in_region: int) -> bytes:
    """The counter `offset_in_region` bytes deep in the region (AES blocks of 16)."""
    value = (int.from_bytes(initial, "big") + offset_in_region // BLOCK) & KEY_MASK
    return value.to_bytes(16, "big")


def decrypt_card_image(source: Path, destination: Path, key_source: KeySource,
                       say: Callable[[str], None] = print) -> Path:
    """Decrypt an NCSD card image into `destination`; the original stays untouched."""
    table = struct.unpack_from("<16I", read_bytes(source, 0, 0x200), 0x120)
    key_table = load_key_x_table(key_source) if key_source.boot9 or key_source.keys_file else {}
    file_size = source.stat().st_size
    position = 0
    with open(source, "rb", buffering=0) as reader, open(destination, "w+b", buffering=0) as writer:
        for entry in range(8):
            base = table[entry * 2] * MEDIA_UNIT
            size = table[entry * 2 + 1] * MEDIA_UNIT
            if not size:
                continue
            if base > position:
                copy_range(reader, writer, position, base - position)
            position = decrypt_partition(reader, writer, base, size, key_table, say)
        if file_size > position:
            copy_range(reader, writer, position, file_size - position)
    say(f"decrypted copy: {destination.name} ({destination.stat().st_size:,} bytes)")
    return destination


def decrypt_partition(reader, writer, base: int, size: int,  # type: ignore[no-untyped-def]
                      key_table: dict[int, bytes], say: Callable[[str], None]) -> int:
    """One NCCH: header copy with NoCrypto, every encrypted region plaintexted.

    The work list is the file's own order (header 0x200, exheader region, ExeFS
    files per section table, RomFS); padding gaps between regions are copied
    unchanged, keeping the container byte-identical apart from the decryption.
    """
    aes = engine()
    header = read_into(reader, base, 0x200)
    if header[0x100:0x104] != b"NCCH":
        raise DecryptError(f"partition at 0x{base:08x}: not NCCH")
    flags = header[0x18F]
    no_crypto = bool(flags & FLAG_NO_CRYPTO)
    fixed_key = bool(flags & FLAG_FIXED_KEY)
    exheader_size = little(header, 0x180)
    plain_off = little(header, 0x190) * MEDIA_UNIT
    plain_size = little(header, 0x194) * MEDIA_UNIT
    exofs_off = little(header, 0x1A0) * MEDIA_UNIT
    exofs_size = little(header, 0x1A4) * MEDIA_UNIT
    exofs_hash_size = little(header, 0x1A8) * MEDIA_UNIT
    romfs_off = little(header, 0x1B0) * MEDIA_UNIT
    romfs_size = little(header, 0x1B4) * MEDIA_UNIT
    romfs_hash_size = little(header, 0x1B8) * MEDIA_UNIT
    part_end = base + size

    plain_header = bytearray(header)
    plain_header[0x18F] = (flags | FLAG_NO_CRYPTO) & 0xFF
    writer.seek(base)
    writer.write(bytes(plain_header))

    cursor = base + 0x200
    if no_crypto:
        copy_range(reader, writer, cursor, part_end - cursor)
        say(f"  partition 0x{base:08x}: no-crypto plaintext, {size:,} bytes")
        return part_end

    keys = partition_keys(header, {MENU_INFO_SLOT: bytes(16)} if fixed_key else key_table)
    # FixedKey partitions encrypt with the documented zero application key.
    menu_key = bytes(16) if fixed_key else keys.menu_info_key
    content_key = bytes(16) if fixed_key else keys.content_key

    # 1. extended header region (menu info; includes the access descriptor).
    if exheader_size:
        stream_decrypt(reader, writer, cursor, exheader_size, menu_key,
                       region_counter(keys, "exheader"), aes)
        cursor += exheader_size
    # 2. plain region (SDK tags) and the 5.0+ logo region: both plaintext in
    # the source, so they pass through unchanged in this loop.
    if plain_off and plain_size:
        end = base + plain_off + plain_size
        if end > cursor:
            copy_range(reader, writer, cursor, end - cursor)
            cursor = end
    # 3. ExeFS: the header decrypts as menu-info; each file by its group, with
    # counters continuing the region's own counter by file offset (3dbrew).
    if exofs_off and exofs_size:
        exofs_start = base + exofs_off
        if exofs_start > cursor:
            copy_range(reader, writer, cursor, exofs_start - cursor)
        exofs_counter = region_counter(keys, "exefs")
        cursor = exofs_start
        stream_decrypt(reader, writer, cursor, 0x200, menu_key, exofs_counter, aes)
        cursor += 0x200
        section_table = read_plain(writer, exofs_start, 0x200)
        for section in range(8):
            entry = section_table[section * 16 : section * 16 + 16]
            name = entry[:8].rstrip(b"\x00").decode("ascii", "replace")
            file_offset = int.from_bytes(entry[8:12], "little")
            file_size = int.from_bytes(entry[12:16], "little")
            if not name or not file_size:
                continue
            file_key = menu_key if name in MENU_INFO_NAMES else content_key
            data_start = exofs_start + 0x200 + file_offset
            if data_start > cursor:
                copy_range(reader, writer, cursor, data_start - cursor)
            file_counter = ctr_at(exofs_counter, 0x200 + file_offset)  # the ExeFS-start CTR + file bytes
            stream_decrypt(reader, writer, data_start, file_size, file_key, file_counter, aes)
            cursor = data_start + file_size
        exofs_end = exofs_start + exofs_size
        if exofs_end > cursor:
            copy_range(reader, writer, cursor, exofs_end - cursor)
            cursor = exofs_end
        if exofs_hash_size:
            produced = hashlib.sha256(read_plain(writer, exofs_start, exofs_hash_size)).digest()
            if produced != bytes(header[0x1C0:0x1E0]):
                raise DecryptError(
                    f"partition 0x{base:08x}: ExeFS superblock hash mismatch — wrong keys"
                    " (boot9 of a different console?) or a modified container"
                )
    # 4. RomFS: one contiguous content-group region.
    if romfs_off and romfs_size:
        romfs_start = base + romfs_off
        if romfs_start > cursor:
            copy_range(reader, writer, cursor, romfs_start - cursor)
        stream_decrypt(reader, writer, romfs_start, romfs_size, content_key,
                       region_counter(keys, "romfs"), aes)
        cursor = romfs_start + romfs_size
        if romfs_hash_size:
            produced = hashlib.sha256(read_plain(writer, romfs_start, romfs_hash_size)).digest()
            if produced != bytes(header[0x1E0:0x200]):
                raise DecryptError(
                    f"partition 0x{base:08x}: RomFS superblock hash mismatch"
                    " — wrong content keys, or a seeded 9.6+ partition"
                )
    # 5. anything after the last known region (rare) copies verbatim.
    if part_end > cursor:
        copy_range(reader, writer, cursor, part_end - cursor)
    say(f"  partition 0x{base:08x}: {'fixed key' if fixed_key else 'derived keys'},"
        f" {size:,} bytes, superblock {'verified' if (exofs_hash_size or romfs_hash_size) else 'not checked'}")
    return part_end


def stream_decrypt(reader, writer, offset: int, length: int, key: bytes,  # type: ignore[no-untyped-def]
                   counter_at_offset: bytes, aes: KeystreamFn) -> None:
    """Decrypt [offset, offset+length); `counter_at_offset` is the counter at `offset`.

    Data offsets the caller passes are always AES-block aligned here (the
    regions the container supplies are media-unit aligned, ExeFS files are
    CTR-aligned per 3dbrew), so the counter moves one block per 16 bytes.
    """
    if length == 0:
        return
    reader.seek(offset)
    blocks = 0
    left = length
    while left > 0:
        take = min(COPY_CHUNK, left)
        chunk = reader.read(take)
        if len(chunk) < take:
            raise DecryptError("file ended inside an encrypted region")
        keystream = aes(key, ctr_at(counter_at_offset, blocks * BLOCK), take)
        writer.write(bytes(a ^ b for a, b in zip(chunk, keystream, strict=True)))
        blocks += take // BLOCK
        left -= take


def copy_range(reader, writer, offset: int, length: int) -> None:  # type: ignore[no-untyped-def]
    """Copy a byte range verbatim (padding stays as the dump has it)."""
    reader.seek(offset)
    left = length
    while left > 0:
        chunk = reader.read(min(COPY_CHUNK, left))
        if not chunk:
            raise DecryptError("file ended while copying plaintext ranges")
        writer.write(chunk)
        left -= len(chunk)


def read_plain(writer, offset: int, length: int) -> bytes:  # type: ignore[no-untyped-def]
    """Read back the written (decrypted) bytes, without moving the write pointer."""
    mark = writer.tell()
    writer.flush()
    writer.seek(offset)
    data = writer.read(length)
    writer.seek(mark)
    if len(data) < length:
        raise DecryptError("decrypted build ended while verifying a superblock")
    return data


def aligned16(length: int) -> int:
    """ExeFS files sit on 16-byte boundaries (their data counters are CTR-aligned)."""
    return (length + 15) & ~15


def little(header: bytes, offset: int) -> int:
    return int.from_bytes(header[offset : offset + 4], "little")


def read_bytes(path: Path, offset: int, length: int) -> bytes:
    with open(path, "rb", buffering=0) as file:
        file.seek(offset)
        data = file.read(length)
    if len(data) < length:
        raise DecryptError(f"{path.name}: ends at 0x{offset + len(data):x}, inside a header read")
    return data


def read_into(reader, offset: int, length: int) -> bytes:  # type: ignore[no-untyped-def]
    reader.seek(offset)
    data = reader.read(length)
    if len(data) < length:
        raise DecryptError("file ends inside a container header")
    return data
