# 중요 변경 HTML 리포트 설계

## 배경

repo-walk의 현재 산출물은 대화창의 Markdown 해설과 최소 순회 상태 JSON뿐이다.
완료한 해설을 다시 읽거나 여러 PR의 핵심을 한 화면에서 비교할 수 없고, 기본
타임라인에는 문서 전용·외형 변경처럼 학습 가치가 낮은 단위도 섞일 수 있다.

이 변경은 기존의 한 단계씩 걷는 학습 흐름을 유지하면서, 사용자가 명시적으로
`--report`를 선택하면 실제 동작 변화나 운영상 중요한 변경만 선별하여 로컬 HTML
리포트로 누적한다.

## 목표

- 머지된 PR만 리포트 후보로 사용한다.
- 순수 문서·테스트·생성물·외형 변경은 제외한다.
- 기능성 Markdown과 보안·배포·DB·공개 계약·의존성 변경은 포함할 수 있다.
- 포함된 PR마다 독립 HTML을 만들고, 전체 요약 `index.html`을 매번 갱신한다.
- Claude Code와 Codex가 같은 판정·산출물 계약을 사용한다.
- 원격 텍스트를 HTML에 안전하게 표시하고 private 저장소 리포트를 로컬에만 둔다.

## 비목표

- GitHub Pages 자동 배포
- GitHub Action 안에서 LLM 해설 생성
- 여러 저장소를 합친 대시보드
- 외부 JavaScript, CSS CDN, 데이터베이스 또는 별도 API 키
- 기존 대화형 퀴즈와 `next`/`skip` 흐름의 제거

## 사용자 인터페이스

새 옵션은 `--report` 하나다.

```text
/repo-walk owner/repo --report
$repo-walk:repo-walk owner/repo --report
```

기존 호출은 지금과 같은 전체 머지 PR 학습 흐름을 유지한다. `--report` 호출만
고신호 필터와 HTML 저장을 활성화한다. 리포트 모드도 한 번에 한 PR을 해설하며,
각 실행 후 전체 인덱스가 누적 갱신된다.

private 저장소에서는 첫 리포트 작성 전에 코드·본문·리뷰 일부가
`.repo-walk/reports/`에 남는다고 알린다. 이 경로는 계속 Git에서 제외한다.

## 아키텍처

### 1. 플랫폼 어댑터

`commands/repo-walk.md`와
`plugins/repo-walk/skills/repo-walk/SKILL.md`가 다음을 담당한다.

- `gh`를 통한 읽기 전용 수집
- 후보 PR의 diff를 근거로 한 의미 판정
- 기존 5단 해설과 퀴즈 생성
- 구조화된 리포트 JSON 작성
- 플랫폼 패키지에 포함된 로컬 도구 호출

두 플랫폼은 같은 JSON 계약과 판정 규칙을 사용하지만 서로의 패키지 파일에는
의존하지 않는다.

### 2. 플랫폼별 로컬 도구

두 플러그인은 독립 설치 패키지이므로 같은 구현을 각각 다음 경로에 포함한다.

- Claude Code: `scripts/repo_walk_report.py`
- Codex: `plugins/repo-walk/scripts/repo_walk_report.py`

두 파일은 Python 표준 라이브러리만 사용하며, 동기화 검증 테스트로 내용이 같은지
확인한다.

- `classify`: PR 메타데이터의 파일 경로를 역할별로 분류하고 결정론적 판정 결과를
  JSON으로 출력한다.
- `render`: 검증된 리포트 JSON을 PR별 HTML로 렌더링하고 `manifest.json`과
  `index.html`을 원자적으로 갱신한다.
- `rebuild-index`: 저장된 PR JSON을 기준으로 인덱스를 다시 만든다.

도구는 LLM을 호출하거나 GitHub에 접근하지 않는다. 원격 조회는 기존의 명시적인
읽기 전용 `gh` 호출에 남겨 권한 경계를 유지한다.

### 3. 산출물

```text
.repo-walk/reports/<owner>-<repo>/
├── index.html
├── manifest.json
├── data/
│   ├── pr-23.json
│   └── pr-25.json
└── prs/
    ├── pr-23.html
    └── pr-25.html
```

