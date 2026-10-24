#!/usr/bin/env bash
# AI 업무자동화 코치 — Mac 설치 스크립트
# 사용법 (터미널에 붙여넣기):
#   curl -fsSL https://raw.githubusercontent.com/hi8735/ai-automation-kit/main/install/install.sh | bash
#
# 하는 일: ~/ai-kit 폴더에 (1) uv(파이썬 관리 도구) (2) 코치 앱 (3) 키트 를 설치하고
#          바탕화면에 "AI 업무자동화 코치" 실행 파일을 만든 뒤 실행한다. 관리자 권한 불필요.
# 다시 실행하면 최신 버전으로 업데이트된다. 내 기록(results, inputs, report, automations, outputs)은 건드리지 않는다.
set -euo pipefail

APP_ZIP="${AI_KIT_APP_ZIP:-https://github.com/hi8735/ai-automation-kit/releases/latest/download/ai-automation-kit-app.zip}"
ROOT="$HOME/ai-kit"
UV="$ROOT/bin/uv"
export UV_PYTHON_INSTALL_DIR="$ROOT/python"
export UV_CACHE_DIR="$ROOT/cache"
export UV_PYTHON_PREFERENCE=only-managed
# 파이썬 부품 환경은 app 폴더 밖에 둔다 (업데이트 때 다시 받지 않게)
export UV_PROJECT_ENVIRONMENT="$ROOT/venv"
# 여러 명이 같은 와이파이로 받을 때 느려도 끊지 않게
export UV_HTTP_TIMEOUT=300

step() { printf '\n\033[36m[%s/5] %s\033[0m\n' "$1" "$2"; }
fail() {
  printf '\n\033[31m설치를 마치지 못했어요: %s\033[0m\n' "$1"
  printf '\033[33m이 창의 내용을 캡처해서 모임 채팅방에 올려주세요. 바로 도와드릴게요.\033[0m\n'
  exit 1
}
trap 'fail "예상하지 못한 오류 (줄 $LINENO)"' ERR

mkdir -p "$ROOT"
printf '\n\033[32mAI 업무자동화 코치를 설치할게요. 설치 위치: %s\033[0m\n' "$ROOT"
echo "처음엔 3~5분 걸릴 수 있어요. 창을 닫지 말고 기다려주세요."

# 코치가 켜져 있으면 먼저 끈다 (업데이트 중 파일이 바뀌지 않게)
if pkill -f "$ROOT/app/server.py" 2>/dev/null; then echo "  켜져 있던 코치를 껐어요."; sleep 1; fi

step 1 "준비 도구(uv) 설치"
if [ ! -x "$UV" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/bin" UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
    || fail "uv 설치 실패 — 인터넷 연결을 확인해 주세요."
  [ -x "$UV" ] || fail "uv 를 찾을 수 없어요 ($UV)"
else
  echo "  이미 있어요."
fi

step 2 "코치 앱 내려받기"
TMP="$ROOT/_download"
rm -rf "$TMP" && mkdir -p "$TMP"
curl -fsSL -o "$TMP/app.zip" "$APP_ZIP" || fail "내려받기 실패 — 인터넷 연결을 확인해 주세요."
unzip -q -o "$TMP/app.zip" -d "$TMP"

step 3 "앱과 키트 설치"
rm -rf "$ROOT/app"
cp -R "$TMP/ai-automation-kit-app/app" "$ROOT/app"
WS="$ROOT/workspace"
mkdir -p "$WS"
for item in "$TMP/ai-automation-kit-app/kit/"* "$TMP/ai-automation-kit-app/kit/".[!.]*; do
  [ -e "$item" ] || continue
  name="$(basename "$item")"
  case "$name" in
    results|inputs|report|automations|outputs)
      # 내 기록 폴더는 없는 파일(README 등)만 채운다
      mkdir -p "$WS/$name"
      cp -R -n "$item/." "$WS/$name/" 2>/dev/null || true ;;
    *)
      rm -rf "$WS/$name"
      cp -R "$item" "$WS/$name" ;;
  esac
done
rm -rf "$TMP"

step 4 "파이썬과 필요한 부품 설치 (처음엔 조금 걸려요)"
"$UV" sync --project "$ROOT/app" --frozen --quiet \
  || { echo "  한 번 더 시도할게요..."; "$UV" sync --project "$ROOT/app" --frozen; } \
  || fail "부품 설치 실패 (uv sync). 인터넷이 느리거나 회사 네트워크가 막았을 수 있어요."

step 5 "바탕화면 실행 파일 만들기"
mkdir -p "$HOME/Desktop"
LAUNCHER="$HOME/Desktop/AI 업무자동화 코치.command"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# AI 업무자동화 코치 실행 — 이 창을 닫으면 코치도 꺼져요.
export UV_PYTHON_INSTALL_DIR="$ROOT/python"
export UV_CACHE_DIR="$ROOT/cache"
export UV_PYTHON_PREFERENCE=only-managed
export UV_PROJECT_ENVIRONMENT="$ROOT/venv"
export PYTHONUTF8=1
exec "$UV" run --project "$ROOT/app" --frozen --quiet python "$ROOT/app/server.py" --workspace "$WS" --open
EOF
chmod +x "$LAUNCHER"
echo "  바탕화면에 'AI 업무자동화 코치' 를 만들었어요."

trap - ERR
printf '\n\033[32m설치 완료! 코치를 켤게요. 브라우저가 열리면 Claude 계정으로 로그인하세요.\033[0m\n'
echo "다음부터는 바탕화면의 'AI 업무자동화 코치' 를 더블클릭하면 돼요."
[ -n "${AI_KIT_NO_LAUNCH:-}" ] || open "$LAUNCHER"
