import contextlib
import hashlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/kanban/scripts/kanban.py"
SPEC = importlib.util.spec_from_file_location("kanban_helper", SCRIPT)
KANBAN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(KANBAN)


class KanbanKernelTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "kanban.db"

    def tearDown(self):
        self.tempdir.cleanup()

    def run_cli(self, *args):
        self.assertEqual(KANBAN.main(["--db", str(self.db), *args]), 0)

    def row(self, query, params=()):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(query, params).fetchone()
        finally:
            conn.close()

    def make_task(self, task_id="task-1", state="Backlog"):
        self.run_cli("intent", "add", "goal", "Deliver an outcome", "--type", "feature")
        self.run_cli(
            "task", "add", task_id, "Bounded work", "--intent", "goal",
            "--state", state, "--scope", "one slice", "--acceptance", "accepted",
            "--validation", "independent evidence", "--owner", "implementer",
            "--details", '{"plan":"bounded implementation"}',
            "--details", '{"plan":"implement and validate one bounded slice"}',
        )

    def test_intents_are_typed_and_tasks_have_many_to_many_intents(self):
        self.run_cli("intent", "add", "feature", "Improve the product", "--type", "feature")
        self.run_cli("intent", "add", "problem", "Remove a defect", "--type", "problem")
        self.run_cli("task", "add", "fix", "Shared corrective work", "--intent", "feature", "--intent", "problem")
        self.assertEqual(self.row("SELECT COUNT(*) FROM task_intents")[0], 2)
        self.assertEqual(self.row("SELECT intent_type FROM intents WHERE id='feature'")[0], "feature")

    def test_task_state_is_a_foreign_key_and_bug_is_a_task_type(self):
        self.make_task("bug-1")
        self.run_cli("task", "add", "bug-2", "Login loops", "--intent", "goal", "--type", "bug", "--details", '{"observed":"loop"}')
        self.assertEqual(self.row("SELECT task_type FROM tasks WHERE id='bug-2'")[0], "bug")
        with self.assertRaises(sqlite3.IntegrityError):
            conn = sqlite3.connect(self.db)
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("UPDATE tasks SET state_id='missing' WHERE id='bug-1'")
            finally:
                conn.close()

    def test_ready_enlists_every_active_specialist_and_done_requires_checks(self):
        self.make_task()
        self.run_cli("task", "move", "task-1", "Ready")
        expected = self.row("SELECT COUNT(*) FROM specialist_roles WHERE active=1")[0]
        self.assertEqual(self.row("SELECT COUNT(*) FROM task_checks WHERE task_id='task-1' AND check_type='assurance'")[0], expected)
        self.run_cli("task", "move", "task-1", "Active")
        self.run_cli("evidence", "add", "implementation-proof", "task-1", "bounded artifact", "--result", "pass", "--producer", "implementer")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tasks SET details_json=json_set(details_json, '$.completion', 'slice complete') WHERE id='task-1'")
        self.run_cli("evidence", "add", "pre-review", "task-1", "bounded artifact", "--result", "pass", "--producer", "implementer")
        self.run_cli("task", "move", "task-1", "Review")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "move", "task-1", "Done")

        checks = self._all("SELECT id, specialist_role_id FROM task_checks WHERE task_id='task-1'")
        for check in checks:
            self.run_cli("review", "check", "record", check["id"], "task-1", "passed", "--reviewer", check["specialist_role_id"])
            self.run_cli("evidence", "add", f"evidence-{check['id']}", "task-1", "bounded artifact", "--check-id", check["id"], "--result", "pass", "--producer", check["specialist_role_id"], "--revision", "HEAD")
        self.run_cli("task", "move", "task-1", "Done")
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='task-1'")[0], "Done")

    def _all(self, query, params=()):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def test_wip_pressure_is_visible_and_does_not_block_parallel_flow(self):
        self.make_task("one")
        self.run_cli("task", "move", "one", "Ready")
        self.run_cli("task", "move", "one", "Active")
        for task_id in ("two", "three", "four"):
            self.run_cli("task", "add", task_id, task_id, "--intent", "goal", "--owner", "worker", "--scope", "one slice", "--acceptance", "accepted", "--validation", "independent evidence", "--details", '{"plan":"implement and validate one bounded slice"}')
            self.run_cli("task", "move", task_id, "Ready")
            if task_id != "four":
                self.run_cli("task", "move", task_id, "Active")
        self.run_cli("task", "move", "four", "Active")
        status = __import__("json").loads(self._capture_cli("status", "--json"))
        active = next(row for row in status["states"] if row["state"] == "Active")
        self.assertTrue(active["full"])
        self.assertEqual(active["overage"], 1)
        self.run_cli("pull", "lease", "issue", "review-capacity", "--stage", "Review", "--lane", "reviewer", "--slots", "2", "--eligibility", '{"type":"review"}', "--required-output", "pass or rework", "--owner", "supervisor", "--ttl-seconds", "60", "--idempotency-key", "lease-1")
        self.run_cli("pull", "lease", "renew", "review-capacity", "--ttl-seconds", "120")
        self.run_cli("pull", "lease", "release", "review-capacity")
        self.assertEqual(self.row("SELECT status FROM pull_capacity_leases WHERE id='review-capacity'")[0], "released")
        self.assertIsNone(self.row("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"))

    def test_existing_state_wip_budget_can_be_changed_explicitly(self):
        self.run_cli("state", "set", "Active", "--wip-limit", "1")
        self.assertEqual(self.row("SELECT wip_limit FROM task_states WHERE id='active'")[0], 1)
        self.run_cli("state", "set", "Active", "--unlimited")
        self.assertIsNone(self.row("SELECT wip_limit FROM task_states WHERE id='active'")[0])
        with self.assertRaises(SystemExit):
            self.run_cli("state", "set", "Active", "--wip-limit", "0")

    def test_research_references_and_guidance_are_linked(self):
        self.run_cli("intent", "add", "goal", "Design a capability", "--type", "capability")
        self.run_cli("reference", "add", "source-1", "https://example.test/source", "--title", "Source")
        self.run_cli("reference", "link", "source-1", "--intent-id", "goal")
        self.run_cli("guidance", "add", "safe-change", "Preserve compatibility", "--type", "tenet", "--version", "1")
        self.run_cli("guidance", "reference", "safe-change", "source-1", "--version", "1")
        self.assertEqual(self.row("SELECT COUNT(*) FROM guidance_references")[0], 1)
        self.assertEqual(self.row("SELECT COUNT(*) FROM reference_intents")[0], 1)

    def test_task_show_includes_active_latest_guidance_for_workers(self):
        self.run_cli("guidance", "add", "safe-change", "Preserve compatibility", "--type", "principle", "--version", "1")
        self.run_cli("guidance", "add", "review-risk", "Address known risks first", "--type", "tenet", "--version", "1")
        self.run_cli("guidance", "add", "safe-change", "Superseded wording", "--type", "principle", "--version", "2", "--status", "retired")
        self.make_task("guided")
        task = __import__("json").loads(self._capture_cli("task", "show", "guided"))
        guidance = {item["id"]: item for item in task["guidance"]}
        self.assertEqual(set(guidance), {"safe-change", "review-risk"})
        self.assertEqual(guidance["safe-change"]["version"], 1)
        self.assertEqual(guidance["review-risk"]["statement"], "Address known risks first")

    def test_status_json_and_validation(self):
        self.make_task()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("status", "--json")
        payload = __import__("json").loads(output.getvalue())
        walked = {row["state"] for row in payload["board_walk"]}
        self.assertTrue({"Ready", "Active", "Review"}.issubset(walked))
        self.assertNotIn("Backlog", walked)
        self.assertNotIn("Done", walked)
        self.run_cli("validate")

    def test_pull_next_selects_and_claims_atomically(self):
        self.make_task("first")
        self.run_cli("task", "add", "second", "Later work", "--intent", "goal", "--scope", "one slice", "--acceptance", "accepted", "--validation", "independent evidence", "--owner", "worker", "--details", '{"plan":"bounded implementation"}')
        self.run_cli("task", "move", "first", "Ready")
        self.run_cli("task", "move", "second", "Ready")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("pull", "next", "--claim", "--actor", "worker-1", "--json")
        self.assertEqual(__import__("json").loads(output.getvalue())["task"]["id"], "first")
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='first'")[0], "Active")

    def test_ready_requirements_are_enforced_on_insert(self):
        self.run_cli("intent", "add", "goal", "Deliver an outcome")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "add", "premature", "Missing scope", "--intent", "goal", "--state", "Ready")

    def test_custom_process_states_drive_claim_and_review_behavior(self):
        self.run_cli("intent", "add", "goal", "Deliver through a custom process")
        self.run_cli("state", "add", "ship", "Ship", "--position", "90", "--terminal", "--assurance-on-entry", "--requires-checks", "--requires-evidence")
        self.run_cli("state", "add", "intake", "Intake", "--position", "60", "--required-fields", "[\"summary\"]")
        self.run_cli("state", "add", "build", "Build", "--position", "70", "--previous", "intake", "--worker-entry", "--required-fields", "[\"scope\",\"worker\"]")
        self.run_cli("state", "add", "qa", "Quality Assurance", "--position", "80", "--previous", "build", "--next", "ship", "--assurance-on-entry", "--review-queue")
        self.run_cli("task", "add", "custom-task", "Custom workflow task", "--intent", "goal", "--state", "intake", "--owner", "worker", "--scope", "one slice")
        self.run_cli("pull", "next", "--claim", "--actor", "worker-1")
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='custom-task'")[0], "Build")
        self.run_cli("task", "move", "custom-task", "qa")
        self.assertGreater(self.row("SELECT COUNT(*) FROM task_checks WHERE task_id='custom-task'")[0], 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("status", "--json")
        self.assertIn("Quality Assurance", output.getvalue())

    def test_task_purge_cascades_task_records_and_dependency_edges(self):
        self.run_cli("intent", "add", "goal", "Purgeable work")
        self.run_cli("state", "add", "archive", "Archive", "--position", "45", "--previous", "review", "--next", "done", "--terminal")
        self.run_cli("task", "add", "old-task", "Old task", "--intent", "goal", "--owner", "worker", "--scope", "one slice", "--acceptance", "accepted", "--validation", "validated", "--details", '{"plan":"bounded implementation"}')
        self.run_cli("task", "add", "survivor", "Surviving task", "--intent", "goal")
        self.run_cli("task", "dependency", "add", "survivor", "old-task")
        self.run_cli("task", "move", "old-task", "Ready")
        self.run_cli("task", "move", "old-task", "Active")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tasks SET details_json=json_set(details_json, '$.completion', 'slice complete') WHERE id='old-task'")
        self.run_cli("evidence", "add", "old-proof", "old-task", "artifact", "--result", "pass", "--producer", "worker")
        self.run_cli("task", "move", "old-task", "Review")
        self.run_cli("evidence", "add", "old-evidence", "old-task", "artifact", "--result", "pass", "--producer", "worker")
        self.run_cli("pull", "lease", "issue", "archive", "--stage", "Archive", "--lane", "archive", "--slots", "1", "--required-output", "archival", "--owner", "coordinator", "--ttl-seconds", "60", "--idempotency-key", "purge-test")
        self.run_cli("pull", "lease", "reserve", "archive", "old-task")
        self.run_cli("task", "move", "old-task", "Archive")
        self.run_cli("task", "purge", "old-task", "--confirm")
        self.assertIsNone(self.row("SELECT id FROM tasks WHERE id='old-task'"))
        self.assertIsNotNone(self.row("SELECT id FROM tasks WHERE id='survivor'"))
        self.assertIsNone(self.row("SELECT task_id FROM task_dependencies WHERE dependency_id='old-task'"))
        self.assertIsNone(self.row("SELECT task_id FROM task_events WHERE task_id='old-task'"))
        self.assertIsNone(self.row("SELECT task_id FROM task_checks WHERE task_id='old-task'"))
        self.assertIsNone(self.row("SELECT task_id FROM evidence WHERE task_id='old-task'"))
        self.assertIsNone(self.row("SELECT task_id FROM pull_capacity_reservations WHERE task_id='old-task'"))

    def test_task_purge_rejects_nonterminal_tasks(self):
        self.make_task("active-work")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "purge", "active-work", "--confirm")
        self.assertIsNotNone(self.row("SELECT id FROM tasks WHERE id='active-work'"))

    def test_review_records_role_and_worker_and_rejects_owner_self_review(self):
        self.make_task("reviewed")
        self.run_cli("task", "move", "reviewed", "Ready")
        self.run_cli("task", "move", "reviewed", "Active")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tasks SET details_json=json_set(details_json, '$.completion', 'slice complete') WHERE id='reviewed'")
        self.run_cli("evidence", "add", "reviewed-proof", "reviewed", "bounded artifact", "--result", "pass", "--producer", "implementer")
        self.run_cli("task", "move", "reviewed", "Review")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "claim", "reviewed", "--actor", "implementer")
        self.run_cli("task", "claim", "reviewed", "--actor", "reviewer-1")
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='reviewed'")[0], "Review")
        self.assertEqual(self.row("SELECT owner FROM tasks WHERE id='reviewed'")[0], "implementer")
        self.assertIsNotNone(self.row("SELECT id FROM task_events WHERE task_id='reviewed' AND event_type='review_claimed'"))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("evidence", "list", "reviewed", "--json")
        self.assertEqual(len(__import__("json").loads(output.getvalue())), 1)
        check = self.row("SELECT id, specialist_role_id FROM task_checks WHERE task_id='reviewed' ORDER BY id LIMIT 1")
        with self.assertRaises(SystemExit):
            self.run_cli("review", "check", "record", check["id"], "reviewed", "passed", "--reviewer-role", check["specialist_role_id"], "--reviewer-worker-id", "implementer")
        self.run_cli("review", "check", "record", check["id"], "reviewed", "passed", "--reviewer-role", check["specialist_role_id"], "--reviewer-worker-id", "reviewer-1")
        recorded = self.row("SELECT reviewer_role_id, reviewer_worker_id FROM task_checks WHERE id=?", (check["id"],))
        self.assertEqual(recorded["reviewer_role_id"], check["specialist_role_id"])
        self.assertEqual(recorded["reviewer_worker_id"], "reviewer-1")

    def test_review_pull_claims_without_transitioning_or_reassigning(self):
        self.make_task("review-pull")
        self.run_cli("task", "move", "review-pull", "Ready")
        self.run_cli("task", "move", "review-pull", "Active")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE tasks SET details_json=json_set(details_json, '$.completion', 'slice complete') WHERE id='review-pull'")
        self.run_cli("evidence", "add", "review-pull-proof", "review-pull", "bounded artifact", "--result", "pass", "--producer", "implementer")
        self.run_cli("task", "move", "review-pull", "Review")
        self.run_cli("pull", "lease", "issue", "review-lease", "--stage", "Review", "--lane", "review", "--slots", "1", "--required-output", "review result", "--owner", "coordinator", "--ttl-seconds", "60", "--idempotency-key", "review-pull-lease")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("pull", "next", "--lease", "review-lease", "--actor", "reviewer-1", "--json")
        result = __import__("json").loads(output.getvalue())["task"]
        self.assertEqual(result["id"], "review-pull")
        self.assertTrue(result["claimed"])
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='review-pull'")[0], "Review")
        self.assertEqual(self.row("SELECT owner FROM tasks WHERE id='review-pull'")[0], "implementer")
        self.assertIsNotNone(self.row("SELECT id FROM pull_capacity_reservations WHERE task_id='review-pull' AND status='active'"))

    def test_evidence_inspection_filters_and_provenance_validation(self):
        self.make_task("evidence-query")
        self.run_cli("task", "move", "evidence-query", "Ready")
        check = self.row("SELECT id, criterion FROM task_checks WHERE task_id='evidence-query' ORDER BY id LIMIT 1")
        artifact = ROOT / "README.md"
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.run_cli(
            "evidence", "add", "evidence-query-proof", "evidence-query", "README proof",
            "--check-id", check["id"], "--result", "pass", "--producer", "reviewer",
            "--revision", "HEAD", "--location", "README.md", "--content-hash", digest,
        )
        with self.assertRaises(SystemExit):
            self.run_cli("evidence", "add", "bad-revision", "evidence-query", "artifact", "--result", "pass", "--producer", "worker", "--revision", "not-a-commit")
        with self.assertRaises(SystemExit):
            self.run_cli("evidence", "add", "bad-hash", "evidence-query", "artifact", "--result", "pass", "--producer", "worker", "--location", "README.md", "--content-hash", "0" * 64)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("evidence", "list", "evidence-query", "--check-id", check["id"], "--criterion", check["criterion"], "--revision", "HEAD", "--producer", "reviewer", "--result", "pass", "--json")
        rows = json.loads(output.getvalue())
        self.assertEqual([row["id"] for row in rows], ["evidence-query-proof"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("evidence", "show", "evidence-query-proof", "--json")
        self.assertEqual(json.loads(output.getvalue())["content_hash"], digest)

    def test_research_references_can_be_listed_and_repaired(self):
        self.run_cli("reference", "add", "source-1", "https://example.test/source", "--title", "Source", "--summary", "incomplete")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("reference", "list", "--json")
        self.assertEqual(json.loads(output.getvalue())[0]["summary"], "incomplete")
        self.run_cli("reference", "update", "source-1", "--relevance", "Directly informs the task", "--constraints", "Vendor publication", "--provenance", '{"retrieved_by":"researcher"}')
        updated = self.row("SELECT relevance, constraints, provenance_json FROM research_references WHERE id='source-1'")
        self.assertEqual(updated["relevance"], "Directly informs the task")
        self.assertEqual(json.loads(updated["provenance_json"])["retrieved_by"], "researcher")
        with self.assertRaises(SystemExit):
            self.run_cli("reference", "update", "source-1")

    def test_new_or_reactivated_specialist_is_synced_to_unfinished_assurance_tasks(self):
        self.make_task("roster-task")
        self.run_cli("task", "move", "roster-task", "Ready")
        before = self.row("SELECT COUNT(*) FROM task_checks WHERE task_id='roster-task'")[0]
        self.run_cli("specialist", "add", "new-specialist", "New specialist", "new purpose", "new description")
        after_add = self.row("SELECT COUNT(*) FROM task_checks WHERE task_id='roster-task'")[0]
        self.assertEqual(after_add, before + 1)
        self.run_cli("specialist", "deactivate", "new-specialist")
        self.run_cli("specialist", "activate", "new-specialist")
        self.assertEqual(self.row("SELECT COUNT(*) FROM task_checks WHERE task_id='roster-task' AND specialist_role_id='new-specialist'")[0], 1)

    def test_task_events_can_be_added_and_listed(self):
        self.make_task("events")
        self.run_cli("task", "event", "add", "events", "handoff", "Prepared for implementation", "--actor", "coordinator", "--payload", '{"next":"build"}', "--idempotency-key", "handoff-1")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("task", "event", "list", "events", "--json")
        events = __import__("json").loads(output.getvalue())
        self.assertTrue(any(event["event_type"] == "handoff" and event["payload"]["next"] == "build" for event in events))

    def test_task_refinement_and_assignment_are_durable_operations(self):
        self.make_task("refinable")
        self.run_cli("task", "refine", "refinable", "--scope", "replacement slice", "--acceptance", "updated", "--validation", "new proof", "--details", '{"risk":"low"}', "--actor", "planner")
        self.run_cli("task", "assign", "refinable", "reviewer", "--actor", "planner")
        task = __import__("json").loads(self._capture_cli("task", "show", "refinable"))
        self.assertEqual(task["scope"], "replacement slice")
        self.assertEqual(task["acceptance"], ["updated"])
        self.assertEqual(task["details"]["validation"], ["new proof"])
        self.assertEqual(task["details"]["risk"], "low")
        self.assertEqual(task["owner"], "reviewer")
        event_types = {row["event_type"] for row in self._all("SELECT event_type FROM task_events WHERE task_id='refinable'")}
        self.assertTrue({"task_refined", "assigned"}.issubset(event_types))

    def test_requeue_records_recovery_and_returns_to_predecessor(self):
        self.make_task("stalled")
        self.run_cli("task", "move", "stalled", "Ready")
        self.run_cli("task", "move", "stalled", "Active")
        self.run_cli("task", "requeue", "stalled", "--reason", "worker lease expired", "--actor", "supervisor")
        self.assertEqual(self.row("SELECT s.name FROM tasks t JOIN task_states s ON s.id=t.state_id WHERE t.id='stalled'")[0], "Ready")
        event = self.row("SELECT event_type, payload_json FROM task_events WHERE task_id='stalled' AND event_type='requeued'")
        self.assertIsNotNone(event)
        self.assertIn("worker lease expired", event["payload_json"])

    def _capture_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli(*args)
        return output.getvalue()

    def test_reviewed_reference_policy_is_enforced_for_custom_state(self):
        self.run_cli("intent", "add", "goal", "Research-backed work")
        self.run_cli("state", "add", "research", "Research", "--position", "15", "--previous", "backlog", "--next", "ready", "--requires-reviewed-references")
        self.run_cli("task", "add", "research-task", "Research task", "--intent", "goal", "--owner", "worker", "--scope", "one slice", "--acceptance", "accepted", "--validation", "validated")
        self.run_cli("reference", "add", "source", "https://example.test/source")
        self.run_cli("reference", "link", "source", "--task-id", "research-task")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "move", "research-task", "research")
        self.run_cli("reference", "review", "source", "reviewed")
        self.run_cli("task", "move", "research-task", "research")
        self.assertEqual(self.row("SELECT state_id FROM tasks WHERE id='research-task'")[0], "research")

    def test_dependency_cycles_are_rejected(self):
        self.make_task("a")
        self.run_cli("task", "add", "b", "B", "--intent", "goal")
        self.run_cli("task", "add", "c", "C", "--intent", "goal")
        self.run_cli("task", "dependency", "add", "a", "b")
        self.run_cli("task", "dependency", "add", "b", "c")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "dependency", "add", "c", "a")

    def test_worker_demand_matches_parallelism_and_work_units(self):
        self.make_task("demand")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "demand", "set", "demand", "--parallelism", "serial", "--min-workers", "1", "--target-workers", "2", "--max-workers", "2", "--reuse-policy", "serial-compatible", "--isolation", "task-bound", "--aggregation", "all-required")
        with self.assertRaises(SystemExit):
            self.run_cli("task", "demand", "set", "demand", "--parallelism", "partitionable", "--min-workers", "1", "--target-workers", "2", "--max-workers", "3", "--work-units", '["one", "two"]', "--reuse-policy", "parallel", "--isolation", "unit-bound", "--aggregation", "all-required")
        self.run_cli("task", "demand", "set", "demand", "--parallelism", "partitionable", "--min-workers", "1", "--target-workers", "2", "--max-workers", "2", "--work-units", '["one", "two"]', "--reuse-policy", "parallel", "--isolation", "unit-bound", "--aggregation", "all-required")
        self.assertEqual(self.row("SELECT max_workers FROM tasks WHERE id='demand'")[0], 2)


if __name__ == "__main__":
    unittest.main()
