# 에이전트 프로젝트 참조

> Last Updated: 2026-07-15

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
│   └── repo-walk.md         # 커맨드 정의 = 프롬프트 = 전체 로직 (실행 바이너리 없음)
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
└── LICENSE                  # MIT
```

## 파일 책임

| 파일 | 책임 | 변경 시 함께 볼 것 |
|---|---|---|
| `commands/repo-walk.md` | 커맨드의 전체 동작(프롬프트) | README 사용법, `agent-command-reference.md` |
| `.claude-plugin/plugin.json` | 매니페스트 | `marketplace.json`(이름·설명 일치) |
| `.claude-plugin/marketplace.json` | 마켓플레이스 등록 | `plugin.json` |
| `AGENTS.md` | 에이전트 핵심 규칙·탐색표 | `.claude/docs/` 전체 |
| `README.md` | 사용자 문서 | 동작을 바꾼 모든 변경 |
| `.github/` | 이슈·PR 템플릿 | `agent-workflow-reference.md` |
| `.gitignore` | 로컬 순회 상태·민감 로컬 산출물 제외 | `agent-security-guidelines.md` |

## 핵심 원칙

이 저장소는 **얇은 래퍼**입니다: `gh`가 데이터를 가져오고 Claude가 해설하며,
서버·API 키·DB·빌드가 없습니다. 새 파일·의존성을 늘리기 전에 기존 구조로
해결되는지 먼저 확인합니다. 상세 그림은 `architecture-overview.md`.
