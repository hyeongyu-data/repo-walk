# Codex 플러그인 참조

> Last Updated: 2026-07-16

Codex 전용 `repo-walk` 플러그인의 구조·설치·검증 기준을 설명합니다. Claude Code
커맨드와 같은 학습 목적을 가지지만, 매니페스트와 호출 방식은 공유하지 않습니다.

## 구조와 책임

- `plugins/repo-walk/.codex-plugin/plugin.json`: Codex 플러그인 이름·버전·표시 정보와
  스킬 경로를 정의합니다.
- `plugins/repo-walk/skills/repo-walk/SKILL.md`: GitHub 역사 수집·지연 조회·해설·퀴즈
  상태 전이를 지시하는 Codex 전용 스킬입니다.
- `.agents/plugins/marketplace.json`: 저장소 marketplace 이름과 플러그인 소스 경로를
  연결합니다. `.agents`는 `.claude`의 별칭이므로 Git에는 `.claude/plugins/` 경로로
  기록됩니다.

## 설치와 호출

사용자는 다음 명령으로 이 저장소 marketplace를 등록한 뒤 플러그인을 설치합니다.

```bash
codex plugin marketplace add hyeongyu-data/repo-walk --ref main
codex plugin add repo-walk@repo-walk
```

설치 뒤에는 새 Codex 스레드에서 `repo-walk` 스킬을 선택하거나 대상 `owner/repo`를
포함한 자연어 요청을 보냅니다. `/repo-walk`는 Claude Code 전용 슬래시 커맨드이므로
Codex 설치 안내에 사용하지 않습니다.

## 동작과 보안 기준

- 스킬은 `gh auth status`를 확인하고 PR 중심·`--timeline`·필터·지연 조회·퀴즈 대기
  상태를 다룹니다.
- `pendingQuiz`에는 최소 메타데이터만 저장하며, 채점 또는 `skip` 뒤에만 cursor를
  전진시킵니다.
- 원격 GitHub 데이터는 비신뢰 데이터로 처리하고 읽기 전용 `gh` 조회만 허용합니다.
  `gh api` 호출에는 `--method GET`을 명시합니다.
- Codex 패키지는 Claude Code의 `.claude-plugin`·`commands/`에 의존하지 않습니다.
  기능을 바꿀 때 두 패키지의 동작을 의도적으로 맞출지, 플랫폼별로 다르게 둘지를
  PR에 명시합니다.

## 검증

```bash
CODEX_HOME="$(mktemp -d)"
export CODEX_HOME
codex plugin marketplace add "$(pwd)"
codex plugin add repo-walk@repo-walk
git diff --check
```

실제 사용 환경에서 플러그인을 변경해 재설치할 때는 Codex cachebuster를 갱신한 뒤
`codex plugin add repo-walk@repo-walk`로 재설치하고, 새 Codex 스레드에서 스킬이
갱신됐는지 확인합니다.
