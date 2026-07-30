# Codex 플러그인 참조

> Last Updated: 2026-07-30

Codex 전용 `repo-walk` 플러그인의 구조·설치·검증 기준을 설명합니다. Claude Code
커맨드와 같은 학습 목적을 가지지만, 매니페스트와 호출 방식은 공유하지 않습니다.

## 구조와 책임

- `plugins/repo-walk/.codex-plugin/plugin.json`: Codex 플러그인 이름·버전·표시 정보와
  스킬 경로를 정의합니다.
- `plugins/repo-walk/skills/repo-walk/SKILL.md`: GitHub 역사 수집·지연 조회·해설·퀴즈
  상태 전이와 `--report` 오케스트레이션을 지시하는 Codex 전용 스킬입니다.
- `plugins/repo-walk/scripts/repo_walk_report.py`: 설치된 Codex 패키지 안에서
  PR 파일 역할을 분류하고 구조화 JSON을 검증해 PR별 HTML과 전체 `index.html`을
  만드는 표준 라이브러리 CLI입니다. SKILL 위치에서 plugin root를 절대 경로로
  해석해 실행하며 대상 저장소의 상대 경로에 의존하지 않습니다.
- `.agents/plugins/marketplace.json`: 저장소 marketplace 이름과 플러그인 소스 경로를
  연결합니다. `.agents`는 `.claude`의 별칭이므로 Git에는 `.claude/plugins/` 경로로
  기록됩니다.

Claude 패키지의 `scripts/repo_walk_report.py`와 Codex 패키지 사본은 같은 JSON·HTML
계약을 구현하지만, 독립 설치를 위해 서로의 파일에 의존하지 않습니다. 구현을 바꿀
때는 두 사본을 함께 수정하고 바이트 단위 동기화 테스트를 통과시킵니다.

## 설치와 호출

사용자는 다음 명령으로 이 저장소 marketplace를 등록한 뒤 플러그인을 설치합니다.

```bash
codex plugin marketplace add hyeongyu-data/repo-walk --ref main
codex plugin add repo-walk@repo-walk
```

설치 뒤에는 새 Codex 스레드에서 플랫폼에 맞는 명시 호출 문법을 사용합니다.

```text
# Codex CLI
$repo-walk:repo-walk owner/repo
$repo-walk:repo-walk owner/repo --report
$repo-walk:repo-walk owner/repo --timeline
$repo-walk:repo-walk owner/repo next

# Codex 데스크톱 앱
@repo-walk owner/repo
```

Codex CLI의 스킬 이름은 플러그인 이름공간을 포함합니다. `/repo-walk`는 Claude Code
전용 슬래시 커맨드이므로 Codex 설치 안내에 사용하지 않습니다. 자연어 요청도 가능하지만,
명시 호출을 사용하면 대상 플러그인을 확실히 선택할 수 있습니다.

## 동작과 보안 기준

- 스킬은 `gh auth status`를 확인하고 PR 중심·`--timeline`·필터·지연 조회·퀴즈 대기
  상태를 다룹니다. 심화 질문은 질문·왜 중요한가·모범 답안을 즉시 함께 보여주고,
  회고 퀴즈와 달리 답변·채점·cursor 전진을 요구하지 않습니다.
- `pendingQuiz`에는 최소 메타데이터만 저장하며, 채점 또는 `skip` 뒤에만 cursor를
  전진시킵니다.
- `--report`는 머지된 PR 가운데 파일 역할과 diff 기반 의미 판정을 모두 통과한
  동작·critical 변경만 `.repo-walk/reports/<owner>-<repo>/`에 저장합니다. 문서·
  테스트·생성물·vendor 전용과 외형·문구 전용 변경은 제외하고, 기능성 Markdown과
  critical 후보도 실제 동작·운영 영향이 확인된 경우에만 포함합니다.
- 리포트 도구의 입력 작성·분류·렌더링·인덱스 재구축 중 하나라도 실패하면
  cursor와 `pendingQuiz`를 유지하고 퀴즈를 내기 전에 중단합니다.
- 원격 GitHub 데이터는 비신뢰 데이터로 처리하고 읽기 전용 `gh` 조회만 허용합니다.
  `gh api` 호출에는 `--method GET`을 명시합니다.
- 리포트 HTML은 원격 텍스트를 escape하고 외부 JavaScript·CDN을 사용하지 않습니다.
  private 저장소의 해설·코드 근거는 로컬 민감 데이터로 취급하며 자동으로
  업로드·배포·게시하지 않습니다.
- Codex 패키지는 Claude Code의 `.claude-plugin`·`commands/`에 의존하지 않습니다.
  기능을 바꿀 때 두 패키지의 동작을 의도적으로 맞출지, 플랫폼별로 다르게 둘지를
  PR에 명시합니다.

## 검증

```bash
repo_walk_codex_home="$(mktemp -d)"
CODEX_HOME="$repo_walk_codex_home" codex plugin marketplace add "$(pwd)"
CODEX_HOME="$repo_walk_codex_home" codex plugin add repo-walk@repo-walk
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
cmp -s scripts/repo_walk_report.py plugins/repo-walk/scripts/repo_walk_report.py
python3 /Users/buzz/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/repo-walk/skills/repo-walk
python3 /Users/buzz/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/repo-walk
git diff --check
```

실제 사용 환경에서 플러그인을 변경해 재설치할 때는 Codex cachebuster를 갱신한 뒤
`codex plugin add repo-walk@repo-walk`로 재설치하고, 새 Codex 스레드에서 스킬이
갱신됐는지 확인합니다. cachebuster는 매니페스트의 base version을 먼저 바꾼 뒤
다음 공식 helper로 생성하며 직접 suffix를 이어 붙이지 않습니다.

```bash
python3 /Users/buzz/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/repo-walk
```
