"""Synthetic regressions for the container integrity audit."""
import io
import struct
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dm.tests.fixtures import build_card_image, build_cxi_partition
from dm.tools import decrypt, ncch


class IntegrityRegressions(unittest.TestCase):
    def test_truncated_smdh_is_rejected(self):
        with self.assertRaises(ncch.ContainerError):
            ncch.parse_smdh(b"SMDH")

    def test_exefs_cannot_escape_partition(self):
        with TemporaryDirectory() as folder:
            card = build_card_image(build_cxi_partition(), Path(folder) / "test.3ds")
            payload = bytearray(card.read_bytes())
            struct.pack_into("<I", payload, 0x124, 1)
            card.write_bytes(payload)
            _, partition, _ = ncch.parse_card_image(card)
            with self.assertRaises(ncch.ContainerError):
                ncch.read_exefrs_file(card, partition, "icon")

    def test_plain_partition_uses_ncch_magic_at_correct_offset(self):
        payload = build_cxi_partition()
        output = io.BytesIO()
        with patch.object(decrypt, "engine", return_value=None):
            end = decrypt.decrypt_partition(io.BytesIO(payload), output, 0, len(payload), {}, lambda _: None)
        self.assertEqual(end, len(payload))
        self.assertEqual(output.getvalue(), payload)

    def test_all_eight_empty_partition_entries(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "empty.3ds"
            destination = Path(folder) / "copy.3ds"
            payload = bytearray(0x200)
            payload[0x100:0x104] = b"NCSD"
            source.write_bytes(payload)
            decrypt.decrypt_card_image(source, destination, decrypt.KeySource(), lambda _: None)
            self.assertEqual(destination.read_bytes(), payload)

    def test_boot9_offsets_with_synthetic_material(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic.bin"
            for size, offset in ((0x8000, 0x59D0), (0x10000, 0xD9D0)):
                payload = bytearray(size)
                payload[offset:offset + 16] = bytes(range(16))
                source.write_bytes(payload)
                self.assertEqual(decrypt.load_key_x_table(decrypt.KeySource(boot9=source)),
                                 {0x2C: bytes(range(16))})
