from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PluginPackageTests(unittest.TestCase):
    def test_claude_report_script_exists(self):
        self.assertTrue((ROOT / "scripts/repo_walk_report.py").is_file())

    def test_codex_report_script_exists_inside_plugin(self):
        self.assertTrue(
            (ROOT / "plugins/repo-walk/scripts/repo_walk_report.py").is_file()
        )

    def test_claude_python_permission_is_not_a_broad_wildcard(self):
        frontmatter = (ROOT / "commands/repo-walk.md").read_text(
            encoding="utf-8"
        ).split("---", 2)[1]
        self.assertNotIn("Bash(python3:*)", frontmatter)


if __name__ == "__main__":
    unittest.main()
