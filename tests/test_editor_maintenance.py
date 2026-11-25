"""Pre-V0.5 maintenance regressions: no partial files and valid video timings."""
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor


class EditorMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name).resolve()
        self.raw = self.folder / "raw"
        self.out = self.folder / "output"
        self.raw.mkdir()
        self.out.mkdir()
        (self.raw / "source.mp4").write_bytes(b"example footage placeholder")
        self.patches = [
            patch.object(editor, "RAW", self.raw),
            patch.object(editor, "OUT", self.out),
            patch.object(editor.shutil, "which", return_value="/usr/bin/ffmpeg"),
            patch.object(editor, "probe", return_value=30.0),
        ]
        for active in self.patches:
            active.start()

    def tearDown(self):
        for active in reversed(self.patches):
            active.stop()
        self.temp.cleanup()

    def test_failed_ffmpeg_leaves_no_partial_output(self):
        def fail_after_writing(args, **kwargs):
            Path(args[-1]).write_bytes(b"incomplete corrupted video")
            raise subprocess.CalledProcessError(returncode=1, cmd=args)

        with patch.object(editor.subprocess, "run", side_effect=fail_after_writing):
            with self.assertRaises(subprocess.CalledProcessError):
                editor.highlight("source.mp4", start=1, seconds=5, filename="output.mp4")

        self.assertEqual(list(self.out.iterdir()), [])

    def test_render_writes_final_video_only_after_success(self):
        def finish(args, **kwargs):
            Path(args[-1]).write_bytes(b"valid bytes")
            return subprocess.CompletedProcess(args, 0)

        with patch.object(editor.subprocess, "run", side_effect=finish):
            result = editor.highlight("source.mp4", start=1, seconds=5, filename="output.mp4")

        self.assertEqual(Path(result).read_bytes(), b"valid bytes")
        self.assertEqual([p.name for p in self.out.iterdir()], ["output.mp4"])

    def test_nonfinite_timings_are_rejected_before_ffmpeg(self):
        for start, seconds in [
            (float("nan"), 5),
            (float("inf"), 5),
            (0, float("nan")),
            (0, float("-inf")),
        ]:
            with self.subTest(start=start, seconds=seconds):
                with patch.object(editor.subprocess, "run") as run:
                    with self.assertRaises(ValueError):
                        editor.highlight("source.mp4", start=start, seconds=seconds)
                    run.assert_not_called()


class APIMetadataTests(unittest.TestCase):
    def test_health_version_matches_release(self):
        from apps.api.main import health
        self.assertEqual(health()["version"], "1.0.0-rc.2")


if __name__ == "__main__":
    unittest.main()
