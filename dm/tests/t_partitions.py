"""A card's crypto decision must include every populated NCSD partition."""
import struct
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dm.tests.fixtures import build_cxi_partition
from dm.tools import ncch


class CardPartitionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.3ds"
        self.partition = build_cxi_partition()
        self.payload = bytearray(0x400 + len(self.partition) * 3)
        self.payload[0x100:0x104] = b"NCSD"
        struct.pack_into("<I", self.payload, 0x104, len(self.payload) // 512)
        # Deliberately sparse table indexes and different physical order.
        for physical, (index, flag) in enumerate(((0, 4), (7, 0), (3, 1))):
            base = 0x400 + physical * len(self.partition)
            self.payload[base:base + len(self.partition)] = self.partition
            self.payload[base + 0x18F] = flag
            struct.pack_into("<II", self.payload, 0x120 + index * 8, base // 512, len(self.partition) // 512)
        self.path.write_bytes(self.payload)

    def test_sparse_indexes_and_secondary_crypto_are_preserved(self):
        partitions = ncch.parse_card_partitions(self.path)
        self.assertEqual([partition.index for partition in partitions], [0, 3, 7])
        self.assertTrue(partitions[0].no_crypto)
        self.assertTrue(partitions[1].fixed_key)
        self.assertTrue(partitions[2].encrypted)
        self.assertFalse(partitions[2].no_crypto)
        self.assertGreater(partitions[1].base, partitions[2].base)

    def test_malformed_secondary_ncch_is_rejected(self):
        base = 0x400 + len(self.partition)
        self.payload[base + 0x100:base + 0x104] = b"BAD!"
        self.path.write_bytes(self.payload)
        with self.assertRaises(ncch.ContainerError):
            ncch.parse_card_partitions(self.path)
        with self.assertRaises(ncch.ContainerError):
            ncch.parse_card_image(self.path)

    def test_secondary_bounds_and_overlap_are_rejected(self):
        for offset, value in ((0x120 + 7 * 8, 0xFFFFFFFF), (0x120 + 7 * 8, 2),
                              (0x400 + len(self.partition) + 0x1A4, 0xFFFFFFFF)):
            with self.subTest(offset=offset, value=value):
                changed = bytearray(self.payload)
                struct.pack_into("<I", changed, offset, value)
                self.path.write_bytes(changed)
                with self.assertRaises(ncch.ContainerError):
                    ncch.parse_card_partitions(self.path)

    def test_inspection_allows_sparse_card_but_build_requires_partition_zero(self):
        self.payload[0x120:0x128] = bytes(8)
        self.path.write_bytes(self.payload)
        self.assertEqual([partition.index for partition in ncch.parse_card_partitions(self.path)], [3, 7])
        with self.assertRaises(ncch.ContainerError):
            ncch.parse_card_image(self.path)
