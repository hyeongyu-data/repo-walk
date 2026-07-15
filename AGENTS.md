# AI 코딩 에이전트 작업 지침

> Version: 1.0.0 | Last Updated: 2026-07-15

이 문서는 Claude Code 등 AI 코딩 에이전트가 이 저장소에서 작업할 때의 기본
진입점입니다. 필수 규칙은 짧게 유지합니다.

## 언어 원칙

에이전트 응답, PR 코멘트, 리뷰 요약, 구현 노트는 한국어 격식체를 사용합니다.
단, **배포되는 플러그인 산출물**(`commands/*.md`, `README.md`, `plugin.json`의
`description`)은 다국어 사용자를 위해 영어로 작성합니다.

## 규칙 우선순위

규칙이 충돌하면 다음 순서로 적용합니다:

1. 사용자의 명시적 요청
2. `AGENTS.md` 및 `CLAUDE.md` symlink
3. `README.md`, 기타 저장소 문서

같은 수준이면 더 구체적이고 더 최근에 갱신된 규칙을 우선합니다.

## 프로젝트 맥락

- **repo-walk**: GitHub 저장소의 커밋·이슈·PR 역사를 한 단계씩 걸으며 Claude가
  *해설*하도록 돕는 Claude Code 슬래시 커맨드 플러그인. `gh`가 데이터를 긁고,
  해설은 Claude가 한다 — 별도 서버·API 키·DB 없음.
- 저장소 구조:
  - `.claude-plugin/plugin.json` — 플러그인 매니페스트
  - `.claude-plugin/marketplace.json` — `/plugin marketplace add`용 매니페스트
  - `commands/repo-walk.md` — 커맨드 정의 = 프롬프트 = 전체 로직 (실행 바이너리 없음)
  - `README.md`, `LICENSE`
- 기본 순회 단위는 **PR**(시간순), `--timeline`으로 커밋·이슈·PR 순수 시간순.
  진행 상태는 `.repo-walk/<owner>-<repo>.json` 커서에 저장해 이어보기.

## 핵심 규칙

- **새 추상화보다 기존 저장소 패턴을 우선합니다.** 이 플러그인은 의도적으로
  "얇은 래퍼"입니다: `gh` 하나에만 의존하고, 새 의존성·실행 파일·설정
  시스템을 추가하지 않습니다 (YAGNI). 한 줄로 되면 한 줄로.
- 커맨드 로직은 전부 `commands/repo-walk.md`에 프롬프트로 있습니다. 동작을
  바꾸면 그 파일과 `README.md`의 사용법을 같은 변경에 함께 갱신합니다.
- `plugin.json`과 `marketplace.json`의 이름·설명은 서로 어긋나지 않게 유지합니다.
- 코드가 변경되는 작업은 이슈를 먼저 발행하고, 그 이슈의 `Create a branch`로
  브랜치를 생성합니다(이슈-브랜치 자동 연결).
- 커밋 메시지·PR 본문·이슈 본문은 작성 전에 `.github/`의 템플릿
  (`PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/*.yml`)을 읽고 그 구조를 그대로
  따릅니다. 임의 형식을 쓰지 않습니다.
- **GitHub 원격에 영향을 주는 작업**(issue/PR 생성·수정, push, label, 릴리스)은
  실행 전에 사용자에게 먼저 확인받습니다.
- 커맨드가 다루는 데이터는 사용자의 `gh` 인증으로 접근합니다. 토큰·시크릿을
  커맨드에 하드코딩하거나 커밋하지 않습니다.

## 로컬 검증

이 저장소는 빌드가 없습니다. 커밋 전 최소 검증:

```bash
# 매니페스트 JSON이 유효한지
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); print('json ok')"

# 커맨드 frontmatter가 --- 로 열리고 닫히는지 육안 확인
head -20 commands/repo-walk.md
```

가능하면 실제 저장소로 `/repo-walk owner/repo`를 한 번 실행해 해설 흐름이
동작하는지 확인합니다.

## 문서 우선

비자명한 동작 변경(순회 단위, 스코프 옵션, 커서 포맷 변경 등)은 `README.md`의
사용법과 이 문서의 프로젝트 맥락을 같은 변경에서 갱신합니다.
