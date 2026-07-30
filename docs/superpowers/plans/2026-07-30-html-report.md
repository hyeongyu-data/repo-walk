# 중요 변경 HTML 리포트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** repo-walk의 `--report` 모드에서 머지된 실제 동작·critical 변경만 선별하고 PR별 HTML과 전체 요약 HTML을 로컬에 누적 생성한다.

**Architecture:** Claude Code와 Codex 어댑터는 기존 `gh` 읽기와 LLM 해설을 담당하고, 각 독립 패키지에 포함된 동일한 Python 표준 라이브러리 도구가 경로 분류·JSON 검증·안전한 HTML 렌더링을 담당한다. PR별 구조화 JSON을 진실의 원천으로 삼아 개별 HTML과 manifest/index를 원자적으로 재생성한다.

**Tech Stack:** Python 3 표준 라이브러리(`argparse`, `html`, `json`, `pathlib`, `tempfile`, `unittest`), `gh` CLI, Claude Code command Markdown, Codex skill Markdown

## Global Constraints

- 모든 `.md`와 코드 주석은 한국어로 작성한다.
- 외부 Python 패키지, JavaScript, CSS CDN, DB, 별도 API 키를 추가하지 않는다.
- GitHub 데이터 조회는 기존 읽기 전용 `gh` 호출에만 남긴다.
- 리포트는 `.repo-walk/reports/<owner>-<repo>/` 아래에만 저장한다.
- 원격 제목·본문·리뷰·코드·파일명은 모두 HTML escape한다.
- 기본 학습 모드는 보존하고 사용자가 `--report`를 지정했을 때만 필터·파일 저장을 활성화한다.
- Claude와 Codex 패키지는 서로의 파일에 의존하지 않으며 두 렌더러 사본의 일치를 테스트한다.
- 기존 미추적 `.DS_Store`를 스테이징하거나 수정하지 않는다.

## 파일 구조

- Create: `scripts/repo_walk_report.py` — Claude 패키지의 분류·렌더링 CLI
- Create: `plugins/repo-walk/scripts/repo_walk_report.py` — Codex 패키지에 독립 포함되는 동일 CLI
- Create: `tests/test_repo_walk_report.py` — 분류·렌더링·CLI·두 사본 동기화 테스트
- Create: `tests/test_plugin_contract.py` — 패키지 경로·frontmatter 최소 권한 검증
- Create: `tests/fixtures/pr-21.json` — docs-only 회귀 입력
- Create: `tests/fixtures/pr-23.json` — 기능성 Markdown 회귀 입력
- Create: `tests/fixtures/pr-25.json` — 매니페스트 critical 회귀 입력
- Create: `tests/fixtures/report-23.json` — HTML escape와 시각 검증용 리포트
- Create: `tests/fixtures/report-25.json` — 다중 카드 인덱스 검증용 리포트
- Modify: `commands/repo-walk.md` — Claude `--report` 수집·판정·렌더링 흐름
- Modify: `plugins/repo-walk/skills/repo-walk/SKILL.md` — Codex의 동일 흐름
- Modify: `.claude-plugin/plugin.json` — Claude 기능 버전 갱신
- Modify: `plugins/repo-walk/.codex-plugin/plugin.json` — Codex 기능 버전·cachebuster 갱신
- Modify: `README.md` — 공통 사용법·필터·산출물·보안 설명
- Modify: `plugins/repo-walk/README.md` — Codex 사용법
- Modify: `.claude/docs/agent-command-reference.md` — Claude 옵션·검증 계약
- Modify: `.claude/docs/agent-codex-plugin-reference.md` — Codex 도구·검증 계약
- Modify: `.claude/docs/architecture-overview.md` — 리포트 데이터 흐름
- Modify: `.claude/docs/agent-project-reference.md` — 새 파일 책임
- Modify: `.claude/docs/agent-security-guidelines.md` — private 리포트 보관 경계
- Modify: `CLAUDE.md` — 프로젝트 구조·로컬 검증 명령

---

### Task 1: 결정론적 PR 파일 분류기

