import copy
from contextlib import redirect_stderr
import importlib.util
from io import StringIO
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


class FaultingTemporaryFile:
    def __init__(self, handle, *, fail_write=False, fail_close=False):
        self.handle = handle
        self.name = handle.name
        self.fail_write = fail_write
        self.fail_close = fail_close

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        result = self.handle.__exit__(exc_type, exc_value, traceback)
        if self.fail_close and exc_type is None:
            raise OSError("임시 파일 close 실패 주입")
        return result

    def write(self, value):
        self.handle.write(value)
        if self.fail_write:
            raise OSError("임시 파일 write 실패 주입")


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

    def test_common_runtime_and_critical_paths_are_candidates(self):
        cases = [
            ("app.py", "runtime"),
            ("cmd/server/main.go", "runtime"),
            ("src/auth/session.ts", "critical"),
            ("security/encrypt.rs", "critical"),
            ("db/migrations/0001_users.sql", "critical"),
            ("schema.prisma", "critical"),
            ("api/openapi.yaml", "critical"),
            ("proto/user.proto", "critical"),
            (".github/actions/setup/action.yml", "critical"),
            ("infra/main.tf", "critical"),
            ("Dockerfile", "critical"),
            ("package.json", "critical"),
            ("pnpm-lock.yaml", "critical"),
            ("pyproject.toml", "critical"),
            ("poetry.lock", "critical"),
            ("Cargo.toml", "critical"),
            ("go.sum", "critical"),
            ("pom.xml", "critical"),
            ("Gemfile.lock", "critical"),
            ("composer.json", "critical"),
            ("Package.resolved", "critical"),
            ("setup.py", "critical"),
            (".releaserc.json", "critical"),
        ]
        for path, candidate_kind in cases:
            with self.subTest(path=path):
                result = self.classify([path], repository="example/project")
                self.assertEqual(
                    ("candidate", candidate_kind),
                    (result["decision"], result["candidateKind"]),
                )

    def test_common_docs_tests_and_generated_paths_are_excluded(self):
        cases = [
            ("CHANGELOG.rst", "docs_only"),
            ("CONTRIBUTING.adoc", "docs_only"),
            ("guide/overview.md", "docs_only"),
            ("docs/images/flow.svg", "docs_only"),
            ("infra/README.md", "docs_only"),
            ("src/__tests__/session.test.ts", "test_only"),
            ("pkg/parser_test.go", "test_only"),
            ("nested/vendor/library/source.c", "generated_only"),
            ("web/node_modules/pkg/index.js", "generated_only"),
            ("frontend/.next/server/app.js", "generated_only"),
            ("pkg/generated/client.py", "generated_only"),
        ]
        for path, reason in cases:
            with self.subTest(path=path):
                result = self.classify([path], repository="example/project")
                self.assertEqual(
                    ("exclude", reason),
                    (result["decision"], result["reason"]),
                )

    def test_mixed_roles_require_real_runtime_or_critical_evidence(self):
        cases = [
            (["README.md", "CHANGELOG.rst"], "exclude", "docs_only", None),
            (
                ["README.md", "tests/test_app.py", "nested/vendor/lib.c"],
                "exclude",
                "non_runtime_only",
                None,
            ),
            (["README.md", "notes.unknown"], "review", "unknown_files", None),
            (["tests/test_app.py", "notes.unknown"], "review", "unknown_files", None),
            (["nested/build/app.bin", "notes.unknown"], "review", "unknown_files", None),
            ([".github/ISSUE_TEMPLATE/bug.yml"], "review", "unknown_files", None),
            (["notes.unknown"], "review", "unknown_files", None),
            (["app.py", "README.md", "notes.unknown"], "candidate", "eligible_files", "runtime"),
            (["package.json", "notes.unknown"], "candidate", "eligible_files", "critical"),
        ]
        for paths, decision, reason, candidate_kind in cases:
            with self.subTest(paths=paths):
                result = self.classify(paths, repository="example/project")
                self.assertEqual((decision, reason), (result["decision"], result["reason"]))
                self.assertEqual(candidate_kind, result["candidateKind"])

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

    def test_manifest_and_index_preserve_aggregate_contract(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            report.render_report(self.fixture_payload(25), root)

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schemaVersion"])
            self.assertEqual("hyeongyu-data/repo-walk", manifest["repository"])
            self.assertEqual("2026-07-30T02:05:00Z", manifest["generatedAt"])
            self.assertEqual(2, manifest["reportCount"])
            self.assertEqual({"behavior": 1, "critical": 1}, manifest["kindCounts"])
            self.assertEqual(
                {"critical": 1, "material": 1, "none": 0},
                manifest["operationalImpactCounts"],
            )
            self.assertEqual(
                ["설치 캐시 무효화에 필요한 배포 매니페스트 변경"],
                manifest["reports"][0]["reasons"],
            )
            self.assertEqual(
                [".claude-plugin/plugin.json", "plugins/repo-walk/.codex-plugin/plugin.json"],
                manifest["reports"][0]["files"],
            )

            index_html = (root / "index.html").read_text(encoding="utf-8")
            for expected in (
                "hyeongyu-data/repo-walk",
                "2026-07-30T02:05:00Z",
                "총 2개",
                "behavior 1",
                "critical 1",
                "material 1",
                "설치 캐시 무효화에 필요한 배포 매니페스트 변경",
                "plugins/repo-walk/.codex-plugin/plugin.json",
            ):
                with self.subTest(expected=expected):
                    self.assertIn(expected, index_html)

    def test_render_rejects_cross_repository_mix_before_modifying_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            mixed = copy.deepcopy(self.fixture_payload(25))
            mixed["repository"] = "other/project"
            mixed["pr"]["number"] = 99
            mixed["pr"]["url"] = "https://github.com/other/project/pull/99"

            with self.assertRaises(report.ReportValidationError):
                report.render_report(mixed, root)

            self.assertEqual(
                before,
                {
                    path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
            )

    def test_rebuild_rejects_mixed_repositories_before_modifying_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            mixed = copy.deepcopy(self.fixture_payload(25))
            mixed["repository"] = "other/project"
            mixed["pr"]["number"] = 99
            mixed["pr"]["url"] = "https://github.com/other/project/pull/99"
            mixed_path = root / "data/pr-99.json"
            mixed_path.write_text(json.dumps(mixed), encoding="utf-8")
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            with self.assertRaises(report.ReportValidationError):
                report.rebuild_index(root)

            self.assertEqual(
                before,
                {
                    path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
            )

    def test_unreadable_individual_data_entry_is_skipped_with_sanitized_warning(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            (root / "data/pr-999.json").mkdir()
            warning = StringIO()

            with redirect_stderr(warning):
                report.rebuild_index(root)

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([23], [entry["number"] for entry in manifest["reports"]])
            self.assertIn("읽을 수 없는 PR data 항목", warning.getvalue())
            self.assertNotIn("pr-999.json", warning.getvalue())

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

    def test_atomic_write_cleans_temporary_path_when_write_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            created = []
            real_named_temporary_file = report.NamedTemporaryFile

            def failing_temporary_file(*args, **kwargs):
                handle = real_named_temporary_file(*args, **kwargs)
                created.append(Path(handle.name))
                return FaultingTemporaryFile(handle, fail_write=True)

            with patch.object(report, "NamedTemporaryFile", side_effect=failing_temporary_file):
                with self.assertRaisesRegex(OSError, "write 실패"):
                    report.atomic_write_text(root / "output.txt", "민감한 일부 내용")

            self.assertTrue(created)
            self.assertFalse((root / "output.txt").exists())
            self.assertTrue(all(not path.exists() for path in created))

    def test_atomic_replace_cleans_staged_path_when_close_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            created = []
            real_named_temporary_file = report.NamedTemporaryFile

            def failing_temporary_file(*args, **kwargs):
                handle = real_named_temporary_file(*args, **kwargs)
                created.append(Path(handle.name))
                return FaultingTemporaryFile(handle, fail_close=True)

            with patch.object(report, "NamedTemporaryFile", side_effect=failing_temporary_file):
                with self.assertRaisesRegex(OSError, "close 실패"):
                    report.atomic_replace_text_files([(root / "output.txt", "새 내용")])

            self.assertTrue(created)
            self.assertFalse((root / "output.txt").exists())
            self.assertTrue(all(not path.exists() for path in created))

    def test_atomic_replace_cleans_backup_path_when_write_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output.txt"
            output.write_text("이전 내용", encoding="utf-8")
            created = []
            call_count = 0
            real_named_temporary_file = report.NamedTemporaryFile

            def failing_second_temporary_file(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                handle = real_named_temporary_file(*args, **kwargs)
                created.append(Path(handle.name))
                return FaultingTemporaryFile(handle, fail_write=call_count == 2)

            with patch.object(
                report,
                "NamedTemporaryFile",
                side_effect=failing_second_temporary_file,
            ):
                with self.assertRaisesRegex(OSError, "write 실패"):
                    report.atomic_replace_text_files([(output, "새 내용")])

            self.assertEqual("이전 내용", output.read_text(encoding="utf-8"))
            self.assertTrue(all(not path.exists() for path in created))

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

    def test_long_text_wraps_while_code_keeps_horizontal_scrolling(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(self.fixture_payload(23), root)
            unit_html = (root / "prs/pr-23.html").read_text(encoding="utf-8")
            index_html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("overflow-wrap: anywhere", unit_html)
            self.assertIn("overflow-wrap: anywhere", index_html)
            self.assertIn("overflow-x: auto", unit_html)

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

    def test_semantic_classification_contract_rejects_invalid_reports(self):
        mutations = [
            ("decision", lambda value: value["classification"].update(decision="exclude")),
            ("kind", lambda value: value["classification"].update(kind="cosmetic")),
            (
                "include predicate",
                lambda value: value["classification"].update(
                    behaviorChanged=False,
                    operationalImpact="none",
                ),
            ),
            (
                "behaviorChanged",
                lambda value: value["classification"].update(behaviorChanged="true"),
            ),
            (
                "operationalImpact",
                lambda value: value["classification"].update(operationalImpact="minor"),
            ),
            ("confidence", lambda value: value["classification"].update(confidence="certain")),
            ("reasons", lambda value: value["classification"].update(reasons=[])),
            ("files", lambda value: value["classification"].update(files=[])),
            ("evidence", lambda value: value["classification"].update(evidence=[])),
            (
                "evidence path",
                lambda value: value["classification"].update(
                    evidence=[{"path": "src/missing.py", "claim": "목록에 없는 파일"}]
                ),
            ),
            (
                "evidence claim",
                lambda value: value["classification"].update(
                    evidence=[{"path": "commands/repo-walk.md", "claim": ""}]
                ),
            ),
            (
                "classifierVersion",
                lambda value: value["classification"].update(classifierVersion=""),
            ),
            (
                "inputDigest",
                lambda value: value["classification"].update(inputDigest="A" * 64),
            ),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                payload = copy.deepcopy(make_report())
                mutate(payload)
                with self.assertRaises(report.ReportValidationError):
                    report.validate_report(payload)

    def test_future_classifier_version_is_preserved(self):
        payload = make_report()
        payload["classification"]["classifierVersion"] = "2026.07-v2"
        validated = report.validate_report(payload)
        self.assertEqual(
            "2026.07-v2",
            validated["classification"]["classifierVersion"],
        )


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
