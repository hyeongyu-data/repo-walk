# repo-walk

GitHub 저장소의 역사를 **한 단계씩 걸으며 해설해주는** Claude Code·Codex 플러그인.
커밋·이슈·PR을 그냥 나열하는 게 아니라, 각 변경이 *왜* 생겼고, *무엇을* 했으며,
앞의 것 위에 *어떻게* 쌓였는지 설명합니다.

`git log`와 `gh`는 이미 역사를 나열합니다. 이 플러그인은 그걸 Claude로 **설명**
하는 부분이에요 — 저장소의 발전 과정을 안내받으며 한 단계씩 읽게 해줍니다.
낯선 코드베이스에 적응하거나, 잘 만든 프로젝트가 어떻게 자랐는지 학습할 때
좋습니다.

## 동작 방식

얇은 래퍼입니다: `gh`가 데이터를 가져오고, Claude 또는 Codex가 해설합니다. 서버·
API 키·데이터베이스 없이 플랫폼별 플러그인 지시문과 Python 표준 라이브러리 기반
로컬 리포트 도구만 제공합니다.

- **기본은 PR 중심, 한 번에 하나씩** — PR이 자연스러운 이해 단위입니다: 연결된
  이슈는 *왜*를, PR 본문은 *무엇을*, 안의 커밋들은 *어떻게*를 담습니다. 머지된
  PR을 시간순으로 정렬한 뒤 기본 **한 개씩**(`--batch 1`) 깊게 걷습니다.
- **선택적 HTML 리포트** — `--report`를 붙이면 실제 동작 또는 운영상 critical
  변경으로 판정한 머지 PR만 PR별 HTML로 저장하고, 전체 결과를 카드 형태로 요약한
  `index.html`도 함께 갱신합니다. 기본 학습 흐름은 파일을 만들지 않습니다.
- **PR마다 심화 5단 구성** — 얕은 요약이 아니라 학습 자료 수준으로(**실제 코드·리뷰
  원문을 인용**하고 개념은 외부 검색 없이 이해되게):
  1. **해설** — 무엇을·왜·어떻게 + 핵심 개념(대안·트레이드오프 포함)
  2. **리뷰 해설** — 리뷰/코드리뷰 코멘트를 "지적 → 배경 개념 → 반영·타당성"으로
     풀어써, 리뷰만 읽어도 개념이 이해되게
  3. **직접 코드리뷰** — Claude가 diff를 직접 정독해 기존 리뷰가 놓친 개선점·위험을
     파일·라인과 함께(기존 리뷰 주장도 비판적으로 검증, 신뢰도 표기)
  4. **학습 포인트** — 개념·모범 사례·흔한 실수·주의점·심화 질문으로 범주화.
     심화 질문에는 **왜 중요한가**와 `핵심 결론 → 확인된 근거 → 대안과
     트레이드오프` 형식의 **모범 답안**을 함께 제공
  (리뷰 해설/직접 코드리뷰/학습 포인트는 Claude 추론이라 교육용 참고입니다.)
- **능동 학습 루프** — 해설 전 예측 질문 1개로 스스로 생각하게 하고, 해설에서는
  `변경 전 → 이번 PR → 다음 변화`와 `입력 → 처리 → 출력/소비자` 코드 추적 경로를
  실제 근거가 있을 때만 제시합니다. 심화 질문은 모범 답안까지 즉시 확인할 수 있고,
  끝의 회고 퀴즈 1~2개만 답변을 채점한 뒤 다음 PR로 넘어갑니다.
- **읽기 쉬운 결과 형식** — 모든 PR은 한 줄 요약과 "한눈에 보기" 표로 시작합니다.
  이후에는 번호가 매겨진 섹션, 파일·라인 표기, 짧은 코드 인용, 심각도 표기로
  근거와 결론을 분리해 빠르게 훑을 수 있습니다.