**Files:**
- Create: `scripts/repo_walk_report.py`
- Create: `plugins/repo-walk/scripts/repo_walk_report.py`
- Create: `tests/test_repo_walk_report.py`
- Create: `tests/fixtures/pr-21.json`
- Create: `tests/fixtures/pr-23.json`
- Create: `tests/fixtures/pr-25.json`

**Interfaces:**
- Consumes: `classify` 입력 JSON `{repository, pr:{number,state,mergedAt,changedFiles,files:[{path}]}}`
- Produces: `classify_pull_request(payload: dict) -> dict`와 CLI JSON `{decision, reason, roles, candidateKind, classifierVersion, inputDigest}`

- [ ] **Step 1: 대표 필터 fixture의 실패 테스트 작성**

실제 저장소 회귀 fixture는 다음 파일 목록을 사용한다.

```json
{"repository":"hyeongyu-data/repo-walk","pr":{"number":21,"state":"MERGED","mergedAt":"2026-07-17T14:03:24Z","changedFiles":3,"files":[{"path":".claude/docs/agent-codex-plugin-reference.md"},{"path":"README.md"},{"path":"plugins/repo-walk/README.md"}]}}
```

```json
{"repository":"hyeongyu-data/repo-walk","pr":{"number":23,"state":"MERGED","mergedAt":"2026-07-17T15:06:44Z","changedFiles":2,"files":[{"path":"commands/repo-walk.md"},{"path":"plugins/repo-walk/skills/repo-walk/SKILL.md"}]}}
```

```json
{"repository":"hyeongyu-data/repo-walk","pr":{"number":25,"state":"MERGED","mergedAt":"2026-07-27T08:56:27Z","changedFiles":2,"files":[{"path":".claude-plugin/plugin.json"},{"path":"plugins/repo-walk/.codex-plugin/plugin.json"}]}}
```

```python
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
```

- [ ] **Step 2: 테스트를 실행해 모듈 부재 실패 확인**

Run: `python3 -m unittest tests.test_repo_walk_report.ClassificationTests -v`

Expected: FAIL with `FileNotFoundError` 또는 import 대상 `scripts/repo_walk_report.py` 부재

- [ ] **Step 3: 최소 경로 역할 분류와 hard gate 구현**

```python
CLASSIFIER_VERSION = "1"

def classify_path(path: str, repository: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    if repository == "hyeongyu-data/repo-walk" and (
        normalized == "commands/repo-walk.md"
        or normalized.startswith("plugins/repo-walk/skills/")
        or normalized.startswith("codex/prompts/")
    ):
        return "runtime"
    if is_critical_path(normalized):
        return "critical"
    if is_test_path(normalized):
        return "test"
    if is_generated_or_vendor_path(normalized):
        return "generated"
    if is_docs_path(normalized):
        return "docs"
    if is_runtime_path(normalized):
        return "runtime"
    return "other"

def classify_pull_request(payload: dict) -> dict:
    validated = validate_classification_input(payload)
    pr = validated["pr"]
    if pr["state"] != "MERGED" or not pr["mergedAt"]:
        return classification_result(validated, "exclude", "unmerged")
    if pr["changedFiles"] != len(pr["files"]):
        return classification_result(validated, "review", "incomplete_metadata")
    roles = [classify_path(item["path"], validated["repository"]) for item in pr["files"]]
    if not roles or set(roles) == {"other"}:
        return classification_result(validated, "review", "unknown_files", roles)
    if set(roles) <= {"docs", "test", "generated"}:
        reason = sole_or_mixed_non_runtime_reason(roles)
        return classification_result(validated, "exclude", reason, roles)
    candidate_kind = "critical" if "critical" in roles else "runtime"
    return classification_result(validated, "candidate", "eligible_files", roles, candidate_kind)
```

- [ ] **Step 4: 분류 테스트 통과 확인**

Run: `python3 -m unittest tests.test_repo_walk_report.ClassificationTests -v`

Expected: 모든 분류 테스트 PASS

- [ ] **Step 5: Codex 사본 생성과 동기화 테스트 추가**

```python
def test_claude_and_codex_scripts_are_identical(self):
    root = Path(__file__).resolve().parents[1]
    self.assertEqual(
        (root / "scripts/repo_walk_report.py").read_bytes(),
        (root / "plugins/repo-walk/scripts/repo_walk_report.py").read_bytes(),
    )
```

