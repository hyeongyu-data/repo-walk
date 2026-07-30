import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_COMMAND = ROOT / "commands/repo-walk.md"
CODEX_SKILL = ROOT / "plugins/repo-walk/skills/repo-walk/SKILL.md"


def write_classification_input(directory):
    source = Path(directory) / "classification.json"
    source.write_text(
        json.dumps({
            "repository": "hyeongyu-data/repo-walk",
            "pr": {
                "number": 23,
                "state": "MERGED",
                "mergedAt": "2026-07-17T15:06:44Z",
                "changedFiles": 1,
                "files": [{"path": "commands/repo-walk.md"}],
            },
        }),
        encoding="utf-8",
    )
    return source


class PluginPackageTests(unittest.TestCase):
    def adapter_texts(self):
        return {
            "Claude": " ".join(CLAUDE_COMMAND.read_text(encoding="utf-8").split()),
            "Codex": " ".join(CODEX_SKILL.read_text(encoding="utf-8").split()),
        }

    def adapter_sources(self):
        return {
            "Claude": CLAUDE_COMMAND.read_text(encoding="utf-8"),
            "Codex": CODEX_SKILL.read_text(encoding="utf-8"),
        }

    def test_report_feature_manifests_share_version_0_3_0(self):
        claude_manifest = json.loads(
            (ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
        codex_manifest = json.loads(
            (
                ROOT / "plugins/repo-walk/.codex-plugin/plugin.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual("0.3.0", claude_manifest["version"])
        self.assertEqual(
            "0.3.0",
            codex_manifest["version"].split("+", 1)[0],
        )

    def test_codex_manifest_has_single_utc_cachebuster(self):
        manifest = json.loads(
            (
                ROOT / "plugins/repo-walk/.codex-plugin/plugin.json"
            ).read_text(encoding="utf-8")
        )

        self.assertRegex(manifest["version"], r"^0\.3\.0\+codex\.\d{14}$")

    def test_claude_report_script_exists(self):
        self.assertTrue((ROOT / "scripts/repo_walk_report.py").is_file())

    def test_codex_report_script_exists_inside_plugin(self):
        self.assertTrue(
            (ROOT / "plugins/repo-walk/scripts/repo_walk_report.py").is_file()
        )

    def test_claude_python_permission_is_not_a_broad_wildcard(self):
        frontmatter = CLAUDE_COMMAND.read_text(encoding="utf-8").split("---", 2)[1]
        self.assertNotIn("Bash(python3:*)", frontmatter)

    def test_claude_permission_targets_installed_plugin_script(self):
        frontmatter = CLAUDE_COMMAND.read_text(encoding="utf-8").split("---", 2)[1]
        self.assertIn(
            "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/repo_walk_report.py:*)",
            frontmatter,
        )
        self.assertNotIn("Bash(python3 scripts/repo_walk_report.py:*)", frontmatter)

    def test_claude_installed_script_runs_from_arbitrary_cwd(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            source = write_classification_input(target)
            environment = {
                **os.environ,
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "CLASSIFICATION_INPUT": str(source),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            completed = subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/repo_walk_report.py "
                    'classify --input "$CLASSIFICATION_INPUT"',
                ],
                cwd=target,
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual("candidate", json.loads(completed.stdout)["decision"])

    def test_codex_installed_script_runs_from_arbitrary_cwd(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            source = write_classification_input(target)
            plugin_root = CODEX_SKILL.parent.parent.parent
            script = plugin_root / "scripts/repo_walk_report.py"
            completed = subprocess.run(
                [sys.executable, str(script), "classify", "--input", str(source)],
                cwd=target,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual("candidate", json.loads(completed.stdout)["decision"])

    def test_codex_contract_resolves_script_from_skill_location(self):
        skill = CODEX_SKILL.read_text(encoding="utf-8")
        self.assertIn(
            "SKILL.md가 있는 디렉터리에서 두 단계 위의 plugin root",
            skill,
        )
        self.assertNotIn(
            "python3 plugins/repo-walk/scripts/repo_walk_report.py",
            skill,
        )

    def test_both_adapters_stage_all_inputs_inside_report_root(self):
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                self.assertIn(
                    ".repo-walk/reports/OWNER-REPO/.staging/classification-pr-N.json",
                    text,
                )
                self.assertIn(
                    ".repo-walk/reports/OWNER-REPO/.staging/report-pr-N.json",
                    text,
                )
                self.assertIn("report root 밖의 별도 input", text)

    def test_both_adapters_build_complete_classifier_input_from_gh_metadata(self):
        marker = "`gh pr view` 응답을 `pr` 객체"
        for adapter, source_text in self.adapter_sources().items():
            with self.subTest(adapter=adapter):
                section = source_text.split(marker, 1)[1]
                normalized_section = " ".join(section.split())
                self.assertIn(
                    "현재 후보 `N`을 `pr.number`로 보강",
                    normalized_section,
                )
                json_text = section.split("```json", 1)[1].split("```", 1)[0]
                payload = json.loads(json_text)
                self.assertEqual(123, payload["pr"]["number"])

                with TemporaryDirectory() as directory:
                    source = Path(directory) / "classification.json"
                    source.write_text(json.dumps(payload), encoding="utf-8")
                    completed = subprocess.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts/repo_walk_report.py"),
                            "classify",
                            "--input",
                            str(source),
                        ],
                        text=True,
                        capture_output=True,
                        check=True,
                    )
                self.assertEqual(
                    "candidate",
                    json.loads(completed.stdout)["decision"],
                )

    def test_both_adapters_handle_every_review_reason_conservatively(self):
        required = (
            '`decision:"review"`의 모든 reason',
            "사용자에게 검토 필요와 reason을 알립니다",
            "파일 메타데이터를 보완합니다",
            "안전하면 diff를 수동 검토합니다",
            "근거가 부족하면 보수적으로 건너뜁니다",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_both_adapters_define_strict_semantic_include_schema(self):
        required = (
            '"decision": "include"',
            '"behaviorChanged": true',
            '"operationalImpact": "none|material|critical"',
            '"confidence": "low|medium|high"',
            '"evidence": [{"path": "변경 파일", "claim": "diff 근거"}]',
            '"classifierVersion": "분류기 provenance"',
            '"inputDigest": "64자 소문자 SHA-256"',
            "`behaviorChanged == true` 또는 `operationalImpact`가 `material|critical`",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_both_adapters_process_at_most_one_report_unit_per_invocation(self):
        required = (
            "수집·파일 분류·의미 판정 단계",
            "적격 PR의 최소 메타데이터만 `units`에 저장",
            "`units[cursor]`의 PR **정확히 하나만**",
            "한 호출에서 렌더링하는 PR은 최대 하나",
            "첫 실행도 수집 뒤 현재 unit 하나만",
            "`next`에 대기 퀴즈가 있으면 답변 또는 `skip`만 안내",
            "퀴즈 답변 또는 `skip`은 cursor를 정확히 한 칸 전진시킨 뒤 즉시 멈춥니다",
            "나중의 `next`에 대기 퀴즈가 없을 때만 현재 unit 하나를 처리",
        )
        forbidden = (
            "각 include PR은 기존 5부분 해설",
            "각 include PR의 기존 해설",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)

    def test_both_adapters_preserve_report_mode_and_failure_state(self):
        required = (
            "저장된 `reportMode`를 계승",
            "충돌하면 상태를",
            "`reset`",
            "재수집하지 않습니다",
            "수집·분류·의미 판정·현재 unit 조회·리포트 JSON 작성·render 또는 명시적 복구의 rebuild-index",
            "`cursor`와 `pendingQuiz`를 호출 전 값으로 유지",
            "실패한 호출에서도 렌더링은 최대 하나",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_both_adapters_close_forward_test_edge_cases(self):
        required = (
            "재검증에서 include 식을 더 이상 만족하지 않으면 리포트와 퀴즈를 만들지 않습니다",
            "해당 unit을 제외로 갱신하고 cursor를 정확히 한 칸 전진시킨 뒤 즉시 멈춥니다",
            "최종 네 산출물을 원자적으로 교체하고 실패하면 기존 bytes를 복원",
            "`.staging/report-pr-N.json`은 final output이 아닌 renderer input",
            "repository 불일치 때 final output bytes는 그대로 유지",
            "`<owner>-<repo>`는 입력 owner/repo의 철자를 보존하고 slash 하나만 hyphen으로 바꿉니다",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_both_adapters_close_second_forward_test_ambiguities(self):
        required = (
            "`--since`는 초기 목록에서 적용하고, `--path`는 파일 메타데이터를 조회한 뒤 적용",
            "`excluded:true`와 `exclusionReason:\"semantic_revalidation\"`을 기록",
            "배열에서 제거하지 않으므로 cursor 인덱스는 안정적",
            "정상 흐름에서는 render 성공만 확인한 뒤 회고 퀴즈를 발행",
            "`rebuild-index`도 manifest와 index를 원자적으로 교체하고 실패하면 기존 bytes를 복원",
            "정규화 경로가 같아도 기존 state 또는 data의 repository가 다르면 경로 충돌",
        )
        forbidden = ("render와 rebuild-index가 성공한 뒤에만",)
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)
                for phrase in forbidden:
                    self.assertNotIn(phrase, text)

    def test_both_adapters_define_remaining_filter_and_state_edges(self):
        required = (
            "`--path DIR`은 정규화한 파일 경로가 DIR과 같거나 `DIR/` prefix인 경우",
            "`--since YYYY-MM-DD`는 UTC 자정 이상인 `mergedAt`을 포함",
            "일반 PR 모드도 파일 메타데이터를 조회한 뒤 `--path`를 적용",
            "선정용 최소 diff 조회는 현재 unit의 전체 상세 조회 한도와 별도",
            "`changedFiles`·`files`를 다시 조회하고 `gh pr diff --name-only`로 파일 목록을 보완",
            "state를 쓴 뒤 다시 읽어 schema·owner/repo·units·cursor를 확인",
            "render 성공 뒤 `pendingQuiz` 저장이 실패하면 산출물은 유지하고 퀴즈는 발행하지 않습니다",
            "다음 재시도는 같은 PR을 idempotent하게 다시 render",
            "`pendingQuiz`가 현재 cursor unit과 불일치하면 상태를 바꾸지 않고 `reset`을 요구",
        )
        for adapter, text in self.adapter_texts().items():
            with self.subTest(adapter=adapter):
                for phrase in required:
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
