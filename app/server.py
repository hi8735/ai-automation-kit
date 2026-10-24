"""AI 업무자동화 키트 — 웹 화면 (내 PC 에서 실행).

브라우저 채팅 화면 ↔ (WebSocket) ↔ 이 서버 ↔ Claude Agent SDK ↔ 키트 폴더.
키트 폴더의 CLAUDE.md · .claude/skills · .claude/settings.json 을 그대로 읽어
터미널 Claude Code 와 같은 흐름(/start, /build, /run, /report)을 웹에서 돌린다.

실행: uv run server.py --workspace <키트 폴더> [--open]
설치 스크립트(docs/install.ps1, docs/install.sh)가 바로가기로 이 명령을 만들어 준다.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

import claude_agent_sdk

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

BASE = Path(__file__).parent
app = FastAPI()
WORKSPACE: Path = BASE / "workspace"
PORT = 8790


def allowed_hosts() -> set[str]:
    return {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


def allowed_origins() -> set[str]:
    return {f"http://{h}" for h in allowed_hosts()}


@app.middleware("http")
async def local_only(request, call_next):
    """다른 사이트·DNS 리바인딩에서 이 로컬 서버를 조작하지 못하게 Host·Origin 을 확인한다."""
    from fastapi.responses import PlainTextResponse
    if request.headers.get("host") not in allowed_hosts():
        return PlainTextResponse("forbidden host", status_code=403)
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed_origins():
        return PlainTextResponse("forbidden origin", status_code=403)
    return await call_next(request)

# ── 로그인 ────────────────────────────────────────────
# Agent SDK 에 함께 들어 있는 Claude Code 실행 파일로 로그인 상태를 확인하고 로그인시킨다.
# 사용자는 Claude Code 를 따로 설치할 필요가 없다. (이미 로그인한 Claude Code 가 있으면 그 로그인을 같이 쓴다)
def claude_cli() -> str:
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled"
    for name in ("claude.exe", "claude"):
        if (bundled / name).exists():
            return str(bundled / name)
    return shutil.which("claude") or "claude"


LOGIN = {"proc": None, "url": None}


@app.get("/api/auth")
async def api_auth():
    proc = await asyncio.create_subprocess_exec(
        claude_cli(), "auth", "status", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    try:
        info = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        info = {"loggedIn": False}
    plan = info.get("subscriptionType")
    return {
        "loggedIn": bool(info.get("loggedIn")),
        "method": info.get("authMethod"),
        "email": info.get("email"),
        "plan": plan,
        # 무료 계정은 Claude Code 를 쓸 수 없다
        "planOk": bool(info.get("loggedIn")) and (plan not in (None, "", "free") or info.get("authMethod") != "claude.ai"),
        "loginRunning": LOGIN["proc"] is not None and LOGIN["proc"].returncode is None,
        "loginUrl": LOGIN["url"],
    }


@app.post("/api/login")
async def api_login():
    """claude auth login 을 띄운다. 보통 브라우저가 자동으로 열리고, 안 열리면 출력된 주소를 화면에 보여준다."""
    if LOGIN["proc"] is not None and LOGIN["proc"].returncode is None:
        return {"started": True, "url": LOGIN["url"]}
    LOGIN["url"] = None
    proc = await asyncio.create_subprocess_exec(
        claude_cli(), "auth", "login", "--claudeai",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    LOGIN["proc"] = proc

    async def watch():
        assert proc.stdout
        async for raw in proc.stdout:
            # 터미널용 링크 표시(OSC 8 · ANSI) 를 걷어내고 첫 주소만 꺼낸다
            text = raw.decode("utf-8", "replace")
            m = re.search(r"https://[^\s\x1b\x07]+", text)
            if m and not LOGIN["url"]:
                LOGIN["url"] = m.group(0)
        await proc.wait()

    asyncio.create_task(watch())
    for _ in range(30):  # 로그인 주소가 나올 때까지 최대 3초 기다린다
        if LOGIN["url"] or proc.returncode is not None:
            break
        await asyncio.sleep(0.1)
    return {"started": True, "url": LOGIN["url"]}


@app.post("/api/login/code")
async def api_login_code(body: dict):
    """브라우저 로그인 끝에 '코드를 붙여넣으세요' 가 나오는 경우, 그 코드를 로그인 과정에 넘긴다."""
    proc = LOGIN["proc"]
    code = str(body.get("code", "")).strip()
    if not code or proc is None or proc.returncode is not None or proc.stdin is None:
        return {"ok": False}
    proc.stdin.write((code + "\n").encode())
    await proc.stdin.drain()
    return {"ok": True}


# 사람이 읽을 도구 이름
TOOL_LABELS = {
    "Read": "파일 읽는 중",
    "Write": "파일 만드는 중",
    "Edit": "파일 고치는 중",
    "Glob": "파일 찾는 중",
    "Grep": "내용 찾는 중",
    "Bash": "명령 실행 중",
    "PowerShell": "명령 실행 중",
    "Skill": "키트 단계 불러오는 중",
}


# 읽기만 하는 점검 명령은 묻지 않고 허락한다 (비개발자에게 첫 화면부터 명령 확인창을 띄우지 않기 위해).
# 프로그램 실행(python 스크립트)·설치·삭제·파일 쓰기는 여기 해당하지 않으므로 계속 묻는다.
READONLY_CMDS = {"ls", "dir", "pwd", "cat", "type", "head", "tail", "wc", "uname", "which", "where", "whoami",
                 "echo", "date", "file", "stat", "test", "[", "true", "command", "Get-ChildItem", "Get-Content",
                 "Test-Path", "Get-Location", "Write-Output"}
VERSION_ONLY = re.compile(r"^(python3?|py|uv|node|git)(\.exe)?\s+(--version|-V)$")


def is_readonly_command(cmd: str) -> bool:
    if not cmd or re.search(r"[`$]\(|<\(", cmd):
        return False
    # 출력 버리기(2>&1, 2>/dev/null, >nul)는 괜찮고, 파일에 쓰는 리디렉션은 안 된다
    cleaned = re.sub(r"\d?>&\d|\d?>\s*/dev/null|\d?>\s*nul\b", "", cmd)
    if ">" in cleaned:
        return False
    for part in re.split(r"&&|\|\||;|\|", cleaned):
        part = part.strip()
        if not part:
            continue
        if VERSION_ONLY.match(part):
            continue
        if part.split()[0] not in READONLY_CMDS:
            return False
    return True


def plain_description(name: str, data: dict) -> str:
    cmd = (data.get("command") or "").strip()
    if re.match(r"^(winget|pip|python3?\s+-m\s+pip|py\s+-m\s+pip|uv\s+pip)\b", cmd):
        return "필요한 프로그램을 설치하려고 해요."
    if re.match(r"^(python3?|py|uv\s+run)\b", cmd):
        return "만든 자동화 프로그램을 실행하려고 해요."
    if re.match(r"^(rm|del|Remove-Item)\b", cmd):
        return "파일을 지우려고 해요. 지워도 되는 파일인지 확인해 주세요."
    if name in ("Bash", "PowerShell"):
        return "컴퓨터에서 명령을 하나 실행하려고 해요. 바로 위 Claude 의 설명을 보고 정해주세요."
    return tool_summary(name, data)


def tool_summary(name: str, data: dict) -> str:
    if name in ("Bash", "PowerShell"):
        # 비개발자에게 셸 명령을 그대로 보여주지 않는다 (허락 카드의 '자세히 보기' 에서만 보인다)
        return "컴퓨터 상태 확인 중" if is_readonly_command(data.get("command", "")) else "프로그램 실행 중"
    label = TOOL_LABELS.get(name, name)
    target = data.get("file_path") or data.get("path") or data.get("pattern") or data.get("skill") or ""
    if target:
        target = str(target).replace(str(WORKSPACE) + "/", "")
    cmd = data.get("command") or ""
    detail = target or (cmd[:80] + ("…" if len(cmd) > 80 else ""))
    return f"{label} · {detail}" if detail else label


def read_state() -> dict:
    """키트 기록(results/interview.md)과 산출물 폴더에서 진행 상태를 뽑는다."""
    state = {"stage": None, "nickname": None, "track": None, "next": None, "report_submitted": None,
             "automations": [], "reports": [], "inputs": [], "outputs": []}
    rec = WORKSPACE / "results" / "interview.md"
    if rec.exists():
        m = re.search(r"^---\n(.*?)\n---", rec.read_text(encoding="utf-8"), re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    v = v.split("#")[0].strip()
                    if k.strip() == "daangn_nickname":
                        state["nickname"] = v
                    elif k.strip() in ("stage", "track", "next", "report_submitted"):
                        state[k.strip()] = v
    for key, sub, pattern in (("automations", "automations", "*/AUTOMATION.md"),
                              ("reports", "report", "submit-*.md"),
                              ("inputs", "inputs", "*"),
                              ("outputs", "outputs", "*")):
        d = WORKSPACE / sub
        if d.exists():
            items = sorted(d.glob(pattern))
            if key == "automations":
                state[key] = [p.parent.name for p in items]
            else:
                state[key] = [p.name for p in items if p.is_file() and p.name != "README.md"]
    return state


@app.get("/api/state")
async def api_state():
    return read_state()


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename or "file").name
    dest = WORKSPACE / "inputs" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    return {"saved": f"inputs/{name}"}


@app.get("/api/file/{folder}/{name:path}")
async def get_file(folder: str, name: str):
    if folder not in ("report", "outputs"):
        raise HTTPException(404)
    path = (WORKSPACE / folder / name).resolve()
    if not str(path).startswith(str((WORKSPACE / folder).resolve())) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    # 브라우저는 WebSocket 에 동일 출처 정책을 적용하지 않으므로 Origin·Host 를 직접 확인한다
    if ws.headers.get("origin") not in allowed_origins() or ws.headers.get("host") not in allowed_hosts():
        await ws.close(code=1008)
        return
    await ws.accept()
    pending: dict[str, asyncio.Future] = {}

    async def send(obj: dict):
        await ws.send_text(json.dumps(obj, ensure_ascii=False))

    async def ask_permission(tool_name: str, data: dict, ctx: ToolPermissionContext):
        """키트 설정상 확인이 필요한 동작(프로그램 실행·설치 등)을 브라우저 버튼으로 묻는다."""
        if tool_name in ("Bash", "PowerShell") and is_readonly_command(data.get("command", "")):
            return PermissionResultAllow(updated_input=data)
        rid = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        pending[rid] = fut
        await send({
            "type": "permission",
            "id": rid,
            "tool": tool_name,
            "summary": plain_description(tool_name, data),
            "command": data.get("command"),
            "description": data.get("description") or getattr(ctx, "description", None),
        })
        allow = await fut
        if allow:
            return PermissionResultAllow(updated_input=data)
        return PermissionResultDeny(message="사용자가 이 동작을 허락하지 않았습니다. 다른 방법을 쉬운 말로 제안하세요.")

    options = ClaudeAgentOptions(
        cwd=str(WORKSPACE),
        setting_sources=["project"],  # 키트의 CLAUDE.md · skills · settings.json 을 읽는다
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": "이 대화는 터미널이 아니라 웹 화면에서 진행된다. 확인이 필요한 동작은 화면에 '허락 / 거절' 버튼으로 뜬다. "
                      "'확인 창에서 예(Yes)를 누르라' 대신 '화면에 뜨는 허락 버튼을 눌러주세요' 라고 안내한다. "
                      "파일은 화면 왼쪽 '내 파일' 칸에 끌어다 놓으면 inputs 폴더에 들어간다고 안내한다. "
                      "Claude Code 를 다시 열라는 안내 대신 '이 화면을 새로고침하면 이어서 할 수 있어요' 라고 안내한다. "
                      "사용자에게 보이는 모든 글은 한국어로 쓴다. 도구를 쓰기 전후의 내부 작업 메모(영어 포함)는 사용자에게 쓰지 않는다.",
        },
        can_use_tool=ask_permission,
    )

    client = ClaudeSDKClient(options=options)
    await client.connect()
    await send({"type": "ready", "state": read_state()})

    async def pump():
        """SDK 에서 나오는 메시지를 브라우저용 이벤트로 바꿔 보낸다."""
        async for msg in client.receive_messages():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        await send({"type": "text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        await send({"type": "tool", "id": block.id, "name": block.name,
                                    "summary": tool_summary(block.name, block.input or {})})
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock):
                        await send({"type": "tool_done", "id": block.tool_use_id, "error": bool(block.is_error)})
            elif isinstance(msg, ResultMessage):
                await send({"type": "done", "cost": msg.total_cost_usd, "ms": msg.duration_ms,
                            "state": read_state()})

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            data = json.loads(await ws.receive_text())
            kind = data.get("type")
            if kind == "user":
                await send({"type": "busy"})
                await client.query(data["text"])
            elif kind == "permission_reply":
                fut = pending.pop(data["id"], None)
                if fut and not fut.done():
                    fut.set_result(bool(data.get("allow")))
            elif kind == "interrupt":
                await client.interrupt()
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        for fut in pending.values():
            if not fut.done():
                fut.set_result(False)
        await client.disconnect()


app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(BASE.parent / "workspace"))
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--open", action="store_true", help="시작하면 브라우저를 연다")
    args = parser.parse_args()
    WORKSPACE = Path(args.workspace).resolve()
    PORT = args.port
    url = f"http://127.0.0.1:{PORT}/"
    if not (WORKSPACE / "CLAUDE.md").exists():
        raise SystemExit(f"키트 폴더를 찾지 못했어요 (CLAUDE.md 없음): {WORKSPACE}")
    if port_in_use(PORT):
        # 이미 켜져 있으면 화면만 다시 연다
        print(f"이미 실행 중이에요. 브라우저로 엽니다: {url}")
        webbrowser.open(url)
        sys.exit(0)
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print("")
    print("  AI 업무자동화 코치가 켜졌어요.")
    print(f"  브라우저에서 {url} 를 여세요. (자동으로 열려요)")
    print("  이 창을 닫으면 코치도 꺼져요. 다 쓰면 닫으셔도 돼요.")
    print("")
    os.environ.setdefault("PYTHONUTF8", "1")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
