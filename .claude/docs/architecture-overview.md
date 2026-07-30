# 아키텍처 개요

> Last Updated: 2026-07-30

플러그인의 전체 그림과 설계 결정을 담은 문서입니다. 파일별 책임은
`agent-project-reference.md`, 커맨드 작성 규칙은 `agent-command-reference.md`를
참고합니다.

## 시스템 맥락

repo-walk는 GitHub 저장소의 역사(커밋·이슈·PR)를 한 단계씩 걸으며 Claude Code
또는 Codex가 *해설*하도록 돕는 플러그인입니다. 두 플랫폼은 각자의 매니페스트와
호출 방식을 쓰는 독립 패키지이며, 목적은 낯선 코드베이스 적응과 프로젝트 발전 과정
학습입니다.

## 핵심 설계 결정

1. **얇은 래퍼.** `gh`가 데이터를 가져오고, 해설은 이미 켜져 있는 Claude 또는
   Codex가 합니다. 별도 서버·API 키·DB·빌드나 외부 Python 패키지가 없습니다.
   Claude는 `commands/repo-walk.md`, Codex는
   `plugins/repo-walk/skills/repo-walk/SKILL.md`의 해설 지시문으로 독립
   배포합니다. 결정론적 분류·검증·HTML escape는 LLM 프롬프트보다 코드로
   강제해야 하므로 Python 표준 라이브러리 CLI만 얇은 래퍼의 예외로 둡니다.
2. **나열이 아니라 해설이 가치.** `git log`·`gh`는 이미 나열을 완벽히 합니다.
   이 플러그인의 유일한 존재 이유는 LLM이 히스토리를 읽고 "왜/무엇을/어떻게"를
   설명하는 것입니다.
3. **PR을 이해의 단위로.** 기본은 PR 중심(이슈=왜, PR=무엇을, 커밋=어떻게).
   순수 시간순은 `--timeline` 옵트인 — 대형 저장소에서 뒤섞임이 오히려 이해를
   흐릴 수 있기 때문입니다.
4. **스코프 강제.** 최대 1,000개의 머지 PR을 시간순으로 정렬한 뒤 기본 첫 15개
   단위를 해설합니다. `--limit`/`--path`/`--since`로 슬라이스하며, 더 큰
   저장소에서는 `--path` 또는 `--since`를 우선 권합니다.
5. **심화 답안과 회고 퀴즈의 분리.** 심화 질문은 왜 중요한가와 근거 기반 모범 답안을
   즉시 제공해 탐구의 발판으로 삼습니다. 타임라인·cursor·`pendingQuiz` 메타데이터는
   `.repo-walk/*.json`에 저장하고, 회고 퀴즈를 채점하거나 명시적으로 건너뛴 뒤에만
   cursor를 전진시켜 긴 역사를 여러 세션에 나눠 걷습니다.
6. **로컬 정적 리포트.** `--report`는 머지된 PR 중 파일 역할과 diff 의미 판정을
   모두 통과한 동작·critical 변경만 저장합니다. PR별 구조화 JSON을 진실의 원천으로
   두고 PR별 HTML과 전체 `index.html`을 원자적으로 재생성합니다. JavaScript·외부
   CDN·호스팅 서비스는 사용하지 않습니다.
7. **독립 패키지, 같은 도구 계약.** Claude용
   `scripts/repo_walk_report.py`와 Codex용
   `plugins/repo-walk/scripts/repo_walk_report.py`는 각 설치 패키지 안에 포함됩니다.
   서로를 import하지 않고 같은 표준 라이브러리 구현을 복제하며, `unittest`에서
   바이트 동일성을 검증합니다.

## 데이터 흐름

```
Claude Code: /repo-walk owner/repo [옵션]
Codex: repo-walk 스킬 + owner/repo 요청
    ↓  gh auth status 확인, 인자 파싱
    ↓  gh pr list / gh api commits / gh issue list  (수집)
    ↓  시간순 정렬 + 스코프 적용 → .repo-walk/<owner>-<repo>.json 저장
    ↓  단위 1개 해설 + 심화 질문/중요성/모범 답안 + 회고 퀴즈 (diff는 지연 로딩)
    ↓  pendingQuiz 저장 → 답변 채점/skip 후 커서 전진 → "next"로 이어가기

--report 분기:
    ↓  머지 확인 → 파일 역할 분류 → diff 기반 동작·critical 의미 판정
    ↓  .repo-walk/reports/<owner>-<repo>/.staging/에 구조화 입력 작성
    ↓  패키지 내부 repo_walk_report.py가 JSON 검증·HTML escape·원자적 저장
    ↓  data/pr-N.json + prs/pr-N.html + manifest.json + index.html
```

일반 상태에는 커서용 최소 메타데이터만 남지만, 리포트 JSON·HTML에는 해설과 코드
근거가 포함될 수 있습니다. 따라서 `.repo-walk/` 전체를 Git에서 제외하며 private
저장소 리포트는 로컬 민감 데이터로 취급하고 자동 업로드·배포하지 않습니다.

## 한계

- 대형 저장소는 수집이 느리고 rate limit·토큰 부담 → 스코프 필터 사실상 필수.
- 인과 설명은 Claude 추론이라 틀릴 수 있음(그럴듯한 오답) — 정밀 감사용 아님.
- `gh` 설치·인증 전제. 오프라인 불가.
- HTML은 로컬 정적 파일이며 검색 서버·공유 대시보드·자동 배포 기능이 아님.
