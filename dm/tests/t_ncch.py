# Copyright (c) 2026 ctr-native contributors — MIT license.
"""Parser tests on synthetic fixtures: NCSD/NCCH headers, ExeFS, SMDH, icon untile."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dm.tests.fixtures import build_card_image, build_cxi_partition, build_smdh, synthetic_icon
from dm.tools import ncch


class ToolCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class TestCardImage(ToolCase):
    def test_find_and_parse(self) -> None:
        card = build_card_image(build_cxi_partition(), self.tmp / "testgame.3ds")
        games = list(ncch.find_game_files(self.tmp))
        self.assertEqual([game.kind for game in games], ["card image"])
        title_id, partition, _ = ncch.parse_card_image(card)
        self.assertEqual(title_id, "00040000000ec300")
        self.assertTrue(partition.magic_ok)
        self.assertEqual(partition.product_code, "CTR-P-TSTM")
        self.assertTrue(partition.no_crypto)
        self.assertFalse(partition.encrypted)
        self.assertEqual(partition.exefs_offset, 6)

    def test_exefs_icon_and_smdh(self) -> None:
        icon_src = synthetic_icon(48)
        smdh = build_smdh(large_icon=icon_src)
        card = build_card_image(build_cxi_partition(smdh=smdh), self.tmp / "game.3ds")
        _, partition, _ = ncch.parse_card_image(card)
        raw = ncch.read_exefrs_file(card, partition, "icon")
        self.assertEqual(raw, smdh)
        parsed = ncch.parse_smdh(raw)
        self.assertEqual(parsed.titles[1][0], "Test Game")
        self.assertEqual(parsed.titles[1][1], "Test Game: The Long Title")
        self.assertEqual(parsed.regions, [1])
        self.assertTrue(parsed.uses_savedata)
        self.assertEqual(ncch.available_languages(parsed), ["en"])
        rgba = ncch.icon_rgba(parsed.large_icon)
        # The icon fixture stripes bands of 12 columns; checked pixels sit inside them.
        self.assertEqual(rgba[0][:3], (255, 0, 0))      # x=0,  y=0,  band 0 (the stripe itself)
        self.assertEqual(rgba[12][:3], (0, 255, 0))     # x=12, y=0,  band 1
        self.assertEqual(rgba[24][:3], (0, 0, 255))     # x=24, y=0,  band 2
        self.assertEqual(rgba[36][:3], (255, 0, 0))     # x=36, y=0,  band 3 -> cycles back to band 0
        self.assertEqual(rgba[47 * 48 + 14][:3], (0, 255, 0))  # y=47, x=14, band 1

    def test_encrypted_partition_raises_without_keys(self) -> None:
        encrypted_flag = 0x00  # no FixedKey/NoCrypto: standard crypto
        card = build_card_image(
            build_cxi_partition(flag_byte=encrypted_flag), self.tmp / "enc.3ds"
        )
        _, partition, _ = ncch.parse_card_image(card)
        self.assertTrue(partition.encrypted)
        try:
            ncch.read_exefrs_file(card, partition, "icon")
        except ncch.EncryptedPartition as error:
            self.assertIn("--boot9", str(error))
        else:
            self.fail("an encrypted ExeFS read should raise EncryptedPartition")

    def test_unknown_files_are_skipped(self) -> None:
        (self.tmp / "._metadata").write_bytes(b"junk")
        (self.tmp / ".DS_Store").write_bytes(b"junk")
        (self.tmp / "not-a-game.txt").write_bytes(b"plain text")
        self.assertEqual([f for f in ncch.find_game_files(self.tmp)], [])


if __name__ == "__main__":
    unittest.main()
