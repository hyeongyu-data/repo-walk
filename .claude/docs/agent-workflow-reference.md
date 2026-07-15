# 에이전트 워크플로우 참조

> Last Updated: 2026-07-15

GitHub 워크플로우 전체 가이드: Issue → Branch → Commit → PR → Review →
Merge. 이 저장소 모든 작업의 운영 표준입니다.

## 이 문서를 볼 때

- 새 작업을 시작하며 전체 워크플로우가 필요할 때
- 커밋 메시지나 PR 본문을 작성할 때
- PR이 워크플로우를 따르는지 검증할 때
- 브랜치 이름, 머지 방식이 헷갈릴 때

## 워크플로우 개요

```
Issue 생성 (form 선택 → label 자동 적용)
    ↓
Branch 생성 (이슈의 Create a branch, <type>/<이슈번호>-<설명>)
    ↓
작업/검증 (JSON 유효성, frontmatter, git diff --check)
    ↓
Draft PR 생성 → 셀프 리뷰 및 설명 보강
    ↓
Ready for review 전환
    ↓
리뷰 반영 → 사용자 승인
    ↓
Squash Merge → Issue 자동 close
```

## 에이전트 기본 규칙

- GitHub 원격에 영향을 주는 작업은 항상 사용자에게 먼저 확인받습니다:
  issue 생성·수정·close, label 변경, PR 생성·수정·**merge**, 원격 branch
  push·삭제, 저장소 설정 변경.
- 로컬 파일 읽기·수정은 진행해도 됩니다. GitHub에 반영하는 순간에만
  확인받습니다.
- 이슈·PR 기본값: Assignee는 생성자(현재 계정 `hyeongyu-data`)로 지정합니다 —
  `gh issue create`·`gh pr create`에 `--assignee @me`를 붙입니다.

## 이슈 생성

**이슈를 만드는 경우:**
- 커맨드 동작·옵션 추가·변경, 순회 단위/해설 방식 변경
- 매니페스트(`plugin.json`/`marketplace.json`) 변경
- 문서 추가·수정, 프롬프트 실험
- 리뷰 중 생긴 범위 밖 후속 작업

아주 작은 오타 수정은 바로 PR로 처리할 수 있습니다.

**Issue Forms** (`.github/ISSUE_TEMPLATE/`, 빈 이슈 생성 불가):

| Form | 제목 prefix | 자동 label | 필수 내용 |
|---|---|---|---|
| `feature.yml` | `[FEAT]` | `feature` | 목적, 작업 범위, 영향받는 컴포넌트, 완료 조건 |
| `bug.yml` | `[BUG]` | `bug` | 현상, 재현 방법, 기대 동작, 영향 컴포넌트, 환경·로그 |
| `experiment.yml` | `[EXP]` | `experiment` | 가설, 실험 대상, 판정 기준, 실험 설정, 결과 |

## 브랜치 이름

**코드가 변경되는 작업은 반드시 이슈를 먼저 발행하고, 그 이슈에서 브랜치를
생성합니다.** 이슈 우측 `Development > Create a branch`를 쓰면 브랜치가 이슈에
자동 연결되어, `main` 머지 시 이슈 자동 close가 확실해집니다.

**형식:** `<type>/<이슈번호>-<간략한-설명>` — 영어 소문자·숫자·하이픈만,
이슈 번호 포함, 한 브랜치에 하나의 목적.

**Type:** `feat/`, `fix/`, `exp/`, `docs/`, `refactor/`, `chore/`

## 커밋 메시지

**형식:** `<type>: <한국어 설명>`

| type | 의미 |
|---|---|
| `feat` | 커맨드 기능, 옵션, 매니페스트 추가 |
| `fix` | 동작·프롬프트·문서 오류 수정 |
| `exp` | 해설 방식·프롬프트 구성 실험 |
| `docs` | 문서 추가 또는 수정 |
| `refactor` | 동작 변화 없는 구조 정리 |
| `test` | 검증 스크립트 추가·수정 |
| `chore` | 저장소 기본 설정, 관리 작업 |

**규칙:** 한 커밋에 하나의 논리적 변경. 포맷 변경과 동작 변경을 섞지 않음.
제목은 현재형 50자 이내.

## PR 생성

**PR 생성 전 체크:**
- [ ] `plugin.json`/`marketplace.json` JSON 유효, 이름·설명 일치
- [ ] `commands/*.md` frontmatter(`---`)·`allowed-tools` 정상
- [ ] 동작을 바꿨다면 `README.md`·`AGENTS.md`를 같은 PR에서 갱신
- [ ] 토큰·시크릿이 포함되지 않았다
- [ ] `git diff --check` 통과
- [ ] Assignee를 생성자로 지정 (`gh pr create --assignee @me`)

**PR 본문**은 `.github/PULL_REQUEST_TEMPLATE.md` 구조를 그대로 씁니다
(작업 내용 / 변경 사항 / 관련 이슈 `Closes #N` / 체크리스트 / 리뷰어 참고).

**Draft vs Ready:** Draft에서 셀프 리뷰로 diff를 처음부터 끝까지 읽고 설명을
보강한 뒤 Ready로 전환합니다.

## 리뷰와 머지

- 이 저장소는 소규모라 승인자 수를 강제하지 않습니다. 기본은 **셀프 리뷰 +
  사용자 승인** 후 머지입니다. 에이전트는 사용자 승인 없이 머지하지 않습니다.
- **Squash and merge**를 사용합니다. 머지 커밋 제목은 `<type>: <설명> (#PR번호)`.
- `Closes #N`으로 연결된 이슈가 자동 close되고 브랜치가 삭제됩니다.

## 충돌·수정 요청

- `main` 충돌: `git fetch origin main && git rebase origin/main` 후
  `git push --force-with-lease`. 재리뷰 요청.
- 리뷰 수정: amend 대신 새 커밋으로 수정하고 push 후 재리뷰 요청.

## CI

현재 이 저장소에는 CI workflow가 없습니다. 필요해지면(예: JSON/YAML lint,
frontmatter 검증) `.github/workflows/`에 추가하고 이 문서를 갱신합니다.