`manifest.json`에는 원문 diff나 리뷰를 중복 저장하지 않는다. PR 번호·제목·URL·
머지 시각·한 줄 요약·분류·영향도·포함 근거·파일 경로만 둔다. `index.html`은 기존
HTML을 파싱하지 않고 manifest 데이터에서 재생성한다.

## 필터 설계

### 1차: 결정론적 hard gate

처리 순서는 다음과 같다.

1. `mergedAt`이 있는 머지 PR만 수집
2. `--since` 적용
3. 변경 파일 전체 조회
4. 파일 역할 분류
5. `--path` 적용
6. 의미 판정
7. 머지 시각 오름차순 정렬
8. `--limit` 적용

`--limit`은 적격 항목 수를 뜻한다. 앞쪽 후보가 제외되더라도 뒤의 적격 PR을 계속
찾는다.

파일 역할 우선순위는 `runtime > critical > test > generated/vendor > docs >
other`다.

- `docs`: `docs/**`, 일반 README·CHANGELOG·CONTRIBUTING, 일반 Markdown·문서 이미지
- `test`: 테스트 전용 디렉터리와 일반 테스트 파일
- `generated/vendor`: 빌드 산출물과 vendored 파일. dependency lockfile은 여기에
  넣지 않고 critical 후보로 분류
- `runtime`: 일반 소스·스크립트와 저장소별 기능 경로
- `critical`: 인증·권한·암호화, DB migration/schema, 공개 API/schema/proto,
  배포·IaC·CI, dependency manifest/lockfile, 패키징·릴리스 매니페스트

저장소별 override로 `commands/repo-walk.md`,
`plugins/repo-walk/skills/**/SKILL.md`, 과거 `codex/prompts/**/*.md`를
Markdown이어도 runtime으로 분류한다.

모든 파일이 docs, test 또는 generated/vendor 중 한 역할이면 각각 `docs_only`,
`test_only`, `generated_only`로 제외한다. 파일 목록이 불완전하거나 알 수 없는
형식뿐이면 자동 제외하지 않고 `review_required`로 둔다.

docs·test·generated/vendor 역할만 섞인 경우도 실행 동작 파일이 없으므로
`non_runtime_only`로 제외한다.

### 2차: diff 근거 기반 의미 판정

플랫폼 LLM은 1차 결과가 runtime 또는 critical 후보일 때 diff를 확인해 다음 JSON
필드를 만든다.

```json
{
  "decision": "include",
  "kind": "behavior",
  "behaviorChanged": true,
  "operationalImpact": "material",
  "evidence": [
    {
      "path": "commands/repo-walk.md",
      "claim": "리포트 모드의 상태 전이가 추가됨"
    }
  ],
  "confidence": "high"
}
```

최종 포함 조건은 `behaviorChanged == true` 또는 `operationalImpact`가 `material`,
`critical`인 경우다. 제목·본문·라벨만으로 포함하지 않으며 diff 파일 근거가 최소
하나 필요하다. 주석·포맷·단순 이름 변경은 `cosmetic_only`로 제외한다.

판정이 불명확하면 조용히 제외하지 않고 사용자에게 `검토 필요`로 알린다.

## 리포트 JSON 계약

PR별 JSON은 다음 상위 필드를 갖는다.

- `schemaVersion`
- `repository`
- `generatedAt`
- `pr`: 번호, 제목, URL, 머지 시각
- `classification`: 종류, 영향도, 신뢰도, 포함 근거, 변경 파일
- `summary`: 인덱스와 PR 제목 아래에 표시할 한 줄 요약
- `overview`: 문제, 핵심 변경, 영향 범위, 다음 연결
- `sections`: 변경 해설·리뷰 해설·직접 코드리뷰·학습 포인트 섹션 배열

각 section은 `title`과 `blocks`를 갖는다. block은 다음 제한된 타입만 허용한다.

- `paragraph`: 일반 설명
- `list`: 문자열 항목 목록
- `code`: 파일 경로·시작 라인·언어·코드
- `quote`: 리뷰 원문과 작성자
- `finding`: 심각도·신뢰도·파일·라인·발견·개선안
- `question`: 질문·왜 중요한가·모범 답안

