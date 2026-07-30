# 에이전트 프로젝트 참조

> Last Updated: 2026-07-30

프로젝트 구조와 파일 책임을 빠르게 찾기 위한 문서입니다. "X는 어디에
있는가?" 질문에 답합니다.

## 이 문서를 볼 때

- 저장소 레이아웃과 파일별 책임을 파악해야 할 때
- 새 기능·문서를 추가할 위치를 정해야 할 때

## 프로젝트 구조

```
repo-walk/
├── .claude-plugin/
│   ├── plugin.json          # 플러그인 매니페스트 (이름·버전·설명·commands 경로)
│   └── marketplace.json     # /plugin marketplace add 용 매니페스트
├── commands/
│   └── repo-walk.md         # Claude 커맨드 정의와 리포트 오케스트레이션
├── scripts/
│   └── repo_walk_report.py  # Claude 패키지용 분류·검증·HTML 렌더링 CLI
├── plugins/
│   └── repo-walk/
│       ├── .codex-plugin/plugin.json # Codex 플러그인 매니페스트
│       ├── skills/repo-walk/SKILL.md # Codex 전용 해설·리포트 스킬
│       └── scripts/repo_walk_report.py # Codex 패키지용 동일 CLI 사본
├── .agents/plugins/marketplace.json  # Codex marketplace 등록 정보(.agents는 .claude 별칭)
├── .claude/
│   └── docs/                # 에이전트 작업 가이드 (이 문서 포함)
├── .github/
│   ├── ISSUE_TEMPLATE/      # bug / feature / experiment / config
│   └── PULL_REQUEST_TEMPLATE.md
├── .gitignore               # 로컬 순회 상태(.repo-walk/) 제외
├── CLAUDE.md                # 에이전트 진입점 (핵심 규칙 + 문서 탐색표)
├── AGENTS.md → CLAUDE.md    # 심링크
├── .agents → .claude        # 심링크 (진입점 별칭)
├── README.md                # 사용자용 설명·설치·사용법
├── tests/                   # unittest 회귀 테스트와 JSON fixture
└── LICENSE                  # MIT
```

## 파일 책임

| 파일 | 책임 | 변경 시 함께 볼 것 |
|---|---|---|
| `commands/repo-walk.md` | Claude 해설·상태 전이·리포트 도구 호출 | README 사용법, `agent-command-reference.md` |
| `scripts/repo_walk_report.py` | Claude 설치 패키지의 분류·JSON 검증·PR/인덱스 HTML 렌더링 | Codex 도구 사본, `tests/test_repo_walk_report.py` |
| `plugins/repo-walk/` | Codex 전용 플러그인·스킬·독립 도구 사본 | README 사용법, `agent-codex-plugin-reference.md` |
| `plugins/repo-walk/scripts/repo_walk_report.py` | Codex 설치 패키지의 동일 표준 라이브러리 CLI | Claude 도구 원본, 동기화 테스트 |
| `.agents/plugins/marketplace.json` | Codex marketplace 등록 | `plugins/repo-walk/.codex-plugin/plugin.json` |
| `.claude-plugin/plugin.json` | 매니페스트 | `marketplace.json`(이름·설명 일치) |
| `.claude-plugin/marketplace.json` | 마켓플레이스 등록 | `plugin.json` |
| `AGENTS.md` | 에이전트 핵심 규칙·탐색표 | `.claude/docs/` 전체 |
| `README.md` | 사용자 문서 | 동작을 바꾼 모든 변경 |
| `tests/` | 외부 네트워크 없는 분류·렌더링·패키지 계약 검증 | 두 도구 사본과 JSON fixture |
| `.github/` | 이슈·PR 템플릿 | `agent-workflow-reference.md` |
| `.gitignore` | 로컬 순회 상태·민감 로컬 산출물 제외 | `agent-security-guidelines.md` |

## 핵심 원칙

이 저장소는 **얇은 래퍼**입니다: `gh`가 데이터를 가져오고 Claude 또는 Codex가
해설하며, 서버·API 키·DB·빌드가 없습니다. 리포트 도구는 결정론적 분류·검증·
안전한 HTML 렌더링을 프롬프트 밖에서 보장하기 위한 좁은 예외이며 Python 표준
라이브러리만 사용합니다. 두 플랫폼은 독립 설치되므로 도구를 각각 포함하되,
`python3 -m unittest discover -s tests -v`와 바이트 비교로 같은 계약을
유지합니다. 상세 그림은 `architecture-overview.md`.
