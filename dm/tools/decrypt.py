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
import os
import tempfile
import struct
from dataclasses import dataclass, field
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
    """In-memory derived group keys; never serialize or log."""

    menu_info_key: bytes = field(repr=False)
    content_key: bytes = field(repr=False)
    partition_id: int
    version: int
    region_offsets: dict[str, int]  # exheader / exefs / romfs: bytes from partition base


def load_key_x_table(source: KeySource) -> dict[int, bytes]:
    """Load retail slot 0x2C from full/protected boot9; TSV supplies other slots.

    The retail keyblob starts at 0xD860 (full) / 0x5860 (protected),
    with the shared 0x2C keyX at +0x170. No key bytes are bundled here.
    """
    table: dict[int, bytes] = {}
    if source.boot9 is not None:
        offset = {0x10000: 0xD9D0, 0x8000: 0x59D0}.get(source.boot9.stat().st_size)
        if offset is None:
            raise DecryptError("boot9 must be a full or protected-region dump")
        table[MENU_INFO_SLOT] = read_bytes(source.boot9, offset, BLOCK)
    if source.keys_file is not None:
        if source.keys_file.stat().st_size > 64 * 1024:
            raise DecryptError("keys table exceeds 64 KiB")
        try:
            rows = source.keys_file.read_text(encoding="utf-8").splitlines()
        except UnicodeError as error:
            raise DecryptError("keys table must be UTF-8 text") from error
        count = 0
        for number, raw in enumerate(rows, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                slot_text, key_text = line.split("=", 1)
                slot = int(slot_text.strip(), 16)
                key = bytes.fromhex(key_text.strip())
            except ValueError as error:
                raise DecryptError(f"keys table row {number}: expected slot=hexkey") from error
            if not 0 <= slot <= 0x3F or len(key) != BLOCK:
                raise DecryptError(f"keys table row {number}: invalid slot or key length")
            if slot in table and table[slot] != key:
                raise DecryptError(f"keys table row {number}: conflicting slot 0x{slot:02X}")
            table[slot] = key
            count += 1
        if not count:
            raise DecryptError("keys table has no slot=key rows")
    if not table:
        raise DecryptError("no key source: pass --boot9 or --keys")
    return table


def normal_key(key_x: bytes, key_y: bytes) -> bytes:
    """The bootrom hardware key generator, as Python integers (BE 128-bit wraparound)."""
    x, y = int.from_bytes(key_x, "big"), int.from_bytes(key_y, "big")
    rolled = ((x << 2) | (x >> 126)) & KEY_MASK
    mixed = ((rolled ^ y) + KEYGEN_C1) & KEY_MASK
    rotated = ((mixed >> 41) | (mixed << 87)) & KEY_MASK  # rotate right 41 bits
    return rotated.to_bytes(16, "big")


def partition_keys(ncch_header: bytes, key_x_table: dict[int, bytes]) -> PartitionKeys:
    """Derive both group keys of one NCCH from its plaintext header."""
    if len(ncch_header) != 0x200:
        raise DecryptError("truncated NCCH header")
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
    if ncch_header[0x18F] & FLAG_FIXED_KEY:
        if int.from_bytes(ncch_header[0x118:0x120], "little") & (1 << 36):
            raise DecryptError("fixed system-key partitions are not supported")
        key_x_table = {MENU_INFO_SLOT: bytes(BLOCK), content_slot: bytes(BLOCK)}
    missing = [hex(slot) for slot in {MENU_INFO_SLOT, content_slot} if slot not in key_x_table]
    if any(len(key) != BLOCK for key in key_x_table.values()):
        raise DecryptError("keyX must contain exactly 16 bytes")
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
    """Verify a complete working copy before replacing the destination."""
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise DecryptError("source and decrypted destination must be different files")
    header = read_bytes(source, 0, 0x200)
    if header[0x100:0x104] != b"NCSD":
        raise DecryptError("not an NCSD card image")
    table = struct.unpack_from("<16I", header, 0x120)
    file_size = source.stat().st_size
    partitions = sorted((table[i] * MEDIA_UNIT, table[i + 1] * MEDIA_UNIT)
                        for i in range(0, 16, 2) if table[i + 1])
    end = 0x200
    for base, size in partitions:
        if base < end or size < 0x200 or base + size > file_size:
            raise DecryptError("partition overlaps another region or exceeds the card image")
        end = base + size
    key_table = load_key_x_table(key_source) if key_source.boot9 or key_source.keys_file else {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w+b", dir=destination.parent, prefix=".decrypt-", delete=False) as writer:
            temporary = Path(writer.name)
            with source.open("rb", buffering=0) as reader:
                position = 0
                for base, size in partitions:
                    copy_range(reader, writer, position, base - position)
                    position = decrypt_partition(reader, writer, base, size, key_table, say)
                copy_range(reader, writer, position, file_size - position)
            writer.flush()
            if writer.tell() != file_size:
                raise DecryptError("decrypted copy changed the card image size")
            os.fsync(writer.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    say(f"decrypted copy: {destination.name} ({file_size:,} bytes)")
    return destination


def checked_regions(header: bytes, size: int) -> list[tuple[int, int, str]]:
    """Validate the NCCH work list before data offsets become file reads."""
    exheader_size = little(header, 0x180)
    if exheader_size not in (0, 0x400):
        raise DecryptError("unsupported extended header size")
    regions = [(0x200, 0x800 if exheader_size else 0, "exheader")]
    for offset, name in ((0x190, "plain"), (0x198, "logo"), (0x1A0, "exefs"), (0x1B0, "romfs")):
        regions.append((little(header, offset) * MEDIA_UNIT, little(header, offset + 4) * MEDIA_UNIT, name))
    regions = sorted(region for region in regions if region[1])
    end = 0x200
    for offset, length, name in regions:
        if offset < end or offset + length > size:
            raise DecryptError(f"{name} overlaps another NCCH region or exceeds partition bounds")
        if name == "exefs" and length < 0x200:
            raise DecryptError("ExeFS is shorter than its header")
        end = offset + length
    for offset, name in ((0x1A0, "ExeFS"), (0x1B0, "RomFS")):
        if little(header, offset + 8) > little(header, offset + 4):
            raise DecryptError(f"{name} superblock exceeds region bounds")
    return regions


def decrypt_partition(reader, writer, base: int, size: int,
                      key_table: dict[int, bytes], say: Callable[[str], None]) -> int:
    """Transform one partition without moving any region or padding byte."""
    if base < 0 or size < 0x200:
        raise DecryptError("invalid NCCH partition bounds")
    mark = reader.tell()
    reader.seek(0, 2)
    source_size = reader.tell()
    reader.seek(mark)
    if base + size > source_size:
        raise DecryptError("NCCH partition exceeds source bounds")
    header = read_into(reader, base, 0x200)
    if header[0x100:0x104] != b"NCCH":
        raise DecryptError(f"partition at 0x{base:08x}: not NCCH")
    content_size = little(header, 0x104) * MEDIA_UNIT
    if content_size < 0x200 or content_size > size:
        raise DecryptError("NCCH content size exceeds partition bounds")
    regions = checked_regions(header, content_size)
    flags = header[0x18F]
    if flags & FLAG_NO_CRYPTO:
        copy_range(reader, writer, base, size)
        say(f"  partition 0x{base:08x}: no-crypto plaintext, {size:,} bytes")
        return base + size
    keys = partition_keys(header, key_table)
    aes = engine()
    fixed = bool(flags & FLAG_FIXED_KEY)
    menu_key = bytes(BLOCK) if fixed else keys.menu_info_key
    content_key = bytes(BLOCK) if fixed else keys.content_key
    plain_header = bytearray(header)
    plain_header[0x18F] = flags | FLAG_NO_CRYPTO
    writer.seek(base)
    writer.write(plain_header)
    cursor = base + 0x200
    for relative, length, name in regions:
        start = base + relative
        copy_range(reader, writer, cursor, start - cursor)
        if name in ("plain", "logo"):
            copy_range(reader, writer, start, length)
        elif name == "exefs":
            counter = region_counter(keys, name)
            stream_decrypt(reader, writer, start, 0x200, menu_key, counter, aes)
            table = read_plain(writer, start, 0x200)
            files = []
            filenames = set()
            for section in range(10):
                entry = table[section * 16:(section + 1) * 16]
                filename = entry[:8].rstrip(b"\0").decode("ascii", "replace")
                offset, count = struct.unpack_from("<II", entry, 8)
                if not count:
                    continue
                if filename in filenames:
                    raise DecryptError("duplicate ExeFS section name")
                filenames.add(filename)
                if not filename or offset % BLOCK or 0x200 + offset + count > length:
                    raise DecryptError("ExeFS section has invalid alignment or bounds")
                digest_offset = 0x1E0 - section * 32
                expected_hash = table[digest_offset:digest_offset + 32]
                files.append((start + 0x200 + offset, count, filename, expected_hash))
            position = start + 0x200
            for offset, count, filename, expected_hash in sorted(files):
                if offset < position:
                    raise DecryptError("overlapping ExeFS sections")
                delta = position - start
                stream_decrypt(reader, writer, position, offset - position, menu_key,
                               ctr_at(counter, delta), aes, skip=delta % BLOCK)
                key = menu_key if filename in MENU_INFO_NAMES else content_key
                stream_decrypt(reader, writer, offset, count, key, ctr_at(counter, offset - start), aes)
                if any(expected_hash) and hash_plain(writer, offset, count) != expected_hash:
                    raise DecryptError("ExeFS file hash mismatch: wrong keys or modified container")
                position = offset + count
            delta = position - start
            stream_decrypt(reader, writer, position, start + length - position, menu_key,
                           ctr_at(counter, delta), aes, skip=delta % BLOCK)
        else:
            key = menu_key if name == "exheader" else content_key
            stream_decrypt(reader, writer, start, length, key, region_counter(keys, name), aes)
        cursor = start + length
    copy_range(reader, writer, cursor, base + size - cursor)
    for offset, hash_offset, name in ((0x1A0, 0x1C0, "ExeFS"), (0x1B0, 0x1E0, "RomFS")):
        hash_size = little(header, offset + 8) * MEDIA_UNIT
        if hash_size:
            produced = hash_plain(writer, base + little(header, offset) * MEDIA_UNIT, hash_size)
            if produced != header[hash_offset:hash_offset + 32]:
                raise DecryptError(f"{name} superblock hash mismatch: wrong keys or modified container")
    say(f"  partition 0x{base:08x}: decrypted, {size:,} bytes, superblocks checked where present")
    return base + size


def hash_plain(writer, offset: int, length: int) -> bytes:
    """Hash written bytes with a bounded read and restore the output position."""
    digest = hashlib.sha256()
    while length:
        count = min(COPY_CHUNK, length)
        digest.update(read_plain(writer, offset, count))
        offset += count
        length -= count
    return digest.digest()


def stream_decrypt(reader, writer, offset: int, length: int, key: bytes,  # type: ignore[no-untyped-def]
                   counter_at_offset: bytes, aes: KeystreamFn, skip: int = 0) -> None:
    """Decrypt [offset, offset+length); `counter_at_offset` is the counter at `offset`.

    ``skip`` selects a byte inside the initial counter block, for the
    original-key padding after an ExeFS file with an unaligned size.
    """
    if length == 0:
        return
    if offset < 0 or length < 0 or len(key) != BLOCK or not 0 <= skip < BLOCK:
        raise DecryptError("invalid encrypted range or key length")
    reader.seek(offset)
    writer.seek(offset)
    consumed = 0
    left = length
    while left > 0:
        take = min(COPY_CHUNK, left)
        chunk = reader.read(take)
        if len(chunk) < take:
            raise DecryptError("file ended inside an encrypted region")
        try:
            prefix = (skip + consumed) % BLOCK
            stream = aes(key, ctr_at(counter_at_offset, skip + consumed), take + prefix)
            keystream = stream[prefix:]
        except Exception:
            # OpenSSL exceptions carry argv, including the private key.
            raise DecryptError("AES engine failed") from None
        if len(keystream) != take:
            raise DecryptError("AES engine returned a short keystream")
        writer.write(bytes(a ^ b for a, b in zip(chunk, keystream, strict=True)))
        consumed += take
        left -= take


def copy_range(reader, writer, offset: int, length: int) -> None:  # type: ignore[no-untyped-def]
    """Copy a byte range verbatim (padding stays as the dump has it)."""
    if offset < 0 or length < 0:
        raise DecryptError("invalid plaintext range")
    reader.seek(offset)
    writer.seek(offset)
    left = length
    while left > 0:
        chunk = reader.read(min(COPY_CHUNK, left))
        if not chunk:
            raise DecryptError("file ended while copying plaintext ranges")
        writer.write(chunk)
        left -= len(chunk)


def read_plain(writer, offset: int, length: int) -> bytes:  # type: ignore[no-untyped-def]
    """Read back the written (decrypted) bytes, without moving the write pointer."""
    if offset < 0 or length < 0 or length > COPY_CHUNK:
        raise DecryptError("invalid bounded verification read")
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
    if offset < 0 or length < 0 or length > COPY_CHUNK:
        raise DecryptError("invalid bounded header read")
    with open(path, "rb", buffering=0) as file:
        file.seek(offset)
        data = file.read(length)
    if len(data) < length:
        raise DecryptError(f"{path.name}: ends at 0x{offset + len(data):x}, inside a header read")
    return data


def read_into(reader, offset: int, length: int) -> bytes:  # type: ignore[no-untyped-def]
    if offset < 0 or length < 0 or length > COPY_CHUNK:
        raise DecryptError("invalid bounded container read")
    reader.seek(offset)
    data = reader.read(length)
    if len(data) < length:
        raise DecryptError("file ends inside a container header")
    return data
