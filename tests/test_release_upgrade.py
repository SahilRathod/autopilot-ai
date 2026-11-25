import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import maintenance, platform_core as core, youtube_connection as yt


class ReleaseUpgradeTests(unittest.TestCase):
    def test_upgrade_preserves_existing_channel_and_upload_grant(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(core,"DB",Path(folder)/"platform.sqlite3"):
            core.initialize()
            w=core.new_workspace("Existing workspace")
            c=core.new_channel(w,"Existing channel","gaming")
            with core.connect() as db:
                db.execute("""CREATE TABLE youtube_links (
                    local_channel_id INTEGER PRIMARY KEY REFERENCES channels(id),
                    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                    remote_channel_id TEXT NOT NULL UNIQUE,
                    profile_json TEXT NOT NULL,
                    encrypted_refresh BLOB NOT NULL,
                    client_id TEXT NOT NULL,
                    connected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    upload_authorized INTEGER NOT NULL DEFAULT 0
                )""")
                db.execute("""INSERT INTO youtube_links(local_channel_id,workspace_id,remote_channel_id,
                    profile_json,encrypted_refresh,client_id,upload_authorized)
                    VALUES(?,?,?,?,?,?,1)""",(c,w,"UC-existing",'{"title":"Existing"}',b"fixture","client"))
            snapshot=maintenance.backup_database(core.DB,Path(folder)/"backup.sqlite3")
            yt.initialize()
            yt.initialize()
            with core.connect() as db:
                row=db.execute("SELECT * FROM youtube_links").fetchone()
                self.assertEqual(row["remote_channel_id"],"UC-existing")
                self.assertEqual(row["encrypted_refresh"],b"fixture")
                self.assertEqual(row["upload_authorized"],1)
                self.assertEqual(row["analytics_authorized"],0)
                self.assertEqual(row["manage_authorized"],0)
            old=sqlite3.connect(snapshot)
            try:
                self.assertEqual(old.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(old.execute("SELECT remote_channel_id FROM youtube_links").fetchone()[0],"UC-existing")
                self.assertNotIn("analytics_authorized",{r[1] for r in old.execute("PRAGMA table_info(youtube_links)")})
            finally:
                old.close()
