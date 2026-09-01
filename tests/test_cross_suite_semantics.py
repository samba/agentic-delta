import json
import re
import unittest
from pathlib import Path


DELTA = Path(__file__).resolve().parents[1]
SRE = DELTA.parent / "agentic-sre"


class CrossSuiteSemanticsTest(unittest.TestCase):
    def test_delta_owns_the_only_handoff_schema(self):
        delta = json.loads(
            (DELTA / "skills/kanban/references/specialist-handoff.schema.json").read_text()
        )
        self.assertEqual(delta["properties"]["contract_version"]["const"], "2")
        self.assertIn("handoff_id", delta["required"])
        self.assertIn("specialist_class", delta["required"])
        self.assertIn("engagement_role", delta["required"])
        self.assertIn("worker_id", delta["required"])
        self.assertIn("gate_id", delta["required"])
        self.assertIn("applicability", delta["required"])
        self.assertFalse((SRE / "docs/specialist-handoff.schema.json").exists())
        for path in SRE.glob("skills/*/references/coordinated-handoff.md"):
            self.assertIn(delta["$id"], path.read_text(), path)

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
            "standard-of-excellence.md",
            "execution-contracts.md",
            "semantic-rule-inventory.md",
            "board-walk.md",
            "backlog-refinement.md",
            "delegation.md",
            "autonomous-loop.md",
            "validation-contracts.md",
            "intents-and-migration.md",
            "commands.md",
            "source-register.md",
            "specialist-handoff.schema.json",
            "specialist-coordination.md",
            "agent-handoff-migration.md",
        )
        root = DELTA / "skills/kanban/references"
        for name in expected:
            self.assertTrue((root / name).is_file(), name)

    def test_normative_invariants_remain_enforced_or_owned(self):
        standard = (DELTA / "skills/kanban/references/standard-of-excellence.md").read_text()
        contracts = (DELTA / "skills/kanban/references/execution-contracts.md").read_text()
        schema = (DELTA / "skills/kanban/scripts/schema.sql").read_text()
        self.assertIn("Durable intent before substantive execution", standard)
        self.assertIn("Controlled autonomy", standard)
        self.assertIn("Research and provenance", standard)
        self.assertIn("Verification and acceptance", standard)
        self.assertIn("Safe delivery and operations", standard)
        self.assertIn("Learning without self-authorized drift", standard)
        self.assertIn("immutable envelope", contracts)
        self.assertIn("exact revision or digest", contracts)
        self.assertIn("earliest stage", contracts)
        for table in (
            "intents", "decisions", "runs", "autonomy_envelopes", "gate_types", "gates",
            "evidence", "specialist_classes", "specialist_class_versions",
            "gate_specialist_requirements",
            "work_types", "task_work_profiles", "review_policies",
            "review_policy_rules", "review_policy_rule_references",
            "review_plans", "review_plan_rule_bindings", "review_plan_items",
            "specialist_handoffs", "handoff_sources",
            "handoff_artifacts", "handoff_findings", "handoff_evidence",
            "handoff_risks", "handoff_decisions", "handoff_receipts",
            "learning_events",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)


if __name__ == "__main__":
    unittest.main()
