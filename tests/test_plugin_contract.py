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


if __name__ == "__main__":
    unittest.main()