Run: `mkdir -p plugins/repo-walk/scripts && cp scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py && python3 -m unittest tests.test_repo_walk_report -v`

Expected: 모든 테스트 PASS

- [ ] **Step 6: 분류기 커밋**

```bash
git add scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py tests/test_repo_walk_report.py
git commit -m "feat: 중요 변경 분류기 추가"
```

### Task 2: 안전한 PR HTML과 요약 인덱스 렌더러

**Files:**
- Modify: `scripts/repo_walk_report.py`
- Modify: `plugins/repo-walk/scripts/repo_walk_report.py`
- Modify: `tests/test_repo_walk_report.py`
- Create: `tests/fixtures/report-23.json`
- Create: `tests/fixtures/report-25.json`

**Interfaces:**
- Consumes: 스키마 1 리포트 JSON의 `pr`, `classification`, `summary`, `overview`, `sections`
- Produces: `render_report(report: dict, output_root: Path) -> Path`, `rebuild_index(output_root: Path) -> Path`, `data/pr-N.json`, `prs/pr-N.html`, `manifest.json`, `index.html`

- [ ] **Step 1: escape·중복 방지·인덱스 생성 실패 테스트 작성**

`tests/fixtures/report-23.json`은 모든 block 타입과 악성 문자열을 포함한다.

```json
{
  "schemaVersion": 1,
  "repository": "hyeongyu-data/repo-walk",
  "generatedAt": "2026-07-30T02:00:00Z",
  "pr": {
    "number": 23,
    "title": "심화 질문 제공 <script>alert('x')</script>",
    "url": "https://github.com/hyeongyu-data/repo-walk/pull/23",
    "mergedAt": "2026-07-17T15:06:44Z"
  },
  "classification": {
    "kind": "behavior",
    "operationalImpact": "material",
    "confidence": "high",
    "reasons": ["기능성 Markdown이 해설 동작을 변경함"],
    "files": ["commands/repo-walk.md", "plugins/repo-walk/skills/repo-walk/SKILL.md"]
  },
  "summary": "심화 질문에 근거 기반 모범 답안을 추가했습니다.",
  "overview": {
    "problem": "질문만으로는 학습자가 판단을 검증하기 어려웠습니다.",
    "keyChanges": "왜 중요한가와 모범 답안 계약을 추가했습니다.",
    "impact": "Claude와 Codex의 학습 출력이 바뀝니다.",
    "next": "HTML 리포트에서도 같은 구조를 보존합니다."
  },
  "sections": [
    {
      "title": "1. 변경 해설",
      "blocks": [
        {"type": "paragraph", "text": "기능성 Markdown은 실행 로직으로 분류합니다."},
        {"type": "list", "items": ["질문", "근거", "트레이드오프"]},
        {"type": "code", "path": "commands/<repo-walk>.md", "line": 210, "language": "markdown", "code": "<script>이 문자열은 실행되면 안 됩니다.</script>"}
      ]
    },
    {
      "title": "2. 리뷰 해설",
      "blocks": [
        {"type": "quote", "author": "reviewer", "text": "근거를 함께 보여주세요."}
      ]
    },
    {
      "title": "3. 직접 코드리뷰",
      "blocks": [
        {"type": "finding", "severity": "중간", "confidence": "높음", "path": "commands/repo-walk.md", "line": 210, "finding": "두 플랫폼 계약이 어긋날 수 있습니다.", "suggestion": "계약 테스트를 추가합니다."}
      ]
    },
    {
      "title": "4. 학습 포인트",
      "blocks": [
        {"type": "question", "question": "왜 기능성 Markdown을 코드로 보아야 하나요?", "importance": "확장자만 보면 실제 동작 변경을 누락하기 때문입니다.", "answer": "실행 시 소비되는 경로와 diff 근거를 우선합니다."}
      ]
    }
  ]
}
```

`tests/fixtures/report-25.json`은 두 번째 인덱스 카드와 critical 배지를 검증한다.

