# repo-walk Codex 플러그인

GitHub 저장소의 PR·이슈·커밋 역사를 한 단계씩 읽으며, 각 변경의 왜·무엇·어떻게를
학습 자료 형태로 해설하는 Codex 전용 플러그인입니다.

각 단위의 학습 포인트에는 심화 질문을 최대 두 개까지 제시합니다. 질문마다
**왜 중요한가**와 `핵심 결론 → 확인된 근거 → 대안과 트레이드오프` 순서의 **모범
답안**을 함께 보여주며, 이는 답변이나 채점을 요구하지 않습니다. 회고 퀴즈만 별도로
답변 또는 `skip` 뒤에 다음 단위로 진행합니다.

이 패키지는 Claude Code 플러그인과 독립적입니다. Codex의 `.codex-plugin` 매니페스트와
스킬 구조를 사용하며, 별도 서버·API 키·외부 Python 패키지 없이 패키지 내부의
표준 라이브러리 리포트 도구만 사용합니다.

## 설치

`gh auth login`으로 GitHub CLI를 인증한 뒤, 다음 명령으로 이 저장소 marketplace를
등록하고 플러그인을 설치합니다.

```bash
codex plugin marketplace add hyeongyu-data/repo-walk --ref main
codex plugin add repo-walk@repo-walk
```

설치 뒤 새 Codex 스레드에서 플랫폼에 맞는 명시 호출 문법을 사용하세요.

```text
# Codex CLI
$repo-walk:repo-walk owner/repo
$repo-walk:repo-walk owner/repo --report
$repo-walk:repo-walk owner/repo --timeline
$repo-walk:repo-walk owner/repo next

# Codex 데스크톱 앱
@repo-walk owner/repo
```

`/repo-walk`는 Claude Code 전용 슬래시 커맨드입니다. Codex 플러그인에는 사용하지
않습니다.

## HTML 리포트

`$repo-walk:repo-walk owner/repo --report`를 실행하면 머지된 PR 가운데 실제
동작 변경 또는 운영상 critical 변경만 골라 다음 경로에 저장합니다.

```text
.repo-walk/reports/<owner>-<repo>/
├── data/pr-N.json
├── prs/pr-N.html
├── manifest.json
└── index.html
```

`index.html`은 생성된 PR별 HTML을 카드로 요약합니다. 예를 들어 macOS에서는 다음
명령으로 열 수 있고, 다른 운영체제에서는 파일 탐색기나 브라우저로 같은 파일을
직접 열면 됩니다.

```bash
open .repo-walk/reports/owner-repo/index.html
```

닫혔지만 머지되지 않은 PR과 문서·테스트·생성물·vendor 전용 PR은 제외합니다.
파일 역할을 통과한 후보도 diff에 동작·운영 영향이 없고 외형이나 문구만 바뀌었다면
제외합니다. 반대로 `commands/repo-walk.md`와 `SKILL.md` 같은 기능성 Markdown은
실제 소비 경로와 동작 변경이 확인되면 포함하며, workflow·보안·스키마·배포·
dependency·플러그인 매니페스트 같은 critical 후보도 diff 근거가 있을 때만
포함합니다.

첫 호출은 적격 PR의 최소 메타데이터를 `units`에 저장한 뒤 현재 cursor의 PR
하나만 해설·렌더링하고 퀴즈를 냅니다. 퀴즈 답변이나 `skip`은 cursor를 한 칸만
전진시키고 끝나며, 나중의 `next`가 다음 PR 하나를 처리합니다. `index.html`에는
저장소·생성 시각·총 개수·종류/운영 영향 집계와 카드별 이유·파일이 표시됩니다.
다른 저장소 data가 같은 출력 root에 섞이면 기존 산출물을 바꾸기 전에 거부합니다.

리포트 모드는 PR 중심 전용이므로 `--timeline`과 함께 사용할 수 없습니다. 리포트
상태에서 `next` 또는 `skip`을 호출하면 `--report`를 다시 쓰지 않아도 같은 모드를
이어갑니다.

## 보안과 상태

플러그인은 `gh` 읽기 전용 조회만 사용합니다. 원격 PR·이슈·diff·리뷰는 비신뢰
데이터로 처리하며, 대상 저장소를 변경하는 GitHub 명령은 실행하지 않습니다. 순회
상태는 `.repo-walk/`에 최소 메타데이터만 저장하고 토큰·개인정보·퀴즈 답변·코드·리뷰
원문은 기록하지 않습니다.

`--report` 산출물에는 해설과 코드 근거가 포함될 수 있으며
`.repo-walk/reports/<owner>-<repo>/`에 로컬 보관됩니다. 특히 private 저장소의
리포트는 민감한 파일로 취급하세요. 플러그인은 리포트를 업로드·배포·게시하지 않으며
외부 CDN이나 JavaScript도 사용하지 않습니다. `.repo-walk/`는 Git 추적에서
제외되지만, 공유 전에는 시크릿·개인정보가 없는지 사용자가 다시 확인해야 합니다.