- **`--timeline` 모드** — 순수 시간순: 커밋·이슈·PR을 하나의 시간축에 뒤섞습니다
  (대형 저장소에서는 어수선하지만, 그게 이 모드의 취지입니다).
- **의도적으로 스코프 제한** — 최대 1,000개의 머지 PR을 시간순으로 정렬한 뒤
  기본 첫 15개 단위를 해설하며, `--limit`·`--path`·`--since`로 좁힙니다. 더 큰
  저장소에서는 `--path` 또는 `--since`를 권장합니다.
- **지연 조회로 토큰 절약** — 초기 목록에는 PR 번호·제목·시각·URL만 저장합니다.
  본문·diff·리뷰는 실제로 해설하는 PR 하나를 선택한 시점에만 가져옵니다.
- **이어보기 가능** — 진행 상태를 로컬 커서 파일에 저장하므로, 긴 역사를 여러
  번에 나눠 `... next`로 이어 걸을 수 있습니다.

## 요구 사항

- [Claude Code](https://claude.com/claude-code) 또는 [Codex CLI](https://github.com/openai/codex)
- [`gh` CLI](https://cli.github.com/), 인증 완료 (`gh auth login`)
- Python 3 (외부 패키지 없이 표준 라이브러리만 사용)

## 보안

- 이 플러그인은 GitHub 데이터를 **읽기만** 하며, 대상 저장소의 이슈·PR·브랜치·설정을
  변경하지 않습니다.
- PR 본문, diff, 리뷰처럼 원격에서 가져온 텍스트는 비신뢰 데이터로 처리합니다. 안에
  포함된 명령이나 지시를 실행하지 않습니다.
- 일반 순회 상태에는 최소 메타데이터만 저장합니다. `--report` 산출물에는 해설과
  코드 근거가 포함될 수 있으며 `.repo-walk/reports/<owner>-<repo>/` 아래에만
  로컬 보관됩니다.
- private 저장소의 리포트는 민감한 로컬 파일로 취급하세요. 플러그인은 이를
  업로드·배포·게시하지 않으며, `.repo-walk/`는 Git 추적에서 제외됩니다. 시크릿·
  개인정보로 보이는 값은 인용하거나 저장하지 않습니다.

## 설치

### Claude Code

```
/plugin marketplace add hyeongyu-data/repo-walk
/plugin install repo-walk
```

또는 클론한 뒤 Claude Code가 그 디렉터리를 가리키게 합니다.

### Codex CLI

Codex 전용 플러그인을 설치합니다. Claude Code용 `commands/`·`.claude-plugin`과는
독립된 `.codex-plugin`·스킬 패키지이므로 커스텀 프롬프트 파일을 복사할 필요가
없습니다.

```
codex plugin marketplace add hyeongyu-data/repo-walk --ref main
codex plugin add repo-walk@repo-walk
```

설치 뒤에는 **새 Codex 스레드**에서 플랫폼에 맞는 명시 호출 문법을 사용합니다.
`/repo-walk`는 Claude Code 전용 슬래시 커맨드이므로 Codex에서 사용하지 않습니다.

## 사용법

### Claude Code

```
/repo-walk owner/repo                     # PR 중심 순회, 시간순 첫 15개 PR
/repo-walk owner/repo --report            # 중요 머지 PR의 HTML 리포트 생성
/repo-walk owner/repo --timeline          # 순수 시간순 (커밋+이슈+PR)
/repo-walk owner/repo --path src/auth     # 특정 경로를 건드리는 역사만
/repo-walk owner/repo --since 2024-01-01  # 최근 역사만
/repo-walk owner/repo --limit 40 --batch 1
/repo-walk owner/repo next                # 퀴즈를 완료한 지점부터 이어가기
/repo-walk owner/repo skip                # 대기 중인 퀴즈를 건너뛰고 다음 PR로
/repo-walk owner/repo reset               # 처음부터 다시
```

순회 중에는 *"#123 diff 보여줘"*, *"이건 왜 필요했어?"* 처럼 그냥 물어봐도 됩니다
— Claude가 맥락을 이미 로드해 두었습니다.

### Codex

Codex CLI에서는 플러그인 이름공간을 포함한 `$repo-walk:repo-walk`로 스킬을 명시
호출합니다. Codex 데스크톱 앱에서는 `@repo-walk`를 입력해 플러그인을 선택한 뒤
같은 인자를 보냅니다. 자연어 요청으로도 스킬이 선택될 수 있지만, 아래처럼 명시
호출하면 의도한 플러그인을 확실히 사용합니다.

```
# Codex CLI
$repo-walk:repo-walk owner/repo
$repo-walk:repo-walk owner/repo --report
$repo-walk:repo-walk owner/repo --timeline
$repo-walk:repo-walk owner/repo next
$repo-walk:repo-walk owner/repo skip

# Codex 데스크톱 앱
@repo-walk owner/repo
```

## HTML 리포트

`--report`는 PR 중심 모드에서만 사용할 수 있으며 `--timeline`과 함께 쓸 수
없습니다. 다음 순서로 후보를 좁힌 뒤, 통과한 PR에만 `--limit`을 적용합니다.
첫 호출은 적격 PR의 최소 메타데이터를 상태에 저장한 뒤 `units[cursor]` 하나만
해설·렌더링하고 회고 퀴즈를 냅니다. 퀴즈 답변이나 `skip`은 cursor를 한 칸만
전진시키고 끝나며, 이후 `next`가 다음 PR 하나를 처리합니다.

- 닫혔지만 머지되지 않은 PR은 제외합니다.
- 문서 전용, 테스트 전용, 생성물·vendor 전용 변경은 제외합니다.
- 파일 역할을 통과해도 diff를 읽었을 때 동작·운영 영향이 없는 외형·문구 변경은
  제외합니다.
- 일반 소스와 스크립트는 실제 동작 변경이 확인될 때 포함합니다.
- `commands/repo-walk.md`와 `SKILL.md` 같은 기능성 Markdown은 실행 지시문이므로
  확장자가 Markdown이어도 실제 소비 경로와 동작 변경을 기준으로 포함합니다.
- workflow·보안·스키마·배포·dependency·플러그인 매니페스트 같은 critical
  후보도 이름만으로 포함하지 않고 diff에서 운영 영향을 확인합니다.

산출물은 현재 작업 디렉터리의 다음 경로에 누적됩니다.

```text
.repo-walk/reports/<owner>-<repo>/
├── data/pr-N.json
├── prs/pr-N.html
├── manifest.json
└── index.html
```

`index.html`은 저장소·생성 시각·총 리포트 수·종류/운영 영향 집계와 각 PR의 포함
이유·영향 파일을 한 번에 요약합니다. 같은 출력 root에 다른 저장소 data가 섞이면
기존 산출물을 바꾸기 전에 거부합니다. 예를 들어
`owner/repo`의 결과는 macOS에서 다음처럼 열 수 있습니다.

```bash
open .repo-walk/reports/owner-repo/index.html
```

다른 운영체제에서는 파일 탐색기나 브라우저에서 같은 `index.html`을 직접 여세요.
정적 HTML에는 외부 CDN이나 JavaScript가 없으며 자동으로 외부에 배포되지 않습니다.

## 일부러 하지 않는 것

의도적으로 게으르게 유지했습니다(정말 필요해질 때만 나중에 추가):

- "커밋 #1부터 전부 걷기" 모드 없음 — 항상 좁힌 슬라이스만 다룹니다.
- 자체 인증 / API 키 관리 없음 — 당신의 `gh` 로그인을 재사용합니다.
- 호스팅 웹 UI, 그래프, 다중 저장소 대시보드, 리포트 자동 배포 없음.

## 라이선스

MIT
