import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "repo_walk_report.py"
SPEC = importlib.util.spec_from_file_location("repo_walk_report", MODULE_PATH)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def make_report(*, title=None, summary=None, sections=None, url=None):
    fixture_path = ROOT / "tests" / "fixtures" / "report-23.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if title is not None:
        payload["pr"]["title"] = title
    if summary is not None:
        payload["summary"] = summary
    if sections is not None:
        payload["sections"] = sections
    if url is not None:
        payload["pr"]["url"] = url
    return payload


def make_classification_input(paths):
    files = [{"path": path} for path in paths]
    return {
        "repository": "hyeongyu-data/repo-walk",
        "pr": {
            "number": 23,
            "state": "MERGED",
            "mergedAt": "2026-07-01T00:00:00Z",
            "changedFiles": len(files),
            "files": files,
        },
    }


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

    def test_root_codex_plugin_manifest_is_critical_candidate(self):
        result = self.classify([".codex-plugin/plugin.json"])
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


class RenderingTests(unittest.TestCase):
    def fixture_payload(self, number):
        fixture_path = ROOT / "tests" / "fixtures" / f"report-{number}.json"
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_remote_html_is_escaped_and_index_is_idempotent(self):
        payload = make_report(
            title='<script>alert("x")</script>',
            summary="권한 <검증>을 추가",
            sections=[{
                "title": "1. 변경 해설",
                "blocks": [{"type": "code", "path": "src/<app>.py", "line": 7,
                            "language": "python", "code": "<script>bad()</script>"}],
            }],
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(payload, root)
            report.render_report(payload, root)
            unit_html = (root / "prs/pr-23.html").read_text()
            index_html = (root / "index.html").read_text()
            self.assertNotIn("<script>", unit_html)
            self.assertIn("&lt;script&gt;", unit_html)
            self.assertEqual(1, index_html.count('href="prs/pr-23.html"'))

    def test_invalid_report_preserves_existing_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(make_report(), root)
            output_paths = [
                root / "data/pr-23.json",
                root / "prs/pr-23.html",
                root / "manifest.json",
                root / "index.html",
            ]
            before = {path: path.read_bytes() for path in output_paths}
            with self.assertRaises(report.ReportValidationError):
                report.render_report({"schemaVersion": 1}, root)
            self.assertEqual(before, {path: path.read_bytes() for path in output_paths})

    def test_corrupt_manifest_is_rebuilt_from_data_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(make_report(), root)
            (root / "manifest.json").write_text("{broken")
            report.rebuild_index(root)
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual([23], [entry["number"] for entry in manifest["reports"]])

    def test_json_corrupt_data_is_excluded_when_rebuilding_index(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            report.render_report(self.fixture_payload(25), root)
            corrupt_path = root / "data/pr-999.json"
            corrupt_path.write_text("{broken", encoding="utf-8")

            try:
                report.rebuild_index(root)
            except report.ReportValidationError as error:
                self.fail(f"손상 JSON은 인덱스 재구축을 중단하면 안 됩니다: {error}")

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([25, 23], [entry["number"] for entry in manifest["reports"]])
            self.assertEqual("{broken", corrupt_path.read_text(encoding="utf-8"))

    def test_schema_corrupt_data_is_excluded_when_rebuilding_index(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            report.render_report(self.fixture_payload(25), root)
            corrupt_path = root / "data/pr-999.json"
            corrupt_path.write_text('{"schemaVersion": 1}', encoding="utf-8")

            try:
                report.rebuild_index(root)
            except report.ReportValidationError as error:
                self.fail(f"스키마 손상은 인덱스 재구축을 중단하면 안 됩니다: {error}")

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([25, 23], [entry["number"] for entry in manifest["reports"]])
            self.assertEqual(
                '{"schemaVersion": 1}',
                corrupt_path.read_text(encoding="utf-8"),
            )

    def test_render_rolls_back_every_output_when_replacement_fails(self):
        relative_paths = (
            Path("data/pr-23.json"),
            Path("prs/pr-23.html"),
            Path("manifest.json"),
            Path("index.html"),
        )
        for failing_relative_path in relative_paths:
            with self.subTest(failing_path=failing_relative_path):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    report.render_report(make_report(title="이전 세대"), root)
                    output_paths = [root / relative_path for relative_path in relative_paths]
                    before = {path: path.read_bytes() for path in output_paths}
                    real_replace = report.os.replace
                    failure_injected = False

                    def replace_with_failure(source, destination):
                        nonlocal failure_injected
                        if Path(destination) == root / failing_relative_path and not failure_injected:
                            failure_injected = True
                            raise OSError(f"교체 실패 주입: {failing_relative_path}")
                        return real_replace(source, destination)

                    with patch.object(report.os, "replace", side_effect=replace_with_failure):
                        with self.assertRaisesRegex(OSError, "교체 실패 주입"):
                            report.render_report(make_report(title="새 세대"), root)

                    self.assertTrue(failure_injected)
                    self.assertEqual(
                        before,
                        {path: path.read_bytes() for path in output_paths},
                    )

    def test_valid_update_atomically_replaces_existing_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(make_report(title="이전 제목"), root)
            unit_path = root / "prs/pr-23.html"
            with unit_path.open(encoding="utf-8") as previous_file:
                previous_output = previous_file.read()
                previous_file.seek(0)
                report.render_report(make_report(title="새 제목"), root)
                self.assertEqual(previous_output, previous_file.read())
            current_output = unit_path.read_text(encoding="utf-8")
            self.assertIn("새 제목", current_output)
            self.assertNotIn("이전 제목", current_output)

    def test_non_github_url_is_rendered_as_text(self):
        payload = make_report(url="javascript:alert(1)")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(payload, root)
            output = (root / "prs/pr-23.html").read_text()
            self.assertNotIn('href="javascript:', output)
            self.assertIn("javascript:alert(1)", output)

    def test_malformed_url_is_escaped_as_text(self):
        payload = make_report(url="https://[broken/<script>")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(payload, root)
            output = (root / "prs/pr-23.html").read_text(encoding="utf-8")
            self.assertNotIn('href="https://[broken/', output)
            self.assertIn("https://[broken/&lt;script&gt;", output)

    def test_all_supported_blocks_and_critical_index_card_are_rendered(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            report.render_report(self.fixture_payload(25), root)

            unit_html = (root / "prs/pr-23.html").read_text(encoding="utf-8")
            index_html = (root / "index.html").read_text(encoding="utf-8")
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

            self.assertIn("<ul>", unit_html)
            self.assertIn("<blockquote>", unit_html)
            self.assertIn('class="finding"', unit_html)
            self.assertIn('class="question"', unit_html)
            self.assertIn("commands/&lt;repo-walk&gt;.md:210", unit_html)
            self.assertNotIn("<script>", unit_html)
            self.assertEqual([25, 23], [entry["number"] for entry in manifest["reports"]])
            self.assertEqual(1, index_html.count('href="prs/pr-23.html"'))
            self.assertEqual(1, index_html.count('href="prs/pr-25.html"'))
            self.assertIn('class="badge critical"', index_html)

    def test_schema_and_block_validation_rejects_malformed_remote_data(self):
        invalid_payloads = [
            [],
            {**make_report(), "schemaVersion": 2},
            {**make_report(), "sections": [{"title": "x", "blocks": [{"type": "video"}]}]},
            {**make_report(), "classification": {**make_report()["classification"], "files": [""]}},
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(report.ReportValidationError):
                        report.render_report(payload, root)


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *arguments],
            text=True,
            capture_output=True,
        )

    def test_classify_cli_writes_json(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(
                json.dumps(make_classification_input(["README.md"])),
                encoding="utf-8",
            )
            completed = self.run_cli("classify", "--input", str(source))
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("docs_only", json.loads(completed.stdout)["reason"])

    def test_render_cli_writes_report_artifacts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            output = root / "reports"
            source.write_text(json.dumps(make_report()), encoding="utf-8")
            completed = self.run_cli(
                "render", "--input", str(source), "--output-dir", str(output)
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((output / "data/pr-23.json").is_file())
            self.assertTrue((output / "prs/pr-23.html").is_file())
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "index.html").is_file())

    def test_rebuild_index_cli_recovers_index_from_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(make_report(), root)
            (root / "index.html").unlink()
            completed = self.run_cli(
                "rebuild-index", "--output-dir", str(root)
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((root / "index.html").is_file())

    def test_invalid_json_exits_2_without_echoing_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text('{"secret":"do-not-echo"', encoding="utf-8")
            completed = self.run_cli("classify", "--input", str(source))
            self.assertEqual(2, completed.returncode)
            self.assertNotIn("do-not-echo", completed.stderr)

    def test_validation_error_exits_3_without_echoing_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(
                '{"repository":"secret-repository","pr":{}}',
                encoding="utf-8",
            )
            completed = self.run_cli("classify", "--input", str(source))
            self.assertEqual(3, completed.returncode)
            self.assertNotIn("secret-repository", completed.stderr)

    def test_write_error_exits_4(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            blocked_output = root / "not-a-directory"
            source.write_text(json.dumps(make_report()), encoding="utf-8")
            blocked_output.write_text("blocked", encoding="utf-8")
            completed = self.run_cli(
                "render",
                "--input",
                str(source),
                "--output-dir",
                str(blocked_output),
            )
            self.assertEqual(4, completed.returncode)
