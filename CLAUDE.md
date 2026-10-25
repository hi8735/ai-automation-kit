# ai-automation-kit — 개발용 안내

비개발자용 Claude Code 업무자동화 키트. 이 파일은 **키트를 만드는 쪽(개발자)** 을 위한 것이다.
참가자가 읽는 지시문은 `kit/CLAUDE.md` 이며, 둘을 혼동하지 않는다.

## 구조

```
kit/      ← 참가자 배포물 원본. Releases 의 ai-automation-kit.zip = 이 폴더 압축
  CLAUDE.md, .claude/skills/{start,build,run,report}, .claude/settings.json, guide/, inputs/ …
app/      ← 코치 앱 (터미널 없이 쓰는 웹 화면). FastAPI + Claude Agent SDK, 포트 8790
docs/     ← 사용설명서 (GitHub Pages: https://hi8735.github.io/ai-automation-kit/)
install/  ← install.sh / install.ps1 — 키트·앱 설치 + 바로가기 생성
```

## 로컬 실행

```bash
cd app && uv sync
cp -R ../kit /tmp/ws   # 원본 kit/ 를 직접 workspace 로 쓰지 않는다 (인터뷰 기록이 섞임)
uv run server.py --workspace /tmp/ws --port 8799 --open
```

- 서버는 Host 헤더를 `127.0.0.1:PORT` / `localhost:PORT` 만 허용한다.
- 브라우저 탭을 모두 닫으면 3분 뒤 스스로 종료한다 (idle watchdog).

## 릴리스

- `kit/VERSION` 과 git tag(`vX.Y`) 를 맞춘다.
- `gh release` 에셋 이름은 항상 `ai-automation-kit.zip` (README 의 latest/download 링크가 이 이름에 의존).
- 레포는 **public** 이다. 회사 정보·개인 데이터를 커밋하지 않는다.

## 보안 원칙 (app/server.py 자동 허락 로직)

자동 허락 명령은 보수적으로 판정한다 — 허용 문자 목록 방식, 따옴표·`^`·네트워크 경로(`//`, `\\`) 포함 시 자동 허락 금지, 키트 폴더 밖 접근 차단.
이 부분을 고칠 때는 우회 케이스(유니코드 따옴표/대시, shlex 분해 인자)를 같이 점검한다.

## 현재 상태 (2026-10-25)

- 최신 릴리스 v1.5 (2026-10-24). 그 이후 **미릴리스 커밋 6개**: 보안 강화 3건, 진행자 소개 페이지(docs/about.html), 붙여넣기 첨부, 키트 폴더 밖 보호 + 메신저식 다중 첨부.
- 무료 챗봇용 인터뷰 프롬프트 추가 (`docs/chat.html`, 프롬프트 본문은 이 페이지의 `.promptbox` 안에만 있다 — `kit/` 의 start·report 스킬을 바꾸면 여기도 같이 맞춘다). 리포트 `kit_version: chat-v1`.
- 다음 후보: 위 변경분을 v1.6 으로 릴리스할지 결정.
