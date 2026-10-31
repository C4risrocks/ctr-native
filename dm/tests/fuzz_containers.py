"""Bounded synthetic mutation corpus; run `python -m dm.tests.fuzz_containers`.

No corpus files or external ROMs/keys are needed. Atheris users may pass
`fuzz_one` directly to their runner; the standard-library mode is deterministic.
"""
from __future__ import annotations

import argparse
from contextlib import suppress
import io
import random
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from dm.tests.fixtures import build_card_image, build_cxi_partition, build_smdh
from dm.tools import decrypt, ncch

MAX_INPUT = 128 * 1024


def fuzz_one(data: bytes) -> None:
    """Exercise parsing/decryption through public interfaces with bounded input."""
    if len(data) > MAX_INPUT:
        return
    with TemporaryDirectory(prefix="ctr-fuzz-") as directory:
        source = Path(directory) / "synthetic.3ds"
        source.write_bytes(data)
        with suppress(ncch.ContainerError):
            ncch.parse_card_partitions(source)
        try:
            _, partition, _ = ncch.parse_card_image(source)
            ncch.read_exefrs_file(source, partition, "icon")
        except ncch.ContainerError:
            pass
        with suppress(ncch.ContainerError):
            ncch.parse_smdh(data)
        with suppress(decrypt.DecryptError):
            decrypt.decrypt_card_image(source, Path(directory) / "clear.3ds", decrypt.KeySource(), lambda _: None)
        with suppress(decrypt.DecryptError):
            decrypt.decrypt_partition(io.BytesIO(data), io.BytesIO(), 0, len(data), {}, lambda _: None)


def run_mutations(iterations: int = 500, seed: int = 0) -> None:
    """Mutate valid manufactured headers plus explicit boundary cases."""
    rng = random.Random(seed)
    with TemporaryDirectory() as directory:
        card = build_card_image(build_cxi_partition(), Path(directory) / "seed.3ds").read_bytes()
    secondary = build_cxi_partition(flag_byte=0)
    mixed = bytearray(card + secondary)
    struct.pack_into("<II", mixed, 0x128, len(card) // 512, len(secondary) // 512)
    seeds = (card, bytes(mixed), build_cxi_partition(), build_smdh(), b"", b"SMDH")
    for payload in seeds:
        fuzz_one(payload)
    for offset in (0x120, 0x124, 0x400 + 0x180, 0x400 + 0x1A0, 0x400 + 0x1A4):
        payload = bytearray(card)
        struct.pack_into("<I", payload, offset, 0xFFFFFFFF)
        fuzz_one(bytes(payload))
    for _ in range(iterations):
        data = bytearray(rng.choice(seeds))
        if data:
            if rng.randrange(4) == 0:
                del data[rng.randrange(len(data)):]
            else:
                for _ in range(rng.randrange(1, 8)):
                    data[rng.randrange(len(data))] = rng.randrange(256)
        fuzz_one(bytes(data))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args()
    if not 0 <= arguments.iterations <= 100_000:
        parser.error("iterations must be between 0 and 100000")
    run_mutations(arguments.iterations, arguments.seed)
    print(f"synthetic fuzz: {arguments.iterations} mutations passed")
