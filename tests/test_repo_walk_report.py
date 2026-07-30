import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "repo_walk_report.py"
SPEC = importlib.util.spec_from_file_location("repo_walk_report", MODULE_PATH)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ClassificationTests(unittest.TestCase):
    def classify(self, paths, *, state="MERGED", merged_at="2026-07-01T00:00:00Z",
                 changed_files=None, repository="hyeongyu-data/repo-walk"):
        files = [{"path": path} for path in paths]
        payload = {
            "repository": repository,
            "pr": {
                "number": 23,
                "state": state,
                "mergedAt": merged_at,
                "changedFiles": changed_files if changed_files is not None else len(files),
                "files": files,
            },
        }
        return report.classify_pull_request(payload)

    def fixture_payload(self, number):
        fixture_path = ROOT / "tests" / "fixtures" / f"pr-{number}.json"
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_closed_unmerged_is_excluded(self):
        result = self.classify(["src/app.py"], state="CLOSED", merged_at=None)
        self.assertEqual(("exclude", "unmerged"), (result["decision"], result["reason"]))

    def test_docs_only_is_excluded(self):
        result = self.classify(["README.md", "docs/guide.md"])
        self.assertEqual(("exclude", "docs_only"), (result["decision"], result["reason"]))

    def test_repo_walk_functional_markdown_is_runtime(self):
        result = self.classify(["commands/repo-walk.md"])
        self.assertEqual(("candidate", "runtime"), (result["decision"], result["candidateKind"]))

    def test_workflow_is_critical_candidate(self):
        result = self.classify([".github/workflows/release.yml"])
        self.assertEqual(("candidate", "critical"), (result["decision"], result["candidateKind"]))

    def test_incomplete_file_list_requires_review(self):
        result = self.classify(["src/app.py"], changed_files=2)
        self.assertEqual(("review", "incomplete_metadata"), (result["decision"], result["reason"]))

    def test_pr_21_fixture_is_docs_only(self):
        result = report.classify_pull_request(self.fixture_payload(21))
        self.assertEqual(("exclude", "docs_only"), (result["decision"], result["reason"]))

    def test_pr_23_fixture_is_runtime_candidate(self):
        result = report.classify_pull_request(self.fixture_payload(23))
        self.assertEqual(("candidate", "runtime"), (result["decision"], result["candidateKind"]))

    def test_pr_25_fixture_is_critical_candidate(self):
        result = report.classify_pull_request(self.fixture_payload(25))
        self.assertEqual(("candidate", "critical"), (result["decision"], result["candidateKind"]))

    def test_claude_and_codex_scripts_are_identical(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (root / "scripts/repo_walk_report.py").read_bytes(),
            (root / "plugins/repo-walk/scripts/repo_walk_report.py").read_bytes(),
        )

    def test_cli_emits_classification_contract(self):
        process = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input=json.dumps(self.fixture_payload(23)),
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        result = json.loads(process.stdout)
        self.assertEqual("candidate", result["decision"])
        self.assertEqual("eligible_files", result["reason"])
        self.assertEqual(["runtime", "runtime"], result["roles"])
        self.assertEqual("runtime", result["candidateKind"])
        self.assertEqual("1", result["classifierVersion"])
        self.assertEqual(64, len(result["inputDigest"]))
