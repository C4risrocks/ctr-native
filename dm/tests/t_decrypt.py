"""End-to-end decryption regressions using manufactured containers and keys."""
import builtins
import io
import struct
import subprocess
import traceback
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dm.tests.fixtures import build_card_image, build_cxi_partition, encrypted_partition
from dm.tools import decrypt, ncch


class DecryptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.keys = self.root / "synthetic.tsv"
        self.keys.write_text(f"2c={bytes(range(16)).hex()}\n25={bytes(range(32, 48)).hex()}\n")
        self.source = self.root / "synthetic.3ds"
        self.output = self.root / "clear.3ds"

    def test_standard_fixed_shuffled_and_counter_versions(self):
        for fixed, shuffled, version in ((False, False, 0), (False, True, 1), (False, True, 2),
                                         (True, False, 2)):
            with self.subTest(fixed=fixed, shuffled=shuffled, version=version):
                encrypted, clear = encrypted_partition(fixed=fixed, shuffled=shuffled, version=version)
                build_card_image(encrypted, self.source)
                original = self.source.read_bytes()
                source = decrypt.KeySource() if fixed else decrypt.KeySource(keys_file=self.keys)
                decrypt.decrypt_card_image(self.source, self.output, source, lambda _: None)
                self.assertEqual(self.source.read_bytes(), original)
                self.assertEqual(self.output.read_bytes()[0x400:], clear)
                self.assertEqual(len(self.output.read_bytes()), len(original))
                _, partition, _ = ncch.parse_card_image(self.output)
                self.assertTrue(ncch.read_exefrs_file(self.output, partition, "icon").startswith(b"SMDH"))

    def test_wrong_keys_do_not_replace_previous_output(self):
        encrypted, _ = encrypted_partition()
        build_card_image(encrypted, self.source)
        self.output.write_bytes(b"previous-good-output")
        self.keys.write_text("2c=" + "00" * 16 + "\n25=" + "00" * 16)
        with self.assertRaises(decrypt.DecryptError):
            decrypt.decrypt_card_image(self.source, self.output, decrypt.KeySource(keys_file=self.keys), lambda _: None)
        self.assertEqual(self.output.read_bytes(), b"previous-good-output")
        self.assertFalse(list(self.root.glob(".decrypt-*")))

    def test_source_destination_alias_is_rejected(self):
        build_card_image(build_cxi_partition(), self.source)
        original = self.source.read_bytes()
        with self.assertRaises(decrypt.DecryptError):
            decrypt.decrypt_card_image(self.source, self.source, decrypt.KeySource(), lambda _: None)
        self.assertEqual(self.source.read_bytes(), original)

    def test_partition_tables_are_sorted_and_fully_read(self):
        partition = build_cxi_partition()
        payload = bytearray(0x400 + len(partition) * 8)
        payload[0x100:0x104] = b"NCSD"
        for index in range(8):
            base = 0x400 + index * len(partition)
            payload[base:base + len(partition)] = partition
            struct.pack_into("<II", payload, 0x120 + (7 - index) * 8,
                             base // 512, len(partition) // 512)
        self.source.write_bytes(payload)
        decrypt.decrypt_card_image(self.source, self.output, decrypt.KeySource(), lambda _: None)
        self.assertEqual(self.output.read_bytes(), payload)

    def test_partition_and_region_bounds_fail_cleanly(self):
        for location, value in ((0x120, 0xFFFFFFFF), (0x124, 0xFFFFFFFF), (0x400 + 0x1A4, 0xFFFFFFFF)):
            with self.subTest(location=location):
                build_card_image(build_cxi_partition(), self.source)
                payload = bytearray(self.source.read_bytes())
                struct.pack_into("<I", payload, location, value)
                self.source.write_bytes(payload)
                with self.assertRaises(decrypt.DecryptError):
                    decrypt.decrypt_card_image(self.source, self.output, decrypt.KeySource(), lambda _: None)

    def test_wrong_content_key_is_detected_without_romfs(self):
        encrypted, _ = encrypted_partition()
        payload = bytearray(encrypted)
        payload[0x1B0:0x1BC] = bytes(12)
        build_card_image(payload, self.source)
        self.keys.write_text(f"2c={bytes(range(16)).hex()}\n25=" + "00" * 16)
        with self.assertRaisesRegex(decrypt.DecryptError, "file hash mismatch"):
            decrypt.decrypt_card_image(self.source, self.output, decrypt.KeySource(keys_file=self.keys), lambda _: None)
        self.assertFalse(self.output.exists())

    def test_missing_key_and_conflicting_rows_fail_cleanly(self):
        encrypted, _ = encrypted_partition()
        build_card_image(encrypted, self.source)
        self.keys.write_text(f"2c={bytes(range(16)).hex()}")
        with self.assertRaisesRegex(decrypt.DecryptError, "slot"):
            decrypt.decrypt_card_image(self.source, self.output, decrypt.KeySource(keys_file=self.keys), lambda _: None)
        self.keys.write_text("2c=" + "00" * 16 + "\n2c=" + "01" * 16)
        with self.assertRaisesRegex(decrypt.DecryptError, "conflicting"):
            decrypt.load_key_x_table(decrypt.KeySource(keys_file=self.keys))

    def test_seeded_crypto_is_explicitly_unsupported(self):
        payload = bytearray(build_cxi_partition(flag_byte=0x20))
        with self.assertRaisesRegex(decrypt.DecryptError, "seed"):
            decrypt.decrypt_partition(io.BytesIO(payload), io.BytesIO(), 0, len(payload), {}, lambda _: None)

    def test_key_sources_merge_and_reject_conflicts(self):
        boot9 = self.root / "synthetic-boot9.bin"
        blob = bytearray(0x8000)
        blob[0x59D0:0x59E0] = bytes(range(16))
        boot9.write_bytes(blob)
        table = decrypt.load_key_x_table(decrypt.KeySource(boot9, self.keys))
        self.assertEqual(set(table), {0x2C, 0x25})
        self.keys.write_text("2c=" + "ff" * 16)
        with self.assertRaisesRegex(decrypt.DecryptError, "conflicting"):
            decrypt.load_key_x_table(decrypt.KeySource(boot9, self.keys))

    def test_engine_errors_do_not_disclose_command_keys(self):
        secret = bytes(range(16))

        def failed_engine(*_):
            raise subprocess.CalledProcessError(1, ["openssl", "-K", secret.hex()])

        try:
            decrypt.stream_decrypt(io.BytesIO(bytes(16)), io.BytesIO(), 0, 16, secret, bytes(16), failed_engine)
        except decrypt.DecryptError:
            self.assertNotIn(secret.hex(), traceback.format_exc())
        else:
            self.fail("engine failure must be a controlled error")

    def test_openssl_fallback_matches_known_aes_vector(self):
        real_import = builtins.__import__

        def without_cryptography(name, *args, **kwargs):
            if name.startswith("cryptography"):
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with (patch.object(decrypt, "_engine_cache", None),
              patch("builtins.__import__", side_effect=without_cryptography)):
            self.assertEqual(decrypt.engine()(bytes(16), bytes(16), 16).hex(),
                             "66e94bd4ef8a2c3b884cfa59ca342b2e")