```json
{
  "schemaVersion": 1,
  "repository": "hyeongyu-data/repo-walk",
  "generatedAt": "2026-07-30T02:05:00Z",
  "pr": {
    "number": 25,
    "title": "플러그인 version 갱신",
    "url": "https://github.com/hyeongyu-data/repo-walk/pull/25",
    "mergedAt": "2026-07-27T08:56:27Z"
  },
  "classification": {
    "kind": "critical",
    "operationalImpact": "critical",
    "confidence": "high",
    "reasons": ["설치 캐시 무효화에 필요한 배포 매니페스트 변경"],
    "files": [".claude-plugin/plugin.json", "plugins/repo-walk/.codex-plugin/plugin.json"]
  },
  "summary": "플러그인 캐시가 새 동작을 배포하도록 버전을 갱신했습니다.",
  "overview": {
    "problem": "버전이 같으면 설치 캐시에 이전 스킬이 남습니다.",
    "keyChanges": "두 플랫폼 매니페스트 버전을 올렸습니다.",
    "impact": "새 설치와 재설치가 최신 동작을 받습니다.",
    "next": "기능 변경마다 버전 계약을 검증합니다."
  },
  "sections": [
    {
      "title": "1. 변경 해설",
      "blocks": [
        {"type": "paragraph", "text": "매니페스트는 실행 코드가 아니어도 배포 결과를 바꿉니다."}
      ]
    }
  ]
}
```

```python
class RenderingTests(unittest.TestCase):
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
            before = (root / "prs/pr-23.html").read_bytes()
            with self.assertRaises(report.ReportValidationError):
                report.render_report({"schemaVersion": 1}, root)
            self.assertEqual(before, (root / "prs/pr-23.html").read_bytes())

    def test_corrupt_manifest_is_rebuilt_from_data_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(make_report(), root)
            (root / "manifest.json").write_text("{broken")
            report.rebuild_index(root)
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual([23], [entry["number"] for entry in manifest["reports"]])

    def test_non_github_url_is_rendered_as_text(self):
        payload = make_report(url="javascript:alert(1)")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report.render_report(payload, root)
            output = (root / "prs/pr-23.html").read_text()
            self.assertNotIn('href="javascript:', output)
```

- [ ] **Step 2: 렌더링 테스트 실패 확인**

Run: `python3 -m unittest tests.test_repo_walk_report.RenderingTests -v`

Expected: FAIL with missing `render_report` 또는 `ReportValidationError`

- [ ] **Step 3: 스키마 검증·typed block 렌더링 구현**

```python
class ReportValidationError(ValueError):
    pass

def validate_report(payload: dict) -> dict:
    require_mapping(payload, "report")
    require_equal(payload, "schemaVersion", 1)
    require_string(payload, "repository")
    require_string(payload, "generatedAt")
    validate_pr(payload.get("pr"))
    validate_classification(payload.get("classification"))
    require_string(payload, "summary")
    validate_overview(payload.get("overview"))
    validate_sections(payload.get("sections"))
    return payload

def render_block(block: dict) -> str:
    block_type = block["type"]
    if block_type == "paragraph":
        return f"<p>{escape(block['text'])}</p>"
    if block_type == "code":
        label = f"{block['path']}:{block['line']}"
        return (
            f'<figure class="code"><figcaption>{escape(label)}</figcaption>'
            f"<pre><code>{escape(block['code'])}</code></pre></figure>"
        )
    return render_supported_non_code_block(block)
```

- [ ] **Step 4: 원자적 저장과 manifest/index 재구축 구현**

```python
def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                            delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)

def render_report(payload: dict, output_root: Path) -> Path:
    validated = validate_report(payload)
    number = validated["pr"]["number"]
    atomic_write_json(output_root / f"data/pr-{number}.json", validated)
    unit_path = output_root / f"prs/pr-{number}.html"
    atomic_write_text(unit_path, render_unit_html(validated))
    rebuild_index(output_root)
    return unit_path
```

- [ ] **Step 5: 렌더링·전체 테스트 통과와 Codex 사본 동기화**

Run: `cp scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py && python3 -m unittest tests.test_repo_walk_report -v`

