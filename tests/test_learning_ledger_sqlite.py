import gzip
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "learning-ledger" / "scripts" / "ledger.py"
SPEC = importlib.util.spec_from_file_location("learning_ledger", SCRIPT)
LEDGER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEDGER)


class SqliteLearningLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tempdir.name)
        self.db = self.project / ".kanban" / "kanban.db"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_append_and_aggregate_use_canonical_database(self):
        end_day = datetime.now(UTC).date().isoformat()
        event = {
            "ts_utc": f"{end_day}T12:00:00Z",
            "session_id": "session-1",
            "turn_id": 1,
            "role": "assistant",
            "event_type": "feedback",
            "text": "redacted",
            "reason_summary": "user correction",
            "context_track": "reflection",
        }
        self.assertEqual(
            LEDGER.main(["append", "--project", str(self.project), "--json", json.dumps(event)]),
            0,
        )
        self.assertFalse((self.project / ".learning-ledger" / "raw").exists())

        conn = sqlite3.connect(self.db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

        conn = LEDGER.KANBAN.connect(self.db)
        try:
            LEDGER.KANBAN.metric_snapshot(conn, "project", "repo")
        finally:
            conn.close()
        self.assertEqual(
            LEDGER.main([
                "aggregate", "--project", str(self.project), "--end-date", end_day
            ]),
            0,
        )
        artifact = self.project / ".learning-ledger" / "aggregates" / f"{end_day}_7d.json.gz"
        with gzip.open(artifact, "rt", encoding="utf-8") as handle:
            aggregate = json.loads(handle.readline())
        self.assertIn("wip_active", aggregate["metric_trends"])

        conn = sqlite3.connect(self.db)
        try:
            archive = conn.execute(
                "SELECT event_count, artifact_location, content_hash FROM learning_archives"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(archive[0], 1)
        self.assertEqual(
            archive[1], f".learning-ledger/aggregates/{end_day}_7d.json.gz"
        )
        self.assertTrue(archive[2].startswith("sha256:"))

    def test_legacy_import_is_idempotent_and_drops_invalid_optional_link(self):
        legacy_dir = self.project / ".learning-ledger" / "raw"
        legacy_dir.mkdir(parents=True)
        source = legacy_dir / "legacy.ndjson"
        source.write_text(json.dumps({
            "ts_utc": "2026-08-30T12:00:00Z",
            "event_type": "checkpoint",
            "context_track": "execution",
            "reason_summary": "legacy checkpoint",
            "task_id": "missing-task"
        }) + "\n", encoding="utf-8")
        args = ["import-legacy", "--project", str(self.project), str(source)]
        self.assertEqual(LEDGER.main(args), 0)
        self.assertEqual(LEDGER.main(args), 0)
        conn = sqlite3.connect(self.db)
        try:
            events = conn.execute(
                "SELECT COUNT(*), MIN(task_id) FROM learning_events WHERE event_type = 'checkpoint'"
            ).fetchone()
            archives = conn.execute(
                "SELECT COUNT(*) FROM learning_archives WHERE policy_version = 'legacy-import-1'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(events, (1, None))
        self.assertEqual(archives, 1)


if __name__ == "__main__":
    unittest.main()
