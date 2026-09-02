import importlib.util
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "kanban" / "scripts" / "kanban.py"
SPEC = importlib.util.spec_from_file_location("kanban_helper", SCRIPT)
KANBAN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(KANBAN)


class GoalWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "kanban.db"

    def tearDown(self):
        self.tempdir.cleanup()

    def run_cli(self, *args):
        self.assertEqual(KANBAN.main(["--db", str(self.db), *args]), 0)

    def row(self, query, params=()):
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(query, params).fetchone()
        finally:
            connection.close()

    def test_goal_capture_is_valid_without_premature_tasks(self):
        self.run_cli(
            "goal", "capture", "durable-goal", "Deliver a durable outcome",
            "--success-criterion", "Independent evidence accepted",
            "--constraint", "Preserve human authority",
            "--autonomy", "background",
            "--stop-condition", "Permission is missing",
        )
        self.run_cli("validate")
        intent = self.row("SELECT state, raw_json FROM intents WHERE id = ?", ("durable-goal",))
        self.assertEqual(intent["state"], "captured")
        self.assertIn('"autonomy":"background"', intent["raw_json"])

    def test_run_checkins_preserve_progress_and_are_idempotent(self):
        self.run_cli("goal", "capture", "goal", "Track worker progress")
        self.run_cli("run", "start", "run-1", "--intent", "goal", "--worker", "worker-1")
        self.run_cli(
            "run", "checkin", "run-1", "working", "--progress", "started",
            "--next-action", "finish slice", "--expected-next-at", "2000000000",
            "--idempotency-key", "check-1",
        )
        first = self.row(
            "SELECT heartbeat_at, progress_at FROM run_checkins WHERE run_id='run-1'"
        )
        self.run_cli(
            "run", "checkin", "run-1", "working", "--progress", "started",
            "--next-action", "finish slice", "--expected-next-at", "2000000000",
            "--idempotency-key", "check-1",
        )
        replay = self.row(
            "SELECT heartbeat_at, progress_at FROM run_checkins WHERE run_id='run-1'"
        )
        self.assertEqual(dict(first), dict(replay))
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM run_checkins")["n"], 1)

        self.run_cli(
            "run", "checkin", "run-1", "waiting", "--progress", "awaiting input",
            "--blocker", "decision", "--idempotency-key", "check-2",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.run_cli("status")
        status = output.getvalue()
        self.assertIn("state=waiting", status)
        self.assertNotIn("progress_age=unknown", status)
        self.assertIn("blocker=decision", status)

    def test_run_checkin_rejects_reused_key_with_different_content(self):
        self.run_cli("goal", "capture", "goal", "Track worker progress")
        self.run_cli("run", "start", "run-1", "--intent", "goal", "--worker", "worker-1")
        self.run_cli(
            "run", "checkin", "run-1", "working", "--progress", "started",
            "--next-action", "finish slice", "--idempotency-key", "check-1",
        )
        with self.assertRaisesRegex(SystemExit, "2"):
            KANBAN.main([
                "--db", str(self.db), "run", "checkin", "run-1", "working",
                "--progress", "different", "--next-action", "finish slice",
                "--idempotency-key", "check-1",
            ])
        self.assertEqual(
            self.row("SELECT progress_summary FROM run_checkins")["progress_summary"],
            "started",
        )

    def test_default_specialist_registry_is_versioned_and_implementation_neutral(self):
        self.run_cli("specialist", "class", "list")
        connection = KANBAN.connect(self.db)
        try:
            rows = connection.execute(
                "SELECT c.id, c.role_context, c.version, v.version AS stored_version "
                "FROM specialist_classes c JOIN specialist_class_versions v "
                "ON v.specialist_class_id = c.id AND v.version = c.version "
                "ORDER BY c.id"
            ).fetchall()
        finally:
            connection.close()
        expected = {
            "workflow-governance", "workflow-learning", "software-product-discovery",
            "software-architecture", "software-delivery", "software-supply-chain",
            "security-privacy-compliance", "production-operations",
            "systems-compatibility", "systems-diagnostics", "code-conventions",
            "structured-language-engineering", "kubernetes-operations",
            "change-record-quality",
        }
        self.assertEqual({row["id"] for row in rows}, expected)
        for row in rows:
            expected_version = 2 if row["id"] == "change-record-quality" else 1
            self.assertEqual(row["version"], expected_version)
            self.assertEqual(row["stored_version"], expected_version)
            self.assertTrue(row["role_context"].startswith("You are "))
            self.assertNotIn("agentic-delta", row["role_context"])
            self.assertNotIn("agentic-sre", row["role_context"])
            self.assertNotIn("/skills/", row["role_context"])

    def test_default_specialist_registry_preserves_project_local_updates(self):
        self.run_cli(
            "specialist", "class", "update", "software-architecture",
            "Project architecture specialist",
            "You are the project architecture specialist. Enforce the accepted local architecture policy.",
        )
        connection = KANBAN.connect(self.db)
        try:
            KANBAN.init_db(connection, KANBAN.DEFAULT_SCHEMA_PATH)
            row = connection.execute(
                "SELECT title, version FROM specialist_classes WHERE id = ?",
                ("software-architecture",),
            ).fetchone()
            versions = connection.execute(
                "SELECT COUNT(*) FROM specialist_class_versions WHERE specialist_class_id = ?",
                ("software-architecture",),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(dict(row), {"title": "Project architecture specialist", "version": 2})
        self.assertEqual(versions, 2)

    def test_comprehensive_review_defaults_every_class_and_reviewer_may_opt_out(self):
        self.run_cli("goal", "capture", "goal", "Review comprehensively")
        self.run_cli(
            "task", "add", "work", "Review work", "--intent", "goal",
            "--scope", "bounded artifact", "--exit-criterion", "reviewed",
            "--validation", "specialist review", "--owner", "worker",
        )
        self.run_cli(
            "review", "profile", "set", "work", "architecture-design", "Design",
            "--artifact-kind", "design-document", "--classified-by", "coordinator",
            "--rationale", "Architecture design packet",
        )
        self.run_cli("review", "plan", "create", "plan", "work")
        connection = KANBAN.connect(self.db)
        try:
            items = connection.execute(
                "SELECT specialist_class_id, purpose, applicability, status, policy_rule_id "
                "FROM review_plan_items WHERE review_plan_id='plan'"
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(items), 28)
        code_items = {row["purpose"]: row for row in items if row["specialist_class_id"] == "code-conventions"}
        self.assertEqual(code_items["assurance"]["status"], "not-applicable")
        self.assertEqual(code_items["control"]["status"], "not-applicable")
        self.assertIsNotNone(code_items["assurance"]["policy_rule_id"])
        self.run_cli(
            "specialist", "class", "add", "domain-review", "Domain review specialist",
            "You are a domain review specialist. Evaluate domain correctness and state your evidence.",
        )
        self.assertEqual(self.row(
            "SELECT COUNT(*) AS n FROM review_plan_items WHERE review_plan_id='plan'"
        )["n"], 28)

        document = {
            "handoff_id": "style-opt-out", "contract_version": "2",
            "specialist_class": "kubernetes-operations", "specialist_class_version": 1,
            "engagement_role": "review", "worker_id": "style-reviewer",
            "review_purpose": "control",
            "review_plan_item_id": "plan-kubernetes-operations-control",
            "gate_id": "plan-control", "applicability": "not-applicable", "independent": True,
            "intent_id": "goal", "task_id": "work", "run_id": None, "attempt_id": None,
            "scope": "bounded artifact", "permissions_used": [], "sources": [],
            "artifacts_observed": [{"artifact_ref": "design.pdf", "revision": "abc"}],
            "artifacts_changed": [],
            "findings": [{
                "severity": "advisory",
                "summary": "The design has no Kubernetes deployment or cluster interaction surface",
            }],
            "evidence": [], "gate_recommendation": "not-applicable",
            "residual_risks": [], "open_decisions": [], "rework_destination": None,
            "status": "not-applicable",
        }
        path = Path(self.tempdir.name) / "style-opt-out.json"
        path.write_text(json.dumps(document))
        self.run_cli("handoff", "ingest", str(path))
        requirement = self.row(
            "SELECT status, applicability, applicability_source, satisfied_by_handoff_id "
            "FROM review_plan_items WHERE id='plan-kubernetes-operations-control'"
        )
        self.assertEqual(dict(requirement), {
            "status": "not-applicable", "applicability": "not-applicable",
            "applicability_source": "reviewer", "satisfied_by_handoff_id": "style-opt-out",
        })
        self.assertEqual(self.row(
            "SELECT COUNT(*) AS n FROM gate_specialist_requirements "
            "WHERE gate_id IN ('plan-assurance', 'plan-control') AND status='pending'"
        )["n"], 25)

    def test_database_rejects_direct_bypass_of_workflow_invariants(self):
        self.run_cli("goal", "capture", "goal", "Enforce workflow invariants")
        for task_id in ("one", "two"):
            self.run_cli(
                "task", "add", task_id, f"Task {task_id}", "--intent", "goal",
                "--scope", "bounded", "--exit-criterion", "proven",
                "--validation", "direct evidence", "--owner", "worker",
            )
            self.run_cli("task", "move", task_id, "Ready")
        self.run_cli("gate", "require", "independent", "one", "independent-review")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "decision requires"):
                connection.execute(
                    "INSERT INTO decisions(id, question, options_json, created_at) VALUES(?, ?, '[]', ?)",
                    ("orphan", "Unlinked", KANBAN.now()),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "gate type"):
                connection.execute(
                    "INSERT INTO gates(id, task_id, gate_type, updated_at) VALUES('unknown-gate', 'one', 'invented', ?)",
                    (KANBAN.now(),),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "depend on itself"):
                connection.execute(
                    "INSERT INTO task_dependencies(task_id, dependency) VALUES('one', 'one')"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "independent evaluator"):
                connection.execute(
                    "UPDATE gates SET recommendation='pass', execution_status='complete' WHERE id='independent'"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "requires a revision"):
                connection.execute(
                    "INSERT INTO evidence(id, task_id, criterion_id, artifact, revision, probe, result, producer, created_at) "
                    "VALUES('bad-evidence', 'one', '1', 'artifact', '', 'probe', 'pass', 'worker', ?)",
                    (KANBAN.now(),),
                )
            connection.execute(
                "INSERT INTO runs(id, task_id, status, created_at, updated_at) "
                "VALUES('direct-run', 'one', 'active', ?, ?)",
                (KANBAN.now(), KANBAN.now()),
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "network policy"):
                connection.execute(
                    "INSERT INTO autonomy_envelopes(run_id, policy_json, policy_hash, granted_by, created_at) "
                    "VALUES('direct-run', '{}', 'invalid', 'worker', ?)",
                    (KANBAN.now(),),
                )
            connection.execute("DELETE FROM runs WHERE id='direct-run'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "unfinished work"):
                connection.execute(
                    "UPDATE intents SET state='closed', closure='realized' WHERE id='goal'"
                )
            connection.execute("UPDATE tasks SET column_name='Active' WHERE id='one'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "WIP limit"):
                connection.execute("UPDATE tasks SET column_name='Active' WHERE id='two'")
            connection.rollback()
        finally:
            connection.close()

    def test_assurance_precedes_active_and_control_precedes_done(self):
        self.run_cli("goal", "capture", "goal", "Deliver reviewed work")
        self.run_cli(
            "task", "add", "work", "Implement safely", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "reviewed",
            "--validation", "assurance and control", "--owner", "worker",
        )
        self.run_cli("task", "move", "work", "Ready")
        connection = KANBAN.connect(self.db)
        try:
            connection.execute(
                "UPDATE specialist_classes SET active=0 WHERE id <> 'security-privacy-compliance'"
            )
            connection.commit()
        finally:
            connection.close()
        self.run_cli(
            "review", "profile", "set", "work", "implementation", "Implement",
            "--artifact-kind", "source-code", "--risk-attribute", "identity",
            "--classified-by", "coordinator", "--rationale", "Security-sensitive implementation",
        )
        self.run_cli("review", "plan", "create", "plan", "work")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "assurance review"):
                KANBAN.task_move(connection, "work", "Active", None)
        finally:
            connection.close()

        def ingest(purpose, role, gate, independent, evidence_id, criterion):
            document = {
                "handoff_id": f"{purpose}-handoff", "contract_version": "2",
                "specialist_class": "security-privacy-compliance", "specialist_class_version": 1,
                "engagement_role": role, "review_purpose": purpose,
                "review_plan_item_id": f"plan-security-privacy-compliance-{purpose}",
                "worker_id": f"{purpose}-worker", "gate_id": gate,
                "applicability": "applicable", "independent": independent,
                "intent_id": "goal", "task_id": "work", "run_id": None, "attempt_id": None,
                "scope": "one component", "permissions_used": [], "sources": [],
                "artifacts_observed": [{"artifact_ref": "src/component", "revision": "abc"}],
                "artifacts_changed": [],
                "findings": [{"severity": "advisory", "summary": f"{purpose} criteria satisfied"}],
                "obligations": ([
                    {
                        "obligation_id": "obligation-assurance-work",
                        "tenet_id": "assurance-becomes-work",
                        "obligation_type": "design-constraint",
                        "summary": "Apply the security assurance constraints during implementation",
                        "affected_artifact": "src/component",
                        "lifecycle_stage": "Implement",
                        "verification_method": "independent control evidence",
                        "owner": "worker",
                    },
                    {
                        "obligation_id": "obligation-fast-feedback",
                        "tenet_id": "fast-feedback-at-source",
                        "obligation_type": "test",
                        "summary": "Run the selected security check while producing the component",
                        "affected_artifact": "src/component",
                        "lifecycle_stage": "Implement",
                        "verification_method": "reproducible security test",
                        "owner": "worker",
                    },
                ] if purpose == "assurance" else []),
                "evidence": [{
                    "evidence_id": evidence_id, "criterion_id": criterion,
                    "artifact": "src/component", "revision": "abc", "probe": f"{purpose} review",
                    "result": "pass", "producer": f"{purpose}-worker",
                }],
                "gate_recommendation": "pass", "residual_risks": [], "open_decisions": [],
                "rework_destination": None, "status": "complete",
            }
            path = Path(self.tempdir.name) / f"{purpose}.json"
            path.write_text(json.dumps(document))
            self.run_cli("handoff", "ingest", str(path))

        ingest("assurance", "inform", "plan-assurance", False, "assurance-proof", "assurance")
        self.run_cli("task", "move", "work", "Active")
        self.run_cli("task", "move", "work", "Review")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                KANBAN.task_move(connection, "work", "Done", None)
        finally:
            connection.close()
        ingest("control", "review", "plan-control", True, "control-proof", "reviewed")
        self.run_cli("obligation", "satisfy", "obligation-assurance-work", "control-proof")
        self.run_cli("obligation", "satisfy", "obligation-fast-feedback", "control-proof")
        self.run_cli("task", "move", "work", "Done")
        self.assertEqual(self.row("SELECT status FROM review_plans WHERE id='plan'")["status"], "complete")

    def test_versioned_tenets_freeze_project_guidance_and_support_experiments(self):
        self.run_cli("goal", "capture", "goal", "Improve governed delivery")
        self.run_cli(
            "task", "add", "work", "Implement with guidance", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "proven",
            "--validation", "guided evidence", "--owner", "worker",
        )
        self.run_cli(
            "tenet", "store", "project-contract-check", "quality", "Project contract check",
            "Run the project contract check while changing its public interface",
            "--effect", "Interface drift is exposed at its source",
            "--verification", "contract test evidence", "--principle", "built-in-quality",
        )
        self.run_cli(
            "review", "profile", "set", "work", "implementation", "Implement",
            "--artifact-kind", "public-sdk", "--classified-by", "coordinator",
            "--rationale", "Public interface implementation",
        )
        self.run_cli("review", "plan", "create", "plan", "work")
        snapshot = self.row(
            "SELECT status, scope_hash, guidance_hash FROM guidance_snapshots WHERE id='plan-guidance'"
        )
        self.assertEqual(snapshot["status"], "frozen")
        self.assertTrue(snapshot["guidance_hash"].startswith("sha256:"))
        item = self.row(
            "SELECT tenet_version, disposition, resolution FROM guidance_snapshot_tenets "
            "WHERE guidance_snapshot_id='plan-guidance' AND tenet_id='project-contract-check'"
        )
        self.assertEqual(dict(item), {"tenet_version": 1, "disposition": "required", "resolution": "pending"})

        self.run_cli(
            "tenet", "store", "project-contract-check", "quality", "Project contract check",
            "Run the project contract and compatibility checks while changing its public interface",
            "--effect", "Interface and compatibility drift are exposed at their source",
            "--verification", "contract and compatibility evidence", "--principle", "built-in-quality",
        )
        self.assertEqual(self.row(
            "SELECT tenet_version FROM guidance_snapshot_tenets "
            "WHERE guidance_snapshot_id='plan-guidance' AND tenet_id='project-contract-check'"
        )["tenet_version"], 1)
        self.assertEqual(self.row(
            "SELECT current_version FROM tenets WHERE id='project-contract-check'"
        )["current_version"], 2)
        self.run_cli(
            "tenet", "store", "contract-check-variant", "quality", "Contract check variant",
            "Run a generated compatibility matrix while changing the public interface",
            "--effect", "The experiment may expose more drift with acceptable latency",
            "--verification", "matrix result and cycle-time evidence", "--principle", "built-in-quality",
            "--draft",
        )
        self.run_cli(
            "experiment", "add", "contract-variant", "built-in-quality",
            "fast-feedback-at-source", "contract-check-variant",
            "Contract drift escapes too late", "The project check reduces escaped drift",
            '{"work_type":"implementation"}', '["security-sensitive work"]',
            '["first-pass acceptance","cycle time"]', "--owner", "workflow-learning",
            "--rollback-condition", "escaped defects or cycle time worsen",
        )
        self.assertEqual(self.row(
            "SELECT status FROM improvement_experiments WHERE id='contract-variant'"
        )["status"], "draft")
        self.run_cli("experiment", "status", "contract-variant", "running")
        self.run_cli(
            "task", "add", "experiment-work", "Run variant", "--intent", "goal",
            "--scope", "experimental slice", "--exit-criterion", "measured",
            "--validation", "experiment metrics", "--owner", "worker",
        )
        self.run_cli("experiment", "assign", "contract-variant", "experiment-work", "variant")
        self.run_cli(
            "review", "profile", "set", "experiment-work", "implementation", "Implement",
            "--artifact-kind", "public-sdk", "--classified-by", "coordinator",
            "--rationale", "Assigned experiment slice",
        )
        self.run_cli("review", "plan", "create", "experiment-plan", "experiment-work")
        self.assertEqual(self.row(
            "SELECT tenet_version FROM guidance_snapshot_tenets "
            "WHERE guidance_snapshot_id='experiment-plan-guidance' AND tenet_id='contract-check-variant'"
        )["tenet_version"], 1)
        self.assertIsNone(self.row(
            "SELECT tenet_version FROM guidance_snapshot_tenets "
            "WHERE guidance_snapshot_id='experiment-plan-guidance' AND tenet_id='fast-feedback-at-source'"
        ))
        self.run_cli(
            "constraint", "set", "review-capacity", "goal", "resource", "specialist-review",
            "--evidence", "review wait dominates cycle time", "--exploit", "protect reviewer focus",
            "--subordinate", "do not start more implementation", "--owner", "coordinator",
            "--buffer-target", "2", "--buffer-current", "4",
        )
        self.assertEqual(self.row(
            "SELECT status FROM flow_constraints WHERE id='review-capacity'"
        )["status"], "active")
        self.run_cli(
            "quality-signal", "open", "bad-assumption", "work", "process-failure",
            "stop-affected-work", "A governing assumption is invalid",
            "--containment", "hold affected implementation", "--owner", "coordinator",
        )
        self.run_cli(
            "quality-signal", "resolve", "bad-assumption",
            "--occurrence-cause", "unstated premise", "--escape-cause", "missing premise check",
            "--systemic-cause", "guidance omitted premise validation",
            "--countermeasure", "add premise validation to the tenet",
            "--recurrence-test", "repeat the profile classification case",
        )
        self.assertEqual(self.row(
            "SELECT status FROM quality_signals WHERE id='bad-assumption'"
        )["status"], "resolved")

        connection = KANBAN.connect(self.db)
        try:
            connection.execute(
                "UPDATE task_work_profiles SET scope_hash='sha256:changed' WHERE task_id='work'"
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(self.row(
            "SELECT status FROM guidance_snapshots WHERE id='plan-guidance'"
        )["status"], "stale")

    def test_early_specialist_enrollment_codebase_review_guidance_and_bug_flow(self):
        self.run_cli("goal", "capture", "product", "Deliver a reliable product")
        self.assertEqual(self.row(
            "SELECT COUNT(*) AS n FROM project_specialist_enrollments WHERE intent_id='product'"
        )["n"], 14)
        self.run_cli(
            "codebase-review", "start", "baseline-review", "product", "repository at revision abc",
        )
        self.assertEqual(self.row(
            "SELECT COUNT(*) AS n FROM review_plan_items WHERE review_plan_id='baseline-review-plan'"
        )["n"], 28)
        handoff = {
            "handoff_id": "security-guidance", "contract_version": "2",
            "specialist_class": "security-privacy-compliance", "specialist_class_version": 1,
            "engagement_role": "inform", "review_purpose": "assurance",
            "review_plan_item_id": "baseline-review-plan-security-privacy-compliance-assurance",
            "worker_id": "security-specialist", "gate_id": "baseline-review-plan-assurance",
            "applicability": "applicable", "independent": False,
            "intent_id": "product", "task_id": "baseline-review", "run_id": None, "attempt_id": None,
            "scope": "repository at revision abc", "permissions_used": [], "sources": [],
            "artifacts_observed": [{"artifact_ref": "repository", "revision": "abc"}],
            "artifacts_changed": [],
            "findings": [{"severity": "required-follow-up", "summary": "Trust boundaries need an explicit project rule"}],
            "guidance_proposals": [{
                "proposal_id": "trust-boundary-tenet", "guidance_kind": "tenet",
                "theme": "security", "title": "Declare trust boundaries",
                "statement": "Declare and test every external trust boundary before implementation",
                "intended_outcome": "Untrusted inputs receive explicit controls at their entry point",
                "rationale": "The existing codebase crosses implicit trust boundaries",
                "applicability": {"risk_attributes_any": ["external-input"]},
                "verification_strategy": "threat model and boundary tests",
            }],
            "obligations": [{
                "obligation_id": "review-trust-boundaries", "tenet_id": "assurance-becomes-work",
                "obligation_type": "design-constraint", "summary": "Inventory current trust boundaries",
                "affected_artifact": "repository", "lifecycle_stage": "Verify",
                "verification_method": "revision-bound trust-boundary review", "owner": "security-specialist",
            }],
            "evidence": [{
                "evidence_id": "security-review-evidence", "criterion_id": "trust-boundaries",
                "artifact": "repository", "revision": "abc", "probe": "security codebase review",
                "result": "pass", "producer": "security-specialist",
            }],
            "gate_recommendation": "pass", "residual_risks": [], "open_decisions": [],
            "rework_destination": None, "status": "complete",
        }
        handoff_path = Path(self.tempdir.name) / "security-guidance.json"
        handoff_path.write_text(json.dumps(handoff))
        self.run_cli("handoff", "ingest", str(handoff_path))
        self.assertEqual(self.row(
            "SELECT status FROM specialist_guidance_proposals WHERE id='trust-boundary-tenet'"
        )["status"], "proposed")
        self.assertEqual(self.row(
            "SELECT status FROM project_specialist_enrollments WHERE intent_id='product' "
            "AND specialist_class_id='security-privacy-compliance'"
        )["status"], "consulted")

        self.run_cli(
            "bug", "register", "login-loop", "product", "Login redirects forever",
            "--observed", "Successful login returns to the login page",
            "--expected", "Successful login opens the account page", "--reporter", "user",
            "--reproduction", "Log in with a valid account", "--evidence", "trace:login-loop",
        )
        self.assertEqual(self.row(
            "SELECT COUNT(*) AS n FROM bug_specialist_assessments WHERE bug_id='login-loop'"
        )["n"], 14)
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "every enrolled specialist"):
                connection.execute(
                    "UPDATE bugs SET status='prioritized', priority_rank=1, priority_rationale='customer blocker' "
                    "WHERE id='login-loop'"
                )
            connection.rollback()
        finally:
            connection.close()
        classes = []
        connection = KANBAN.connect(self.db)
        try:
            classes = [row[0] for row in connection.execute(
                "SELECT specialist_class_id FROM bug_specialist_assessments WHERE bug_id='login-loop' ORDER BY specialist_class_id"
            )]
        finally:
            connection.close()
        for class_id in classes:
            if class_id == "security-privacy-compliance":
                self.run_cli(
                    "bug", "assess", "login-loop", class_id, "applicable",
                    "--rationale", "Authentication flow affects trust and availability",
                    "--assessed-by", "security-reviewer", "--goal-impact", "95", "--urgency", "90",
                    "--risk-summary", "Users cannot access the product",
                )
            else:
                self.run_cli(
                    "bug", "assess", "login-loop", class_id, "not-applicable",
                    "--rationale", "No material concern within this specialist scope",
                    "--assessed-by", f"{class_id}-reviewer",
                )
        self.run_cli("bug", "prioritize", "login-loop", "1", "--rationale", "Blocks the product goal for all users")
        self.run_cli("bug", "action", "login-loop", "fix-login-loop", "--owner", "worker")
        bug = self.row("SELECT status, action_task_id FROM bugs WHERE id='login-loop'")
        self.assertEqual(dict(bug), {"status": "actioned", "action_task_id": "fix-login-loop"})
        self.assertTrue(self.row(
            "SELECT priority FROM tasks WHERE id='fix-login-loop'"
        )["priority"].startswith("rank 1:"))

    def test_decision_requires_link_and_preserves_resolution_rationale(self):
        self.run_cli("goal", "capture", "durable-goal", "Deliver a durable outcome")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                KANBAN.decision_add(
                    connection, "orphan", "Unlinked question",
                    None, None, [], None, None,
                )
        finally:
            connection.close()
        self.run_cli(
            "decision", "add", "public-interface", "Choose the public interface",
            "--intent", "durable-goal", "--option", "CLI", "--option", "API",
            "--default", "CLI", "--impact", "Implementation waits",
        )
        self.run_cli(
            "decision", "resolve", "public-interface", "CLI",
            "--rationale", "Matches the existing helper", "--decided-by", "user",
        )
        decision = self.row(
            "SELECT status, answer, rationale, decided_by FROM decisions WHERE id = ?",
            ("public-interface",),
        )
        self.assertEqual(dict(decision), {
            "status": "resolved",
            "answer": "CLI",
            "rationale": "Matches the existing helper",
            "decided_by": "user",
        })

    def test_factual_clarification_can_be_resolved(self):
        self.run_cli("clarify", "add", "Which runtime?", "--default", "Python")
        self.run_cli("clarify", "answer", "1", "Python")
        clarification = self.row(
            "SELECT status, answer FROM clarifications WHERE id = 1"
        )
        self.assertEqual(dict(clarification), {"status": "resolved", "answer": "Python"})

    def test_source_revisions_preserve_historical_context(self):
        common = (
            "https://example.test/standard", "--title", "Example Standard",
            "--publisher", "Example Body", "--type", "standard",
            "--published-at", "2026-01-01", "--topic", "workflow",
        )
        self.run_cli("reference", "add", "standard-v1", *common, "--content-hash", "sha256:v1")
        self.run_cli(
            "reference", "review", "standard-v1", "--summary", "Initial guidance",
            "--relevance", "Defines workflow", "--constraints", "Version one",
        )
        self.run_cli("reference", "add", "standard-v2", *common, "--content-hash", "sha256:v2")
        connection = sqlite3.connect(self.db)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM research_references WHERE url = ?",
                ("https://example.test/standard",),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 2)

    def test_autonomous_run_requires_immutable_envelope_before_active(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Implement slice", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "works",
            "--validation", "run test", "--owner", "worker",
        )
        self.run_cli("task", "move", "slice", "Ready")
        self.run_cli("run", "start", "run-1", "--task", "slice", "--worker", "worker")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                KANBAN.task_move(connection, "slice", "Active", None)
        finally:
            connection.close()
        policy = {
            "mode": "bounded-agent", "allowed_tools": ["apply_patch"],
            "allowed_paths": ["src"], "network_policy": "deny", "max_steps": 20,
            "max_duration_seconds": 900, "max_retries": 2, "max_concurrency": 1,
            "approval_required": ["commit"], "stop_conditions": ["budget exhausted"],
        }
        self.run_cli("run", "envelope", "run-1", KANBAN.json_dumps(policy), "--granted-by", "user")
        self.run_cli("task", "move", "slice", "Active")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                KANBAN.envelope_set(connection, "run-1", KANBAN.json_dumps(policy), "worker")
        finally:
            connection.close()

    def test_required_gates_and_revision_bound_evidence_control_done(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Implement slice", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "works",
            "--validation", "run test", "--owner", "worker",
        )
        self.run_cli("task", "move", "slice", "Ready")
        self.run_cli("task", "move", "slice", "Active")
        self.run_cli("gate", "require", "review", "slice", "design-validation")
        self.run_cli("task", "move", "slice", "Review")
        connection = KANBAN.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                KANBAN.task_move(connection, "slice", "Done", None)
        finally:
            connection.close()
        self.run_cli(
            "evidence", "add", "proof", "slice", "1", "src/component", "abc123",
            "unit test", "pass", "--producer", "worker", "--gate", "review",
        )
        self.run_cli("gate", "record", "review", "pass", "--evaluator", "reviewer", "--independent")
        self.run_cli("task", "conformance", "slice")
        self.run_cli("task", "move", "slice", "Done")
        self.run_cli("intent", "status", "goal", "closed", "--closure", "realized")

    def test_gate_registry_covers_product_to_production_lifecycle(self):
        expected = {
            "product-contract", "research-readiness", "architecture",
            "design-validation", "implementation-verification",
            "security-design", "security-release", "supply-chain",
            "independent-review", "delivery", "production-readiness",
            "operational-observation",
        }
        connection = KANBAN.connect(self.db)
        try:
            KANBAN.init_db(connection, KANBAN.DEFAULT_SCHEMA_PATH)
            registered = {
                row["id"] for row in connection.execute(
                    "SELECT id FROM gate_types WHERE active = 1"
                )
            }
        finally:
            connection.close()
        self.assertTrue(expected.issubset(registered))

    def test_handoff_ingest_is_validated_normalized_atomic_and_idempotent(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Design slice", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "works",
            "--validation", "review design", "--owner", "architect",
        )
        self.run_cli("gate", "require", "architecture", "slice", "architecture")
        self.run_cli(
            "specialist", "class", "add", "architecture-design",
            "Software architecture specialist",
            "You are a software architecture specialist. Evaluate boundaries, contracts, quality attributes, and tradeoffs.",
        )
        self.run_cli(
            "specialist", "gate", "require", "architecture", "architecture-design", "produce",
            "--rationale", "The design gate needs architecture expertise",
        )
        document = {
            "handoff_id": "handoff-1",
            "contract_version": "2",
            "specialist_class": "architecture-design",
            "specialist_class_version": 1,
            "engagement_role": "produce",
            "worker_id": "worker-architect",
            "gate_id": "architecture",
            "applicability": "applicable",
            "independent": False,
            "intent_id": "goal",
            "task_id": "slice",
            "run_id": None,
            "attempt_id": None,
            "scope": "one component",
            "permissions_used": [],
            "sources": [{
                "title": "Architecture description",
                "publisher": "Standards body",
                "url": "https://example.test/architecture",
            }],
            "artifacts_observed": [{"artifact_ref": "requirements.md", "revision": "abc"}],
            "artifacts_changed": [{"artifact_ref": "architecture.md", "revision": "def"}],
            "findings": [{"severity": "advisory", "summary": "Design satisfies the slice"}],
            "evidence": [{
                "evidence_id": "handoff-proof",
                "criterion_id": "1",
                "artifact": "architecture.md",
                "revision": "def",
                "probe": "independent scenario review",
                "result": "pass",
                "producer": "worker-architect",
            }],
            "gate_recommendation": "pass",
            "residual_risks": [{
                "summary": "External dependency remains",
                "owner": "team",
                "acceptance_required": False,
            }],
            "open_decisions": [],
            "rework_destination": None,
            "status": "complete",
        }
        path = Path(self.tempdir.name) / "handoff.json"
        path.write_text(json.dumps(document))
        self.run_cli("handoff", "validate", str(path), "--expected-task", "slice")
        self.run_cli("handoff", "ingest", str(path), "--expected-task", "slice")
        self.run_cli("handoff", "ingest", str(path), "--expected-task", "slice")
        handoff = self.row(
            "SELECT recommendation, execution_status, document_hash FROM specialist_handoffs WHERE id = ?",
            ("handoff-1",),
        )
        self.assertEqual(handoff["recommendation"], "pass")
        self.assertEqual(handoff["execution_status"], "complete")
        self.assertTrue(handoff["document_hash"].startswith("sha256:"))
        gate = self.row(
            "SELECT recommendation, execution_status, evaluator FROM gates WHERE id = ?",
            ("architecture",),
        )
        self.assertEqual(dict(gate), {
            "recommendation": "pass",
            "execution_status": "complete",
            "evaluator": "worker-architect",
        })
        requirement = self.row(
            "SELECT status, satisfied_by_handoff_id FROM gate_specialist_requirements "
            "WHERE gate_id = ? AND specialist_class_id = ? AND engagement_role = ?",
            ("architecture", "architecture-design", "produce"),
        )
        self.assertEqual(dict(requirement), {
            "status": "satisfied",
            "satisfied_by_handoff_id": "handoff-1",
        })
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM handoff_sources")["n"], 1)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM handoff_evidence")["n"], 1)
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM handoff_receipts")["n"], 1)
        self.assertEqual(
            self.row("SELECT COUNT(*) AS n FROM learning_events WHERE event_type = 'handoff.ingested'")["n"],
            1,
        )

        invalid = dict(document)
        invalid["handoff_id"] = "handoff-invalid"
        invalid["evidence"] = []
        invalid_path = Path(self.tempdir.name) / "invalid-handoff.json"
        invalid_path.write_text(json.dumps(invalid))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            KANBAN.main(["--db", str(self.db), "handoff", "ingest", str(invalid_path)])
        self.assertIsNone(self.row("SELECT id FROM specialist_handoffs WHERE id = ?", ("handoff-invalid",)))

        conflict = json.loads(json.dumps(document))
        conflict["handoff_id"] = "handoff-conflict"
        conflict_path = Path(self.tempdir.name) / "conflict-handoff.json"
        conflict_path.write_text(json.dumps(conflict))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            KANBAN.main(["--db", str(self.db), "handoff", "ingest", str(conflict_path)])
        self.assertIsNone(self.row("SELECT id FROM specialist_handoffs WHERE id = ?", ("handoff-conflict",)))
        self.assertEqual(self.row("SELECT COUNT(*) AS n FROM handoff_sources")["n"], 1)

    def test_not_applicable_gate_and_side_effect_receipt_are_durable(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Inspect only", "--intent", "goal",
            "--scope", "one component", "--exit-criterion", "observed",
            "--validation", "inspect", "--owner", "worker",
        )
        self.run_cli("run", "start", "run-1", "--task", "slice", "--worker", "worker")
        self.run_cli(
            "receipt", "add", "receipt-1", "run-1", "inspect-1", "read", "component",
            "applied", "--receipt", "observation stored",
        )
        self.run_cli(
            "gate", "require", "security", "slice", "security", "--not-applicable",
            "--rationale", "No security-sensitive surface changed",
        )
        receipt = self.row(
            "SELECT status, idempotency_key FROM side_effect_receipts WHERE id = ?",
            ("receipt-1",),
        )
        self.assertEqual(dict(receipt), {"status": "applied", "idempotency_key": "inspect-1"})
        gate = self.row(
            "SELECT applicability, recommendation, execution_status FROM gates WHERE id = ?",
            ("security",),
        )
        self.assertEqual(dict(gate), {
            "applicability": "not-applicable",
            "recommendation": "not-applicable",
            "execution_status": "not-applicable",
        })

    def test_gate_waits_for_all_dynamically_assigned_specialist_classes(self):
        self.run_cli("goal", "capture", "goal", "Validate a SaaS design")
        self.run_cli(
            "task", "add", "design", "Review design", "--intent", "goal",
            "--scope", "service design", "--exit-criterion", "design accepted",
            "--validation", "specialist review", "--owner", "coordinator",
        )
        self.run_cli("gate", "require", "design-review", "design", "design-validation")
        classes = (
            (
                "systems-security", "Systems security specialist",
                "You are a systems security specialist. Evaluate trust boundaries and deterministic controls.",
                "inform", False,
            ),
            (
                "saas-production-operations", "SaaS production operations specialist",
                "You are a specialist in production operations for SaaS products. Evaluate operability and recovery.",
                "review", True,
            ),
        )
        for class_id, title, context, role, _ in classes:
            self.run_cli("specialist", "class", "add", class_id, title, context)
            self.run_cli(
                "specialist", "gate", "require", "design-review", class_id, role,
                "--rationale", f"Need {title.lower()}",
            )
        self.run_cli(
            "specialist", "class", "update", "systems-security",
            "Systems security specialist",
            "You are a systems security specialist. Evaluate trust, controls, and adversarial behavior.",
        )
        connection = KANBAN.connect(self.db)
        try:
            row = connection.execute(
                "SELECT v.role_context, r.specialist_class_version, c.version AS current_version "
                "FROM gate_specialist_requirements r "
                "JOIN specialist_class_versions v ON v.specialist_class_id = r.specialist_class_id "
                "AND v.version = r.specialist_class_version "
                "JOIN specialist_classes c ON c.id = r.specialist_class_id "
                "WHERE r.gate_id = ? AND r.specialist_class_id = ?",
                ("design-review", "systems-security"),
            ).fetchone()
            self.assertTrue(row["role_context"].startswith("You are a systems security specialist"))
            self.assertEqual(row["specialist_class_version"], 1)
            self.assertEqual(row["current_version"], 2)
            old = connection.execute(
                "SELECT role_context FROM specialist_class_versions WHERE specialist_class_id = ? AND version = 1",
                ("systems-security",),
            ).fetchone()
            self.assertIn("deterministic controls", old["role_context"])
        finally:
            connection.close()

        for index, (class_id, _, _, role, independent) in enumerate(classes, start=1):
            document = {
                "handoff_id": f"specialist-{index}",
                "contract_version": "2",
                "specialist_class": class_id,
                "specialist_class_version": 1,
                "engagement_role": role,
                "worker_id": f"worker-{index}",
                "gate_id": "design-review",
                "applicability": "applicable",
                "independent": independent,
                "intent_id": "goal",
                "task_id": "design",
                "run_id": None,
                "attempt_id": None,
                "scope": "service design",
                "permissions_used": [],
                "sources": [],
                "artifacts_observed": [{"artifact_ref": "design.md", "revision": "abc"}],
                "artifacts_changed": [],
                "findings": [{"severity": "advisory", "summary": f"{class_id} accepts the design"}],
                "evidence": [{
                    "evidence_id": f"specialist-proof-{index}",
                    "criterion_id": f"specialist-{index}",
                    "artifact": "design.md",
                    "revision": "abc",
                    "probe": f"{class_id} evaluation",
                    "result": "pass",
                    "producer": f"worker-{index}",
                }],
                "gate_recommendation": "pass",
                "residual_risks": [],
                "open_decisions": [],
                "rework_destination": None,
                "status": "complete",
            }
            path = Path(self.tempdir.name) / f"specialist-{index}.json"
            path.write_text(json.dumps(document))
            self.run_cli("handoff", "ingest", str(path))
            gate = self.row(
                "SELECT recommendation, execution_status FROM gates WHERE id = ?",
                ("design-review",),
            )
            expected = (
                {"recommendation": "pending", "execution_status": "pending"}
                if index == 1 else
                {"recommendation": "pass", "execution_status": "complete"}
            )
            self.assertEqual(dict(gate), expected)

    def test_task_state_and_learning_event_are_linked_atomically(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Implement slice", "--intent", "goal",
            "--scope", "component", "--exit-criterion", "works",
            "--validation", "test", "--owner", "worker",
        )
        event = self.row(
            "SELECT le.task_id, le.event_type, le.source_task_event_id "
            "FROM learning_events le WHERE le.task_id = ? AND le.event_type = 'created'",
            ("slice",),
        )
        self.assertEqual(event["task_id"], "slice")
        self.assertIsNone(event["source_task_event_id"])

        connection = KANBAN.connect(self.db)
        before = connection.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0]
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                with KANBAN.write_transaction(connection):
                    connection.execute(
                        "INSERT INTO learning_events(occurred_at, event_type, reason_summary, task_id) VALUES(?, ?, ?, ?)",
                        (KANBAN.now(), "test.atomic", "must roll back", "slice"),
                    )
                    connection.execute(
                        "INSERT INTO learning_events(occurred_at, event_type, reason_summary, task_id) VALUES(?, ?, ?, ?)",
                        (KANBAN.now(), "invalid", "invalid reference", "missing-task"),
                    )
            after = connection.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0]
            self.assertEqual(after, before)
            rolled_back = connection.execute(
                "SELECT COUNT(*) FROM learning_events WHERE event_type = 'test.atomic'"
            ).fetchone()[0]
            self.assertEqual(rolled_back, 0)
        finally:
            connection.close()

    def test_metric_snapshots_preserve_derivation_version(self):
        self.run_cli("metric", "snapshot", "--scope-type", "project", "--scope-id", "repo")
        row = self.row(
            "SELECT COUNT(*) AS count, MIN(derivation_version) AS version "
            "FROM metric_snapshots WHERE scope_id = ?",
            ("repo",),
        )
        self.assertEqual(row["count"], 8)
        self.assertEqual(row["version"], "1")

    def test_init_backfills_legacy_task_events_idempotently(self):
        self.run_cli("goal", "capture", "goal", "Deliver outcome")
        self.run_cli(
            "task", "add", "slice", "Implement slice", "--intent", "goal",
            "--scope", "component", "--exit-criterion", "works",
            "--validation", "test", "--owner", "worker",
        )
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                "INSERT INTO task_events(task_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
                ("slice", "legacy.created", "legacy event", KANBAN.now()),
            )
            connection.execute("DELETE FROM learning_events")
            connection.commit()
        finally:
            connection.close()
        self.run_cli("init")
        first = self.row("SELECT COUNT(*) AS count FROM learning_events")["count"]
        self.run_cli("init")
        second = self.row("SELECT COUNT(*) AS count FROM learning_events")["count"]
        self.assertGreater(first, 0)
        self.assertEqual(second, first)


if __name__ == "__main__":
    unittest.main()