Expected: escape, URL 제한, 원자적 갱신, 중복 방지, 복구, 사본 일치 테스트 모두 PASS

- [ ] **Step 6: 렌더러 커밋**

```bash
git add scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py tests/test_repo_walk_report.py
git commit -m "feat: PR HTML과 요약 인덱스 렌더링"
```

### Task 3: CLI 계약과 두 플랫폼 리포트 흐름

**Files:**
- Modify: `scripts/repo_walk_report.py`
- Modify: `plugins/repo-walk/scripts/repo_walk_report.py`
- Create: `tests/test_plugin_contract.py`
- Modify: `commands/repo-walk.md`
- Modify: `plugins/repo-walk/skills/repo-walk/SKILL.md`

**Interfaces:**
- Consumes: `--report`, `.repo-walk/...`의 분류 입력·리포트 JSON
- Produces: `classify --input PATH`, `render --input PATH --output-dir PATH`, `rebuild-index --output-dir PATH` CLI와 플랫폼별 실행 지침

- [ ] **Step 1: 기존 스킬의 `--report` baseline 실패를 새 에이전트로 기록**

현재 `plugins/repo-walk/skills/repo-walk/SKILL.md`만 제공한 새 에이전트에게 다음
사용 요청을 전달하고 `.superpowers/sdd/.../task-3-skill-baseline.md`에 결과를
기록한다.

```text
Use the repo-walk skill at the supplied path. Without network access or file changes,
explain the exact steps and output paths for:
repo-walk hyeongyu-data/repo-walk --report
```

Expected baseline failure: 기존 스킬은 `--report`를 파싱하지 못하고 PR별 HTML,
`manifest.json`, `index.html` 생성 절차를 제시하지 못한다.

- [ ] **Step 2: CLI 실패 테스트와 패키지 경계 검증 작성**

```python
def test_classify_cli_writes_json(self):
    with TemporaryDirectory() as directory:
        source = Path(directory) / "input.json"
        source.write_text(json.dumps(make_classification_input(["README.md"])))
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "classify", "--input", str(source)],
            text=True, capture_output=True, check=True,
        )
        self.assertEqual("docs_only", json.loads(completed.stdout)["reason"])

class PluginPackageTests(unittest.TestCase):
    def test_claude_report_script_exists(self):
        self.assertTrue((ROOT / "scripts/repo_walk_report.py").is_file())

    def test_codex_report_script_exists_inside_plugin(self):
        self.assertTrue((ROOT / "plugins/repo-walk/scripts/repo_walk_report.py").is_file())

    def test_claude_python_permission_is_not_a_broad_wildcard(self):
        frontmatter = (ROOT / "commands/repo-walk.md").read_text().split("---", 2)[1]
        self.assertNotIn("Bash(python3:*)", frontmatter)
```

- [ ] **Step 3: CLI 테스트 실패 확인**

Run: `python3 -m unittest tests.test_plugin_contract tests.test_repo_walk_report.CliTests -v`

Expected: CLI subcommand 부재로 FAIL

- [ ] **Step 4: argparse 기반 CLI 구현**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="repo-walk HTML 리포트 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    classify = subparsers.add_parser("classify")
    classify.add_argument("--input", required=True, type=Path)
    render = subparsers.add_parser("render")
    render.add_argument("--input", required=True, type=Path)
    render.add_argument("--output-dir", required=True, type=Path)
    rebuild = subparsers.add_parser("rebuild-index")
    rebuild.add_argument("--output-dir", required=True, type=Path)
    return parser
