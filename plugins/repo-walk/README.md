# repo-walk Codex 플러그인

GitHub 저장소의 PR·이슈·커밋 역사를 한 단계씩 읽으며, 각 변경의 왜·무엇·어떻게를
학습 자료 형태로 해설하는 Codex 전용 플러그인입니다.

이 패키지는 Claude Code 플러그인과 독립적입니다. Codex의 `.codex-plugin` 매니페스트와
스킬 구조를 사용하며, 별도 서버·API 키·실행 파일을 추가하지 않습니다.

## 설치

`gh auth login`으로 GitHub CLI를 인증한 뒤, 다음 명령으로 이 저장소 marketplace를
등록하고 플러그인을 설치합니다.

```bash
codex plugin marketplace add hyeongyu-data/repo-walk --ref main
codex plugin add repo-walk@repo-walk
```

설치 뒤 새 Codex 스레드에서 `repo-walk` 스킬을 선택하거나, 예를 들어
`hyeongyu-data/repo-walk의 역사를 PR 순서대로 설명해줘`라고 요청하세요.

## 보안과 상태

플러그인은 `gh` 읽기 전용 조회만 사용합니다. 원격 PR·이슈·diff·리뷰는 비신뢰
데이터로 처리하며, 대상 저장소를 변경하는 GitHub 명령은 실행하지 않습니다. 순회
상태는 `.repo-walk/`에 최소 메타데이터만 저장하고 토큰·개인정보·퀴즈 답변·코드·리뷰
원문은 기록하지 않습니다.
