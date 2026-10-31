"""User-data tools exercise only temporary synthetic app folders."""
import io
import os
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import bug_report, clean_cache


class UserDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="ctr-ops-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root / "Synthetic Game.app"
        self.app.mkdir()
        self.sandbox = self.root / (self.app.name + ".ctr-native")
        self.user = self.sandbox / "home/Library/Application Support/zakuro"
        self.user.mkdir(parents=True)

    def report(self, target=None):
        output = self.root / "report.zip"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bug_report.main([str(target or self.app), "-o", str(output)]), 0)
        return zipfile.ZipFile(output)

    def test_report_collects_current_runtime_logs(self):
        (self.user / "zakuro.log").write_text("runtime evidence")
        with self.report() as bundle:
            self.assertEqual(bundle.read("sandbox/zakuro.log"), b"runtime evidence")

    def test_cleaner_removes_only_inactive_known_cache_and_stale_log(self):
        cache = self.sandbox / "home/Library/Caches/zakuro/pipelines/0004000000000000.bin"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"cache")
        save = self.user / "savedata/save.bin"
        save.parent.mkdir()
        save.write_bytes(b"save")
        previous = self.user / "zakuro.previous.log"
        previous.write_text("previous")
        old = time.time() - 31 * 86400
        os.utime(previous, (old, old))
        current = self.user / "zakuro.log"
        current.write_text("current")
        with patch("dm.tools.user_data.active_files", return_value=set()), redirect_stdout(io.StringIO()):
            self.assertEqual(clean_cache.main([str(self.app)]), 0)
        self.assertFalse(cache.exists())
        self.assertFalse(previous.exists())
        self.assertTrue(current.exists())
        self.assertEqual(save.read_bytes(), b"save")

    def test_report_rejects_link_and_key_rows(self):
        fake = self.root / "boot9-fake.bin"
        fake.write_text("synthetic private marker")
        log = self.user / "zakuro.log"
        log.symlink_to(fake)
        with self.report() as bundle:
            self.assertNotIn("sandbox/zakuro.log", bundle.namelist())
        log.unlink()
        log.write_text("2c=" + "01" * 16 + "\n")
        with self.report() as bundle:
            self.assertNotIn("sandbox/zakuro.log", bundle.namelist())

    def test_report_rejects_parent_directory_symlinks(self):
        external = self.root / "external"
        external.mkdir()
        (external / "zakuro.log").write_text("private marker")
        self.user.rmdir()
        self.user.symlink_to(external)
        with self.report() as bundle:
            self.assertNotIn("sandbox/zakuro.log", bundle.namelist())

    def test_report_collects_build_logs_and_ignores_arbitrary_metadata(self):
        build = self.root / "0004000000000000_build"
        (build / "logs").mkdir(parents=True)
        (build / "logs/pack.log").write_text("synthetic build")
        (build / "logs/pack.tsv").write_text("appid\tsynthetic")
        (build / "logs/unknown.log").write_text("not allowlisted")
        with self.report(build) as bundle:
            self.assertEqual(bundle.read("build/pack.log"), b"synthetic build")
            self.assertIn("build/pack.tsv", bundle.namelist())
            self.assertNotIn("build/unknown.log", bundle.namelist())

    def test_report_keeps_bounded_tail(self):
        (self.user / "zakuro.log").write_bytes(b"x" * (bug_report.MAX_FILE + 100) + b"FINAL")
        with self.report() as bundle:
            data = bundle.read("sandbox/zakuro.log")
            self.assertEqual(len(data), bug_report.MAX_FILE)
            self.assertTrue(data.endswith(b"FINAL"))
            self.assertIn("sandbox/zakuro.log.truncated.txt", bundle.namelist())

    def test_cleanup_skips_entire_app_when_descendant_is_open(self):
        from dm.tools import user_data
        cache = self.sandbox / "home/Library/Caches/zakuro/pipelines/0004000000000000.bin"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"cache")
        with (patch.object(user_data, "active_files", return_value={self.user / "savedata/open.bin"}),
              redirect_stdout(io.StringIO())):
            self.assertEqual(clean_cache.main([str(self.app)]), 0)
        self.assertTrue(cache.exists())

    def test_cleanup_detection_error_does_not_delete(self):
        from dm.tools import user_data
        cache = self.sandbox / "home/Library/Caches/zakuro/pipelines/0004000000000000.bin"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"cache")
        with patch.object(user_data, "active_files", side_effect=user_data.DetectionError("test failure")):
            self.assertEqual(clean_cache.main([str(self.app)]), 1)
        self.assertTrue(cache.exists())

    def test_cleanup_dry_run_matches_actual_byte_count(self):
        from dm.tools import user_data
        cache = self.sandbox / "home/Library/Caches/zakuro/pipelines/0004000000000000.bin"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b"cache")
        outputs = []
        with patch.object(user_data, "active_files", return_value=set()):
            for extra in (["--dry-run"], []):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(clean_cache.main([str(self.root), *extra]), 0)
                outputs.append(out.getvalue())
        self.assertEqual(outputs[0].replace("(dry run) ", ""), outputs[1])
        self.assertIn("5 bytes", outputs[1])

    def test_cleanup_does_not_follow_cache_symlink(self):
        from dm.tools import user_data
        external = self.root / "keep.bin"
        external.write_bytes(b"must survive")
        cache = self.sandbox / "home/Library/Caches/zakuro/pipelines/0004000000000000.bin"
        cache.parent.mkdir(parents=True)
        cache.symlink_to(external)
        with patch.object(user_data, "active_files", return_value=set()), redirect_stdout(io.StringIO()):
            self.assertEqual(clean_cache.main([str(self.app)]), 0)
        self.assertEqual(external.read_bytes(), b"must survive")
        self.assertTrue(cache.is_symlink())

    def test_runtime_detection_preserves_spaces_and_failures(self):
        import subprocess
        from dm.tools import user_data
        host = self.app / "Contents/MacOS/zakuro-host"
        replies = [subprocess.CompletedProcess([], 0, b"123\n", b""),
                   subprocess.CompletedProcess([], 0, b"p123\0\nn" + os.fsencode(host) + b"\0", b"")]
        with patch.object(user_data.subprocess, "run", side_effect=replies):
            self.assertTrue(user_data.runtime_in_use(self.app))
        with (patch.object(user_data.subprocess, "run", side_effect=OSError("missing lsof")),
              self.assertRaises(user_data.DetectionError)):
            user_data.runtime_in_use(self.app)

    def test_cleanup_legacy_directory_cache_and_open_descendant(self):
        from dm.tools import user_data
        cache = self.app / "Contents/MacOS/sandbox/home/Library/Application Support/zakuro/cache/test.shadercache"
        cache.mkdir(parents=True)
        child = cache / "nested/cache.bin"
        child.parent.mkdir()
        child.write_bytes(b"legacy")
        with patch.object(user_data, "active_files", return_value={child}), redirect_stdout(io.StringIO()):
            self.assertEqual(clean_cache.main([str(self.app)]), 0)
        self.assertTrue(child.exists())
        with patch.object(user_data, "active_files", return_value=set()), redirect_stdout(io.StringIO()):
            self.assertEqual(clean_cache.main([str(self.app)]), 0)
        self.assertFalse(cache.exists())

    def test_runtime_detection_normalizes_safe_parent_segments(self):
        from dm.tools import user_data
        (self.root / "nested").mkdir()
        alias = self.root / "nested/../Synthetic Game.app"
        self.assertTrue(user_data.runtime_in_use(alias, {self.app / "Contents/MacOS/zakuro-host"}))

    def test_parent_segments_never_hide_directory_symlinks(self):
        from dm.tools import user_data
        external = self.root / "external"
        external.mkdir()
        (self.root / "link").symlink_to(external)
        alias = self.root / "link/../Synthetic Game.app"
        self.assertFalse(user_data.safe_path(alias))
        with self.assertRaises(OSError):
            user_data.runtime_in_use(alias, set())

    def test_report_ignores_non_dictionary_plist(self):
        import plistlib
        contents = self.app / "Contents"
        contents.mkdir()
        (contents / "Info.plist").write_bytes(plistlib.dumps([]))
        with self.report() as bundle:
            self.assertIn("report.txt", bundle.namelist())

    def test_report_keeps_utf8_tail_when_cut_inside_codepoint(self):
        (self.user / "zakuro.log").write_bytes(("é" * (bug_report.MAX_FILE // 2)).encode() + b"FINAL")
        with self.report() as bundle:
            data = bundle.read("sandbox/zakuro.log")
            data.decode("utf-8")
            self.assertTrue(data.endswith(b"FINAL"))
            self.assertLessEqual(len(data), bug_report.MAX_FILE)

    def test_report_does_not_treat_an_app_title_as_a_key_filename(self):
        app = self.root / "Keys and Doors.app"
        app.mkdir()
        user = app.with_name(app.name + ".ctr-native") / "home/Library/Application Support/zakuro"
        user.mkdir(parents=True)
        (user / "zakuro.log").write_text("runtime evidence")
        with self.report(app) as bundle:
            self.assertEqual(bundle.read("sandbox/zakuro.log"), b"runtime evidence")