```

CLI는 JSON 오류에 종료 코드 2, 검증 오류에 종료 코드 3, 파일 쓰기 오류에 종료 코드
4를 사용하고 민감 원문을 stderr에 출력하지 않는다.

- [ ] **Step 5: Claude command에 `--report` 상태·필터·렌더링 전이 추가**

다음 순서를 `commands/repo-walk.md`에 실제 명령 예시와 함께 명시한다.

```text
merged 후보 수집
→ PR별 gh pr view --json state,mergedAt,changedFiles,files
→ classify CLI
→ exclude면 최소 이유를 상태에 기록하고 다음 후보
→ candidate면 diff 근거 의미 판정
→ include면 기존 해설 + schema 1 JSON 작성
→ render CLI
→ 퀴즈 발행, cursor는 그대로
```

Claude frontmatter에는 저장소 안의 정확한 스크립트 경로를 실행하는 최소
`Bash(python3 ...)` 허용만 추가한다.

순회 상태는 `"schemaVersion": 3`으로 올리고 기존 상태에는 `reportMode:false`,
각 unit에는 필요한 경우 `classification:{decision,reason,classifierVersion,
inputDigest}`만 추가한다. 코드·리뷰·해설 원문은 상태 파일에 넣지 않는다.

- [ ] **Step 6: Codex skill에 같은 판정·JSON·렌더링 계약 추가**

Codex 패키지 안의 `plugins/repo-walk/scripts/repo_walk_report.py`를 사용하고,
Claude와 동일하게 필터 뒤 limit, incomplete metadata review, idempotent render,
private 저장 경고를 명시한다.

- [ ] **Step 7: 변경된 스킬을 같은 시나리오로 forward-test**

새 에이전트에 수정된 skill 경로와 Step 1의 동일한 사용 요청만 제공한다. 성공
조건은 다음 네 항목을 모두 스스로 찾아 설명하는 것이다.

- 머지 PR만 수집하고 파일 분류 뒤 limit 적용
- 기능성 Markdown과 critical 후보의 diff 근거 의미 판정
- `data/pr-N.json`, `prs/pr-N.html`, `manifest.json`, `index.html`
- private 저장 경고와 원격 텍스트 escape

결과는 `.superpowers/sdd/.../task-3-skill-forward.md`에 기록한다.

- [ ] **Step 8: CLI·패키지·전체 테스트 통과**

Run: `cp scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py && python3 -m unittest discover -s tests -v`

Expected: 모든 테스트 PASS

- [ ] **Step 9: 플랫폼 통합 커밋**

```bash
git add scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py tests/test_repo_walk_report.py tests/test_plugin_contract.py commands/repo-walk.md plugins/repo-walk/skills/repo-walk/SKILL.md
git commit -m "feat: repo-walk 리포트 모드 연동"
```

### Task 4: 버전·사용법·보안 문서 동기화

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `plugins/repo-walk/.codex-plugin/plugin.json`
- Modify: `README.md`
- Modify: `plugins/repo-walk/README.md`
- Modify: `.claude/docs/agent-command-reference.md`
- Modify: `.claude/docs/agent-codex-plugin-reference.md`
- Modify: `.claude/docs/architecture-overview.md`
- Modify: `.claude/docs/agent-project-reference.md`
- Modify: `.claude/docs/agent-security-guidelines.md`
- Modify: `CLAUDE.md`
- Modify: `tests/test_plugin_contract.py`

**Interfaces:**
- Consumes: Task 3의 `--report` CLI·산출물 경로
- Produces: 설치 후 발견 가능한 사용법, `0.3.0` 기능 버전, private 보관 정책

- [ ] **Step 1: 매니페스트 버전과 사용자 문서 갱신**

- Claude 버전: `0.3.0`
- Codex base version을 `0.3.0`으로 바꾼 뒤 plugin-creator의
  `update_plugin_cachebuster.py`를 실행해 `0.3.0+codex.<UTC timestamp>` 형식으로
  갱신
- README 사용 예: `/repo-walk owner/repo --report`,
  `$repo-walk:repo-walk owner/repo --report`
- 출력 위치와 `index.html` 여는 법
- 문서/테스트/생성물/외형 제외 및 기능성 Markdown·critical 포함 규칙
- private 저장소 리포트는 로컬에 남고 자동 배포하지 않는다는 경고

Codex base version 수정 뒤 다음 공식 helper를 실행한다.

```bash
python3 /Users/buzz/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/repo-walk
```

- [ ] **Step 2: 에이전트 참조 문서와 검증 명령 갱신**

`CLAUDE.md`와 `.claude/docs/`에 두 스크립트 책임, 표준 라이브러리 예외 근거,
`python3 -m unittest discover -s tests -v` 검증, 리포트 보안 경계를 반영한다.

- [ ] **Step 3: 전체 테스트와 공식 validator 확인**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); json.load(open('plugins/repo-walk/.codex-plugin/plugin.json')); print('json ok')"
python3 /Users/buzz/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/repo-walk/skills/repo-walk
python3 /Users/buzz/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/repo-walk
git diff --check
```