필수 메타데이터가 없거나 타입이 맞지 않으면 렌더링하지 않는다. 알 수 없는 추가
필드는 무시하여 이후 스키마 확장을 허용한다.

## HTML 설계

PR별 HTML은 다음 순서로 표시한다.

1. PR 제목, 날짜, GitHub 링크
2. 한 줄 요약과 중요도 배지
3. 한눈에 보기 카드
4. 변경 해설
5. 리뷰 해설
6. 직접 코드리뷰
7. 학습 포인트

인덱스는 저장소명, 생성 시각, 포함 PR 수, 종류·영향도별 집계와 PR 카드 목록을
보여준다. 카드는 날짜·제목·요약·포함 이유·영향 파일을 표시하고 개별 HTML로
연결한다.

HTML은 단일 파일로 열 수 있도록 CSS를 내장한다. JavaScript와 외부 리소스는
사용하지 않는다. 모든 원격 텍스트와 파일명은 `html.escape`를 거치며, URL은
`https://github.com/` 형식만 링크로 허용한다.

## 상태와 재실행

리포트 모드는 상태 스키마 3을 사용한다. 기존 스키마 2에는 `reportMode:false`와
최소 분류 메타데이터를 추가해 마이그레이션한다.

해설 HTML은 회고 퀴즈를 내기 직전에 생성한다. 퀴즈 답변 전 재실행해도 같은 PR
번호의 JSON과 HTML을 원자적으로 교체하므로 중복 카드가 생기지 않는다. 퀴즈 채점·
`skip` 뒤에만 기존처럼 cursor가 전진한다.

각 리포트 JSON에 분류기 버전과 입력 파일 목록 digest를 저장한다. 같은 버전과
digest면 결정론적 판정을 재사용할 수 있다.

## 오류 처리

- `gh` 인증 실패: 기존처럼 중단하고 `gh auth login` 안내
- closed-unmerged 또는 open PR: `unmerged`로 제외
- 파일 목록 누락·3,000개 초과: `review_required(incomplete_metadata)`
- 잘못된 리포트 JSON: 파일 경로와 누락 필드를 출력하고 기존 HTML은 보존
- 출력 디렉터리 생성 실패: 리포트를 쓰지 않고 대화 해설은 계속 제공
- 일부 PR HTML 실패: 다른 기존 리포트와 인덱스를 삭제하지 않음
- manifest 손상: `data/*.json`에서 재구축하고 복구 사실을 알림
- private 저장소: 로컬 저장 경고 후 외부 배포·업로드 금지

모든 쓰기는 임시 파일을 같은 디렉터리에 만든 뒤 `os.replace`로 교체한다.

## 테스트

`unittest` 기반으로 외부 네트워크 없이 검증한다.

필터 fixture:

- closed-unmerged 소스 PR 제외
- README/docs-only PR 제외
- 소스와 README가 섞인 동작 변경 포함 후보
- `commands/repo-walk.md` 동작 변경 포함 후보
- workflow·보안·매니페스트 변경 critical 후보
- 테스트-only, generated-only, cosmetic-only 제외
- 불완전 파일 목록은 review_required
- 필터 뒤 limit과 머지 시각 정렬
- 회귀 예시: #21 제외, #23 runtime 후보, #25 critical 후보

렌더링 fixture:

- HTML 특수문자와 script 태그 escape
- 허용되지 않은 URL 비링크 처리
- PR별 HTML과 index 생성
- 재실행 시 같은 PR 카드 중복 없음
- manifest 손상 시 data 파일 기반 복구
- 잘못된 JSON에서 기존 산출물 보존

플러그인 검증:

- Claude frontmatter와 최소 `allowed-tools`
- Claude·Codex 판정/JSON 계약 문구 일치
- 매니페스트 JSON 유효성
- 격리된 Codex 설치
- `git diff --check`

## 배포

이번 범위에서는 로컬 리포트 생성까지만 제공한다. GitHub Action은 테스트 자동화나
공개 저장소의 정적 파일 배포가 실제로 필요해질 때 같은 도구를 호출하는 얇은
래퍼로 후속 추가한다. private 리포트의 기본 배포 수단으로 Pages를 사용하지 않는다.
