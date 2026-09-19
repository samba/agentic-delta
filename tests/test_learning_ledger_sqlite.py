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

    def test_append_and_aggregate_use_ledger_artifacts_not_kanban_schema(self):
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
        self.assertTrue((self.project / ".learning-ledger" / "raw").exists())

        self.assertEqual(
            LEDGER.main([
                "aggregate", "--project", str(self.project), "--end-date", end_day
            ]),
            0,
        )
        artifact = self.project / ".learning-ledger" / "aggregates" / f"{end_day}_7d.json.gz"
        with gzip.open(artifact, "rt", encoding="utf-8") as handle:
            aggregate = json.loads(handle.readline())
        self.assertEqual(aggregate["metric_trends"], {})

        manifest = self.project / ".learning-ledger" / "archives.jsonl"
        self.assertTrue(manifest.exists())
        self.assertIn("content_hash", manifest.read_text())

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
        self.assertTrue((self.project / ".learning-ledger" / "imports").exists())
        self.assertGreaterEqual(len(LEDGER.load_file_events(self.project / ".learning-ledger")), 1)


if __name__ == "__main__":
    unittest.main()
