import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "skill_federation.py"
SPEC = importlib.util.spec_from_file_location("skill_federation", SCRIPT)
FEDERATION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(FEDERATION)


class FederationCatalogTest(unittest.TestCase):
    def setUp(self):
        self.catalog = FEDERATION.load_catalog(ROOT / "skill-federation.yaml")

    def test_catalog_contains_no_machine_local_source_paths(self):
        for source in self.catalog["sources"]:
            self.assertNotIn("local_path", source, source.get("id"))
            self.assertNotEqual(source.get("kind"), "local_repo", source.get("id"))

    def test_installable_repository_sources_use_public_https_urls(self):
        for source in self.catalog["sources"]:
            policy = FEDERATION.source_policy(self.catalog, source)
            if policy["install_policy"] not in {"installable", "review-required"}:
                continue
            url = source.get("repo_url")
            self.assertIsInstance(url, str, source.get("id"))
            self.assertTrue(url.startswith("https://"), source.get("id"))

    def test_revision_required_sources_are_pinned(self):
        for source in self.catalog["sources"]:
            if not source.get("revision_required"):
                continue
            revision = source.get("revision", "")
            if source.get("publication_status") == "pending-commit":
                self.assertIsNone(revision, source.get("id"))
            else:
                self.assertRegex(revision, r"^[0-9a-f]{40}$", source.get("id"))
            self.assertEqual(source.get("handoff_contract_version"), "2")

    def test_pending_required_revision_blocks_even_dry_run(self):
        source = next(
            item for item in self.catalog["sources"]
            if item.get("publication_status") == "pending-commit"
        )
        with tempfile.TemporaryDirectory() as tempdir, self.assertRaises(SystemExit):
            FEDERATION.materialize_source(source, Path(tempdir), update=False, dry_run=True)

    def test_agentic_sre_publishes_product_to_production_lifecycle(self):
        source = next(
            item for item in self.catalog["sources"]
            if item.get("id") == "agentic-sre"
        )
        skills = {item["name"]: item for item in source["skills"]}
        expected_stages = {
            "software-product-discovery": "discovery",
            "software-architecture": "architecture",
            "software-delivery": "implementation",
            "software-supply-chain": "supply-chain",
            "production-readiness": "production-readiness",
        }
        for name, stage in expected_stages.items():
            self.assertIn(name, skills)
            self.assertEqual(skills[name].get("workflow_stage"), stage)
            self.assertEqual(skills[name].get("handoff_contract_version"), "2")
            self.assertTrue(skills[name].get("capabilities"))


if __name__ == "__main__":
    unittest.main()