Expected: 전체 테스트 PASS, `json ok`, diff 오류 없음

- [ ] **Step 4: 문서·버전 커밋**

```bash
git add .claude-plugin/plugin.json plugins/repo-walk/.codex-plugin/plugin.json README.md plugins/repo-walk/README.md .claude/docs CLAUDE.md tests/test_plugin_contract.py
git commit -m "docs: HTML 리포트 사용법과 보안 경계 추가"
```

### Task 5: 실제 fixture 렌더링과 설치 검증

**Files:**
- Modify only if verification exposes a defect: files owned by Tasks 1–4

**Interfaces:**
- Consumes: 완성된 분류·렌더링 CLI와 두 플러그인 패키지
- Produces: 네트워크 없는 샘플 HTML, 격리 설치 결과, 최종 검증 증거

- [ ] **Step 1: #21·#23·#25 회귀 fixture 분류**

Run:

```bash
python3 scripts/repo_walk_report.py classify --input tests/fixtures/pr-21.json
python3 scripts/repo_walk_report.py classify --input tests/fixtures/pr-23.json
python3 scripts/repo_walk_report.py classify --input tests/fixtures/pr-25.json
```

Expected:

- #21: `exclude/docs_only`
- #23: `candidate/runtime`
- #25: `candidate/critical`

- [ ] **Step 2: 악성 문자열을 포함한 샘플 리포트 렌더링**

Run:

```bash
python3 scripts/repo_walk_report.py render --input tests/fixtures/report-23.json --output-dir .repo-walk/verification/html
python3 scripts/repo_walk_report.py render --input tests/fixtures/report-25.json --output-dir .repo-walk/verification/html
```

Expected: `prs/pr-23.html`, `prs/pr-25.html`, `manifest.json`, `index.html` 생성

- [ ] **Step 3: 브라우저로 개별·인덱스 HTML 시각 검증**

`.repo-walk/verification/html/index.html`과 `prs/pr-23.html`을 로컬 브라우저에서
열고 다음을 확인한다.

- 좁은 화면과 넓은 화면에서 카드·코드가 잘리지 않음
- 외부 네트워크 요청 없음
- 악성 `<script>` 문자열이 텍스트로만 표시됨
- 인덱스 카드가 PR HTML로 연결됨
- 제목·요약·분류·영향 파일이 한 화면에서 구분됨

- [ ] **Step 4: Claude·Codex 패키지 검증**

Run:

```bash
head -20 commands/repo-walk.md
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py
git diff --check
```

Codex 격리 설치:

```bash
repo_walk_codex_home="$(mktemp -d)"
CODEX_HOME="$repo_walk_codex_home" codex plugin marketplace add "$(pwd)"
CODEX_HOME="$repo_walk_codex_home" codex plugin add repo-walk@repo-walk
```

Expected: 모든 명령 성공, 스크립트 사본 일치, 플러그인 설치 성공

- [ ] **Step 5: 최종 diff 자체 리뷰와 필요한 수정 커밋**

검토 순서:

1. 원격 텍스트 escape 누락
2. closed-unmerged 포함 가능성
3. 필터 전 limit 적용 문구
4. 두 플랫폼 계약 불일치
5. private 데이터 외부 전송
6. `.DS_Store` 또는 `.repo-walk` 스테이징 여부

수정이 필요할 때만 관련 파일을 고치고 다음 형식으로 커밋한다.

```bash
git add scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py tests/test_repo_walk_report.py tests/test_plugin_contract.py tests/fixtures commands/repo-walk.md plugins/repo-walk/skills/repo-walk/SKILL.md .claude-plugin/plugin.json plugins/repo-walk/.codex-plugin/plugin.json README.md plugins/repo-walk/README.md .claude/docs CLAUDE.md
git commit -m "fix: HTML 리포트 검증 결과 반영"
```
