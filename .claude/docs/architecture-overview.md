# 아키텍처 개요

> Last Updated: 2026-07-16

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
   Codex가 합니다. 별도 서버·API 키·DB·빌드·실행 바이너리가 없습니다. Claude는
   `commands/repo-walk.md`, Codex는 `plugins/repo-walk/skills/repo-walk/SKILL.md`의
   해설 지시문으로 독립 배포합니다.
2. **나열이 아니라 해설이 가치.** `git log`·`gh`는 이미 나열을 완벽히 합니다.
   이 플러그인의 유일한 존재 이유는 LLM이 히스토리를 읽고 "왜/무엇을/어떻게"를
   설명하는 것입니다.
3. **PR을 이해의 단위로.** 기본은 PR 중심(이슈=왜, PR=무엇을, 커밋=어떻게).
   순수 시간순은 `--timeline` 옵트인 — 대형 저장소에서 뒤섞임이 오히려 이해를
   흐릴 수 있기 때문입니다.
4. **스코프 강제.** 최대 1,000개의 머지 PR을 시간순으로 정렬한 뒤 기본 첫 15개
   단위를 해설합니다. `--limit`/`--path`/`--since`로 슬라이스하며, 더 큰
   저장소에서는 `--path` 또는 `--since`를 우선 권합니다.
5. **퀴즈 대기 상태를 가진 디스크 커서.** 타임라인·cursor·`pendingQuiz` 메타데이터를
   `.repo-walk/*.json`에 저장합니다. 회고 퀴즈를 채점하거나 명시적으로 건너뛴 뒤에만
   cursor를 전진시켜 긴 역사를 여러 세션에 나눠 걷습니다.

## 데이터 흐름

```
Claude Code: /repo-walk owner/repo [옵션]
Codex: repo-walk 스킬 + owner/repo 요청
    ↓  gh auth status 확인, 인자 파싱
    ↓  gh pr list / gh api commits / gh issue list  (수집)
    ↓  시간순 정렬 + 스코프 적용 → .repo-walk/<owner>-<repo>.json 저장
    ↓  단위 1개 해설 + 회고 퀴즈: 왜/무엇을/어떻게 (diff는 지연 로딩)
    ↓  pendingQuiz 저장 → 답변 채점/skip 후 커서 전진 → "next"로 이어가기
```

## 한계

- 대형 저장소는 수집이 느리고 rate limit·토큰 부담 → 스코프 필터 사실상 필수.
- 인과 설명은 Claude 추론이라 틀릴 수 있음(그럴듯한 오답) — 정밀 감사용 아님.
- `gh` 설치·인증 전제. 오프라인 불가.
