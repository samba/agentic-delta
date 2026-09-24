import json
import re
import unittest
from pathlib import Path


DELTA = Path(__file__).resolve().parents[1]
SRE = DELTA.parent / "agentic-sre"


class CrossSuiteSemanticsTest(unittest.TestCase):
    def test_delta_owns_the_only_handoff_schema(self):
        self.assertFalse((DELTA / "skills/kanban/references/specialist-handoff.schema.json").exists())
        self.assertTrue((DELTA / "skills/kanban/references/coordination-protocol.md").exists())
        self.assertFalse((SRE / "docs/specialist-handoff.schema.json").exists())

    def test_sre_skills_are_independently_packaged(self):
        link_pattern = re.compile(r"\[[^]]*\]\(([^)]+)\)")
        for skill in (SRE / "skills").iterdir():
            if not skill.is_dir():
                continue
            files = list(skill.rglob("*.md")) + list(skill.rglob("*.yaml"))
            self.assertTrue((skill / "SKILL.md").is_file(), skill)
            for path in files:
                text = path.read_text()
                self.assertNotIn("../../docs/", text, path)
                self.assertNotIn("../../../docs/", text, path)
                for target in link_pattern.findall(text):
                    if target.startswith(("https://", "http://", "#", "mailto:")):
                        continue
                    resolved = (path.parent / target.split("#", 1)[0]).resolve()
                    self.assertTrue(resolved.is_relative_to(skill.resolve()), (path, target))
                    self.assertTrue(resolved.exists(), (path, target))

    def test_lifecycle_specialists_use_canonical_gate_results(self):
        names = (
            "software-product-discovery",
            "software-architecture",
            "software-delivery",
            "software-supply-chain",
            "production-readiness",
        )
        legacy = (
            "product-contract-pass",
            "architecture-pass",
            "implementation-pass",
            "supply-chain-pass",
            "operational-ready",
        )
        for name in names:
            path = SRE / "skills" / name / "SKILL.md"
            text = path.read_text()
            self.assertIn("version 2", text.lower(), name)
            self.assertIn("gate_id:", text, name)
            for value in legacy:
                self.assertNotIn(value, text, name)

    def test_smart_commits_partitions_with_context_without_claiming_authority(self):
        skill = (SRE / "skills/smart-commits/SKILL.md").read_text()
        partition = (
            SRE / "skills/smart-commits/references/working-draft-partitioning.md"
        ).read_text()
        partition_lower = partition.lower()
        self.assertIn("working draft contains multiple topics", skill)
        self.assertIn("thread history", partition_lower)
        self.assertIn("evidence of intent, not authority or proof", partition_lower)
        self.assertIn("preserve uncertain pre-existing work", partition_lower)
        self.assertIn("never use broad staging", partition_lower)
        self.assertIn("exact staged snapshot", partition_lower)
        self.assertIn("stop on validation failure", partition_lower)

    def test_every_conditional_kanban_reference_exists(self):
        expected = (
            "commands.md",
            "coordination-protocol.md",
            "pull-flow.md",
            "source-register.md",
        )
        root = DELTA / "skills/kanban/references"
        for name in expected:
            self.assertTrue((root / name).is_file(), name)

    def test_kanban_command_cookbook_keeps_common_operational_examples(self):
        commands = (DELTA / "skills/kanban/references/commands.md").read_text()
        for example in (
            "status --json",
            "task refine",
            "task requeue",
            "pull next",
            "review check record",
            "evidence add",
            "state set <state-id-or-name> --wip-limit <n>",
        ):
            self.assertIn(example, commands)

    def test_normative_invariants_remain_enforced_or_owned(self):
        guidance = (DELTA / "skills/kanban/SKILL.md").read_text()
        coordination = (DELTA / "skills/kanban/references/coordination-protocol.md").read_text()
        schema = (DELTA / "skills/kanban/scripts/schema.sql").read_text()
        self.assertIn("Capture the intent", guidance)
        self.assertIn("Research the intent", guidance)
        self.assertIn("terminal state", guidance)
        self.assertIn("Recovery", coordination)
        self.assertIn("Lease renewal", coordination)
        for table in (
            "meta", "task_states", "tasks", "task_intents", "task_dependencies",
            "task_events", "intents", "research_references", "reference_intents",
            "reference_tasks", "specialist_roles", "task_checks", "evidence",
            "guidance", "guidance_references", "pull_capacity_leases",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)
        for table in (
            "backlog_ideas", "bugs", "runs", "run_checkins", "learning_events",
            "principles", "tenets", "review_plans", "specialist_handoffs",
            "task_worker_demands", "gates",
        ):
            self.assertNotIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)

    def test_background_work_drains_review_lanes_and_queue(self):
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        pull_flow = (DELTA / "skills/kanban/references/pull-flow.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        for text in (kanban, workstream):
            self.assertIn("pullable", text)
            self.assertIn("serial", text)
        self.assertIn("backpressure", pull_flow.lower())
        self.assertIn("parallel", kanban)
        self.assertIn("parallel", workstream)
        self.assertIn("Re-evaluate the queues after every completion", kanban)
        self.assertIn("capacity release", kanban)
        self.assertIn("Every supervisor wake performs a queue-drain scheduling pass", workstream)
        self.assertIn("Do not launch one worker per criterion by default", workstream)
        self.assertIn("until no unblocked pullable work remains", workstream)
        self.assertIn("walk the active board", workstream)
        self.assertIn("Ready is below its finite WIP limit", workstream)
        self.assertIn("research-capable refinement workers", workstream)
        self.assertIn("does not perform", workstream)
        self.assertIn("research or refinement itself", workstream)

    def test_autonomous_role_topology_keeps_control_and_production_distinct(self):
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        self.assertIn("Use one long-lived supervisor", workstream)
        self.assertIn("Review lane", workstream)
        self.assertIn("Implementation lane", workstream)
        self.assertIn("must not implement a task it", workstream)
        self.assertIn("Do not launch one worker per criterion by default", workstream)

    def test_runtime_worker_authority_stays_ephemeral_and_coordinator_is_not_worker(self):
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        coordination = (DELTA / "skills/kanban/references/coordination-protocol.md").read_text()
        adapter = (DELTA / "skills/autonomous-workstream/references/runtime-adapters.md").read_text()
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        self.assertIn("supervisor is coordinator-only", coordination)
        self.assertIn("must not claim implementation", coordination)
        self.assertIn("acknowledge the task and lease", adapter)
        self.assertIn("start_supervisor", adapter)
        self.assertIn("submit_worker", adapter)
        self.assertIn("live runtime concerns", adapter)
        self.assertIn("does not verify runtime worker liveness", kanban)
        self.assertIn("does not perform", workstream)

    def test_runtime_operations_cover_cleanup_preflight_and_scheduler_reporting(self):
        adapter = (DELTA / "skills/autonomous-workstream/references/runtime-adapters.md").read_text()
        coordination = (DELTA / "skills/kanban/references/coordination-protocol.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        for phrase in ("repository capability preflight", "close and release the worker"):
            self.assertIn(phrase, adapter)
        self.assertIn("one live assignment for each serial task", coordination)
        self.assertIn("review-worker liveness separately", coordination)
        for phrase in ("pullable count", "live claimed count", "available lease capacity", "session-cleanup"):
            self.assertIn(phrase, workstream)

    def test_active_claim_requires_worker_handshake_and_external_suppression(self):
        adapter = (DELTA / "skills/autonomous-workstream/references/runtime-adapters.md").read_text()
        coordination = (DELTA / "skills/kanban/references/coordination-protocol.md").read_text()
        commands = (DELTA / "skills/kanban/references/commands.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        for text in (adapter, coordination):
            self.assertIn("first live checkpoint", text)
            self.assertIn("verified worker ID", text)
        self.assertIn("task remains `Ready`", coordination)
        self.assertIn("helper cannot verify runtime", commands)
        for text in (adapter, coordination, workstream):
            self.assertIn("external-capability", text)
            self.assertIn("environment fingerprint", text)

    def test_workstream_continuation_shorthand_drains_all_active_lanes(self):
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        self.assertIn("continue workstream", workstream)
        self.assertIn("or the shorter `continue`", workstream)
        self.assertIn("research/refinement", workstream)
        self.assertIn("implementation of pullable Ready", workstream)
        self.assertIn("assurance/control review", workstream)
        self.assertIn("not a status-only", workstream)
        self.assertIn("active worker count", workstream)
        self.assertIn("oldest queued age", workstream)
        self.assertIn("whether the stage is hungry", workstream)
        self.assertIn("proactively dispatch", workstream)
        self.assertIn("do not flood Ready", workstream)

    def test_completion_command_requires_recurrent_reports_until_terminal(self):
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        pull_flow = (DELTA / "skills/kanban/references/pull-flow.md").read_text()
        self.assertIn("complete workstream", workstream)
        self.assertIn("run to completion", workstream)
        self.assertIn("completion mandate", workstream)
        self.assertIn("every in-scope task", workstream)
        self.assertIn("Each iteration must produce a progress report", workstream)
        self.assertIn("must not return control to the user", workstream)
        self.assertIn("all non-terminal states", workstream)
        self.assertIn("Backlog is an active refinement queue", workstream)
        self.assertIn("must also inventory every in-scope Backlog task", workstream)
        self.assertIn("recurrent supervisor loop", kanban)
        self.assertIn("in-scope Backlog is drained", kanban)
        self.assertIn("Backlog is never treated as an excluded source", pull_flow)

    def test_pull_flow_defines_stage_hunger_and_backpressure_reporting(self):
        pull_flow = (DELTA / "skills/kanban/references/pull-flow.md").read_text()
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        self.assertIn("## Stage hunger", pull_flow)
        self.assertIn("Hunger flows", pull_flow)
        self.assertIn("full or over-limit stage is not", pull_flow)
        self.assertIn("live worker count and", kanban)

    def test_stage_transitions_are_defined_pull_and_handoff_processes(self):
        pull_flow = (DELTA / "skills/kanban/references/pull-flow.md").read_text()
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        self.assertIn("## Stage transition processes", pull_flow)
        for phrase in ("Backlog → Ready", "Ready → Active", "Active → Review", "Review → Done"):
            self.assertIn(phrase, pull_flow)
        self.assertIn("A state change by", pull_flow)
        self.assertIn("Queues are not static", kanban)
        self.assertIn("treat every transition as an active process", workstream)

    def test_revision_bound_work_requires_isolated_writable_workspaces(self):
        adapter = (DELTA / "skills/autonomous-workstream/references/runtime-adapters.md").read_text()
        coordination = (DELTA / "skills/kanban/references/coordination-protocol.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        self.assertIn("provision_workspace", adapter)
        self.assertIn("isolated writable worktree", adapter)
        self.assertIn("workspace identity", adapter)
        self.assertIn("different isolated workspace", adapter)
        self.assertIn("workspace identity", coordination)
        self.assertIn("Revision-bound review workers", workstream)

    def test_pull_flow_contract_is_linked_and_preserves_task_status(self):
        pull = (DELTA / "skills/kanban/references/pull-flow.md").read_text()
        kanban = (DELTA / "skills/kanban/SKILL.md").read_text()
        workstream = (DELTA / "skills/autonomous-workstream/SKILL.md").read_text()
        self.assertIn("short-lived and renewable", pull)
        self.assertRegex(pull, r"reserves\s+capacity, not a specific task")
        self.assertRegex(pull, r"without moving the task to\s+`Blocked`")
        self.assertIn("worker-demand contract", pull)
        self.assertIn("backpressure", pull.lower())
        self.assertIn("pull-flow.md", kanban)
        self.assertIn("pull-flow contract", workstream)
        self.assertIn("preparation/refinement/research and validation lanes", workstream)


if __name__ == "__main__":
    unittest.main()
