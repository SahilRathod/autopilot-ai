"""V0.5 M3: deterministic local heuristic ranking, no semantic game-event claims."""
import math
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import editor, platform_core as core, media_intelligence as media
from app import highlight_ranker as ranker


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        (self.raw / "game.mp4").write_bytes(b"unchanged source")
        self.p_db = patch.object(core, "DB", self.root / "db.sqlite")
        self.p_raw = patch.object(editor, "RAW", self.raw)
        self.p_db.start()
        self.p_raw.start()
        core.initialize()
        media.initialize()
        ranker.initialize()
        self.w = core.new_workspace("Gaming studio")
        self.c = core.new_channel(self.w, "FPS", "gaming")
        self.other_w = core.new_workspace("Other")
        self.other_c = core.new_channel(self.other_w, "School", "education")
        self.meta = {"duration_seconds": 45.0, "width": 1920, "height": 1080,
                     "fps": 30.0, "video_codec": "h264", "audio_codec": "aac"}

    def tearDown(self):
        self.p_raw.stop()
        self.p_db.stop()
        self.temp.cleanup()

    def create_candidates(self, audio=True):
        meta = dict(self.meta)
        if not audio:
            meta["audio_codec"] = None
        with patch.object(media, "probe_metadata", return_value=meta):
            asset = media.import_media(self.w, self.c, "game.mp4")
        with patch.object(media, "detect_changes", return_value=[12.0, 24.0]):
            media.scan_media(self.w, self.c, asset["id"], clip_seconds=8, max_scan_seconds=35)
        return asset, media.candidates(self.w, self.c, asset["id"])

    def test_audio_transient_beats_quiet_scene_for_tactical_profile(self):
        asset, clips = self.create_candidates()
        self.assertEqual(len(clips), 3)
        # 0.5 second RMS bins: burst around 22–23 seconds, near candidate 24s.
        levels = [0.01] * 90
        levels[44:48] = [0.6, 0.8, 0.65, 0.7]
        with patch.object(ranker, "decode_audio_levels", return_value=levels) as decode:
            ranked = ranker.rank_asset(self.w, self.c, asset["id"], profile="tactical")
        self.assertEqual(decode.call_count, 1)
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["candidate_id"], clips[2]["id"])
        self.assertGreater(ranked[0]["score"], ranked[-1]["score"])
        self.assertTrue(ranked[0]["audio_analyzed"])
        self.assertEqual(ranked[0]["profile"], "tactical")
        self.assertEqual(ranked[0]["evidence"]["signals"]["audio_transient"], "elevated")
        self.assertEqual(ranked[0]["evidence"]["claims"], "visual and audio heuristics only")
        self.assertNotIn("kill", " ".join(ranked[0]["evidence"]["reasons"]).lower())

    def test_no_audio_still_ranks_visual_candidates_without_ffmpeg_audio(self):
        asset, clips = self.create_candidates(audio=False)
        with patch.object(ranker, "decode_audio_levels") as audio:
            rows = ranker.rank_asset(self.w, self.c, asset["id"], profile="sandbox")
        audio.assert_not_called()
        self.assertEqual({r["audio_analyzed"] for r in rows}, {False})
        self.assertEqual(rows[0]["candidate_id"], clips[1]["id"])
        self.assertTrue(all(0 <= r["score"] <= 100 for r in rows))
        self.assertIn("No audio track", rows[0]["evidence"]["reasons"][-1])

    def test_ranking_persists_and_rescan_removes_stale_scores(self):
        asset, _ = self.create_candidates()
        with patch.object(ranker, "decode_audio_levels", return_value=[0.05] * 90):
            generated = ranker.rank_asset(self.w, self.c, asset["id"], profile="balanced")
        persisted = ranker.rankings(self.w, self.c, asset["id"], "balanced")
        self.assertEqual([r["candidate_id"] for r in generated],
                         [r["candidate_id"] for r in persisted])
        self.assertEqual(ranker.rankings(self.w, self.c, asset["id"], "tactical"), [])
        with patch.object(media, "detect_changes", return_value=[18.0]):
            media.scan_media(self.w, self.c, asset["id"], clip_seconds=8)
        self.assertEqual(ranker.rankings(self.w, self.c, asset["id"], "balanced"), [])

    def test_workspace_and_profile_validation(self):
        asset, _ = self.create_candidates()
        with self.assertRaises(ValueError):
            ranker.rankings(self.other_w, self.other_c, asset["id"], "balanced")
        with self.assertRaises(ValueError):
            ranker.rank_asset(self.other_w, self.other_c, asset["id"])
        with self.assertRaises(ValueError):
            ranker.rank_asset(self.w, self.c, asset["id"], profile="fake_game")
        with self.assertRaises(ValueError):
            ranker.rankings(self.w, self.c, asset["id"], profile="fake_game")
        with self.assertRaises(ValueError):
            ranker.rank_asset(self.w, self.c, asset["id"], max_seconds=float("nan"))
        with self.assertRaises(ValueError):
            ranker.rank_asset(self.w, self.c, asset["id"], max_seconds=601)

    def test_audio_pcm_rms_bins_are_deterministic_and_bounded(self):
        # 8k mono, 16bit PCM; two 0.5s bins with very different loudness.
        quiet = struct.pack("<h", 500) * 4000
        loud = struct.pack("<h", 12000) * 4000
        with patch.object(ranker.shutil, "which", return_value="ffmpeg"), \
             patch.object(ranker.subprocess, "run",
               return_value=subprocess.CompletedProcess([], 0, quiet + loud, b"")) as run:
            levels = ranker.decode_audio_levels(self.raw / "game.mp4", 1)
        self.assertEqual(len(levels), 2)
        self.assertGreater(levels[1], levels[0] * 10)
        command = run.call_args.args[0]
        self.assertIn("8000", command)
        self.assertIn("s16le", command)
        self.assertEqual(run.call_args.kwargs["timeout"] <= 180, True)

    def test_audio_decoder_failure_does_not_create_fake_zero_data(self):
        with patch.object(ranker.shutil, "which", return_value="ffmpeg"), \
             patch.object(ranker.subprocess, "run",
                          side_effect=subprocess.CalledProcessError(1, ["ffmpeg"])):
            with self.assertRaises(ValueError):
                ranker.decode_audio_levels(self.raw / "game.mp4", 12)

    def test_silent_or_flat_audio_falls_back_to_visual_weights(self):
        asset, clips = self.create_candidates(audio=True)
        for constant in (0.0, 0.25):
            with self.subTest(constant=constant), patch.object(
                    ranker, "decode_audio_levels", return_value=[constant] * 90):
                rows = ranker.rank_asset(self.w, self.c, asset["id"], profile="tactical")
            self.assertTrue(all(not row["audio_analyzed"] for row in rows))
            self.assertEqual(rows[0]["candidate_id"], clips[1]["id"])
            self.assertEqual(rows[0]["score"], 65)

    def test_ranking_checks_large_source_checksum_only_once(self):
        asset, _ = self.create_candidates()
        original = media._validated_source
        with patch.object(media, "_validated_source", wraps=original) as verified, \
             patch.object(ranker, "decode_audio_levels", return_value=[0.02] * 90):
            ranker.rank_asset(self.w, self.c, asset["id"])
        self.assertEqual(verified.call_count, 1)

    def test_ranking_detects_source_changed_during_audio_decoding(self):
        asset, _ = self.create_candidates()
        def alter_source(source, seconds):
            (self.raw / "game.mp4").write_bytes(b"now changed during analysis")
            return [0.01] * 90
        with patch.object(ranker, "decode_audio_levels", side_effect=alter_source):
            with self.assertRaises(ValueError):
                ranker.rank_asset(self.w, self.c, asset["id"])
        self.assertEqual(ranker.rankings(self.w, self.c, asset["id"]), [])

    def test_ranking_source_mutation_is_rejected(self):
        asset, _ = self.create_candidates()
        (self.raw / "game.mp4").write_bytes(b"changed after media scan")
        with patch.object(ranker, "decode_audio_levels") as audio:
            with self.assertRaises(ValueError):
                ranker.rank_asset(self.w, self.c, asset["id"])
        audio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
