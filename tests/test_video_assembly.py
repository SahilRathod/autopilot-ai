"""V0.5 Milestone 4: test local multi-clip assembly and truthful subtitle generation."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor, media_intelligence as media, platform_core as core
from app import video_assembly as assembly


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        self.raw = folder / "raw"
        self.out = folder / "out"
        self.raw.mkdir()
        self.out.mkdir()
        (self.raw / "game.mp4").write_bytes(b"test video bytes")
        self.patches = [
            patch.object(core, "DB", folder / "db.sqlite"),
            patch.object(editor, "RAW", self.raw),
            patch.object(editor, "OUT", self.out),
        ]
        for item in self.patches:
            item.start()
        core.initialize()
        media.initialize()
        assembly.initialize()
        self.w = core.new_workspace("My Workspace")
        self.channel = core.new_channel(self.w, "Gaming", "gaming")
        self.other = core.new_workspace("Other Workspace")
        self.other_channel = core.new_channel(self.other, "Private", "gaming")
        metadata = {
            "duration_seconds": 40.0, "width": 1280, "height": 720,
            "fps": 30.0, "video_codec": "h264", "audio_codec": "aac"
        }
        with patch.object(media, "probe_metadata", return_value=metadata):
            self.asset = media.import_media(self.w, self.channel, "game.mp4")
        with patch.object(media, "detect_changes", return_value=[12, 25]):
            media.scan_media(self.w, self.channel, self.asset["id"], clip_seconds=8, max_scan_seconds=35)
        self.candidates = media.candidates(self.w, self.channel, self.asset["id"])
        self.job = core.add_job(self.w, self.channel, "Best moments", "short")

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def approve(self):
        core.transition(self.w, self.job, "ready_for_review")
        core.transition(self.w, self.job, "approved")

    def fake_render(self, segments, target, preset, quality, audio_mode, caption_mode, caption_lines):
        target = Path(target)
        target.write_bytes(b"final video bytes")
        self.assertEqual(len(segments), 2)
        self.assertEqual(preset, "short")
        self.assertEqual(audio_mode, "normalize")
        self.assertEqual(caption_mode, "soft")
        return str(target)

    def test_assembly_requires_approved_job(self):
        with patch.object(assembly, "render_assembled_video") as encoder:
            with self.assertRaises(ValueError):
                assembly.export_job(self.w, self.channel, self.job,
                                    [self.candidates[0]["id"]])
            encoder.assert_not_called()

    def test_success_persists_local_output_and_rejects_duplicate_job(self):
        self.approve()
        with patch.object(assembly, "render_assembled_video", side_effect=self.fake_render) as encoder:
            result = assembly.export_job(
                self.w, self.channel, self.job,
                [self.candidates[0]["id"], self.candidates[1]["id"]],
                audio_mode="normalize", caption_mode="soft",
                caption_lines=["Hello gamers", "Welcome back"],
                quality="fast"
            )
        self.assertEqual(encoder.call_count, 1)
        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["youtube_uploaded"])
        self.assertTrue(Path(result["output_path"]).exists())
        saved = assembly.exports(self.w, self.channel)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["candidate_ids"], [self.candidates[0]["id"], self.candidates[1]["id"]])
        self.assertEqual(saved[0]["caption_lines"], ["Hello gamers", "Welcome back"])
        with self.assertRaises(ValueError):
            assembly.export_job(self.w, self.channel, self.job, [self.candidates[0]["id"]])
        self.assertEqual(assembly.exports(self.other, self.other_channel), [])
        with self.assertRaises(ValueError):
            assembly.export_job(self.other, self.other_channel, self.job, [self.candidates[0]["id"]])

    def test_failed_encoder_releases_claim_and_allows_retry(self):
        self.approve()
        with patch.object(assembly, "render_assembled_video", side_effect=RuntimeError("encoder failed")):
            with self.assertRaises(RuntimeError):
                assembly.export_job(self.w, self.channel, self.job, [self.candidates[0]["id"]])
        self.assertEqual(assembly.exports(self.w, self.channel), [])
        def success(segments, target, preset, quality, audio_mode, caption_mode, caption_lines):
            Path(target).write_bytes(b"ok")
            return str(target)
        with patch.object(assembly, "render_assembled_video", side_effect=success):
            result = assembly.export_job(self.w, self.channel, self.job, [self.candidates[0]["id"]])
        self.assertEqual(result["state"], "ready")

    def test_stale_source_and_out_of_scope_candidates_are_rejected(self):
        self.approve()
        with self.assertRaises(ValueError):
            assembly.export_job(self.w, self.channel, self.job, [999999])
        with self.assertRaises(ValueError):
            assembly.export_job(self.w, self.other_channel, self.job, [self.candidates[0]["id"]])
        (self.raw / "game.mp4").write_bytes(b"modified video")
        with self.assertRaises(ValueError):
            assembly.export_job(self.w, self.channel, self.job, [self.candidates[0]["id"]])

    def test_invalid_caption_and_export_settings_are_rejected(self):
        self.approve()
        combinations = [
            {"caption_lines": ["hello"], "caption_mode": "none"},
            {"caption_lines": ["caption"], "caption_mode": "burn", "audio_mode": "not_real"},
            {"caption_lines": ["line\n2"], "caption_mode": "soft"},
            {"caption_lines": ["<b>html</b>"], "caption_mode": "soft"},
            {"caption_lines": ["x" * 161], "caption_mode": "burn"},
            {"quality": "ultra"},
            {"audio_mode": "wrong"},
            {"caption_mode": "unavailable"},
        ]
        for opts in combinations:
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                assembly.export_job(self.w, self.channel, self.job,
                                    [self.candidates[0]["id"]], **opts)
        self.assertEqual(assembly.exports(self.w, self.channel), [])

    def test_generate_srt_from_user_text_evenly_not_speech_transcript(self):
        subtitles = assembly.captions_to_srt(["First line", "Second line"], 6)
        self.assertIn("00:00:00,000 --> 00:00:03,000", subtitles)
        self.assertIn("00:00:03,000 --> 00:00:06,000", subtitles)
        self.assertIn("First line", subtitles)
        self.assertNotIn("autotranscribed", subtitles.lower())

    def test_encoder_uses_staging_concat_and_audio_modes(self):
        fake_source = self.raw / "game.mp4"
        target = self.out / "final.mp4"
        segments = [
            {"source": fake_source, "start": 0, "seconds": 2, "has_audio": True},
            {"source": fake_source, "start": 5, "seconds": 3, "has_audio": False},
        ]
        seen = []
        def simulate(command, **kwargs):
            seen.append((command, kwargs))
            Path(command[-1]).write_bytes(b"video-stage")
            return subprocess.CompletedProcess(command, 0)
        with patch.object(assembly.shutil, "which", return_value="ffmpeg"), \
             patch.object(assembly.subprocess, "run", side_effect=simulate):
            output = assembly.render_assembled_video(
                segments, target, "short", "fast", "normalize", "soft",
                ["First", "Second"])
        self.assertEqual(output, str(target))
        self.assertTrue(target.exists())
        self.assertEqual(len(seen), 4)  # 2 segments + concat + subtitle mux
        self.assertTrue(any(any("loudnorm=I=-16:TP=-1.5:LRA=11" in token for token in cmd) for cmd, _ in seen))
        self.assertTrue(any(any("anullsrc" in token for token in cmd) for cmd, _ in seen))
        self.assertTrue(any("mov_text" in cmd for cmd, _ in seen))
        self.assertEqual([p.name for p in self.out.iterdir()], ["final.mp4"])

    def test_ffmpeg_failure_cleans_output_and_temporary_files(self):
        fake_source = self.raw / "game.mp4"
        target = self.out / "broken.mp4"
        segments = [{"source": fake_source, "start": 0, "seconds": 2, "has_audio": True}]
        def fail(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial output")
            raise subprocess.CalledProcessError(1, command)
        with patch.object(assembly.shutil, "which", return_value="ffmpeg"), \
             patch.object(assembly.subprocess, "run", side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):
                assembly.render_assembled_video(segments, target, "long", "fast",
                                                "preserve", "none", [])
        self.assertFalse(target.exists())
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
