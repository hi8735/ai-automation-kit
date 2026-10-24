// AI 업무자동화 코치 — 브라우저 쪽. 서버(/ws)와 이벤트를 주고받는다.
(() => {
  const $ = (s) => document.querySelector(s);
  const log = $("#log"), input = $("#input"), sendBtn = $("#send"), stopBtn = $("#stop");
  const statusEl = $("#status"), quick = $("#quick");
  const STAGE_ORDER = ["welcome", "track", "deep-dive", "diagnosis", "build", "report"];
  let ws, busy = false, typingEl = null;
  const tools = new Map();

  marked.setOptions({ breaks: true });
  // 링크는 새 탭으로 연다 (이 화면을 벗어나면 대화가 끊긴다). 외부 이미지는 막는다.
  DOMPurify.addHook("afterSanitizeAttributes", (n) => {
    if (n.tagName === "A") { n.setAttribute("target", "_blank"); n.setAttribute("rel", "noopener noreferrer"); }
  });
  const md = (t) => DOMPurify.sanitize(marked.parse(t), { FORBID_TAGS: ["img"] });

  function scroll() { log.scrollTop = log.scrollHeight; }
  function clearEmpty() { const e = $("#empty"); if (e) e.remove(); }

  function setBusy(b) {
    busy = b;
    sendBtn.disabled = b;
    stopBtn.hidden = !b;
    statusEl.textContent = b ? "Claude 가 생각하는 중이에요" : "연결됨 · 키트 폴더에서 작업 중";
    if (b && !typingEl) { typingEl = el("div", "typing", "답을 준비하고 있어요"); log.appendChild(typingEl); scroll(); }
    if (!b && typingEl) { typingEl.remove(); typingEl = null; }
  }

  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  function add(node) {
    clearEmpty();
    if (typingEl && typingEl.parentNode) log.insertBefore(node, typingEl); else log.appendChild(node);
    scroll();
  }

  function addUser(text) { add(el("div", "msg u", text)); }

  function addClaude(text) {
    const wrap = el("div", "msg c");
    const b = el("div", "bubble");
    b.innerHTML = md(text);
    wrap.appendChild(b);
    add(wrap);
    renderQuick(text);
  }

  // "**1.** ... / 2. ..." 같은 번호 선택지가 있으면 빠른 답 버튼을 띄운다
  function renderQuick(text) {
    quick.innerHTML = "";
    const opts = [];
    for (const line of text.split("\n")) {
      const m = line.match(/^\s*(?:\*\*)?([1-9])[.)](?:\*\*)?\s+(.+)$/);
      if (m) opts.push([m[1], m[2].replace(/\*\*/g, "").slice(0, 40)]);
    }
    if (opts.length >= 2 && opts.length <= 5) {
      for (const [n, label] of opts) {
        const btn = el("button", null, `${n}. ${label}`);
        btn.onclick = () => submit(n);
        quick.appendChild(btn);
      }
    }
  }

  function addTool(id, summary) {
    const n = el("div", "tool");
    n.appendChild(el("span", "dot"));
    n.appendChild(el("span", null, summary));
    tools.set(id, n);
    add(n);
  }

  function addPermission(p) {
    const box = el("div", "perm");
    box.appendChild(el("b", null, "이 동작을 허락할까요?"));
    box.appendChild(el("span", null, p.summary));
    if (p.command) {
      const det = el("details");
      det.appendChild(el("summary", null, "자세히 보기"));
      det.appendChild(el("code", null, p.command));
      box.appendChild(det);
    }
    const row = el("div", "row");
    const yes = el("button", "yes", "허락");
    const no = el("button", null, "거절");
    const answer = (allow) => {
      ws.send(JSON.stringify({ type: "permission_reply", id: p.id, allow }));
      box.classList.add("answered");
      row.replaceWith(el("span", null, allow ? "✓ 허락했어요" : "거절했어요"));
    };
    yes.onclick = () => answer(true);
    no.onclick = () => answer(false);
    row.append(yes, no);
    box.appendChild(row);
    add(box);
  }

  function renderState(s) {
    if (!s) return;
    $("#who").innerHTML = s.nickname ? `<b>${DOMPurify.sanitize(s.nickname)}</b> 님의 키트` : "닉네임을 알려주시면 여기에 표시돼요";
    let idx = STAGE_ORDER.indexOf(s.stage === "done" ? "report" : s.stage);
    if (s.report_submitted === "yes") idx = Math.max(idx, STAGE_ORDER.length);
    document.querySelectorAll("#stages li").forEach((li, i) => {
      li.className = i < idx ? "done" : i === idx ? "now" : "";
    });
    $("#next").textContent = s.next && s.next !== "" ? `다음: ${s.next}` : "";
    const files = $("#files");
    files.innerHTML = "";
    const item = (tag, cls, name, href) => {
      const li = el("li");
      li.appendChild(el("span", "tag " + (cls || ""), tag));
      if (href) { const a = el("a", null, name); a.href = href; a.target = "_blank"; li.appendChild(a); }
      else li.appendChild(el("span", null, name));
      files.appendChild(li);
    };
    s.reports.forEach((f) => item("리포트", "report", f, `/api/file/report/${encodeURIComponent(f)}`));
    s.automations.forEach((a) => item("자동화", "auto", a));
    s.outputs.forEach((f) => item("결과", "", f, `/api/file/outputs/${encodeURIComponent(f)}`));
    s.inputs.forEach((f) => item("넣은 파일", "", f));
  }

  async function refreshState() {
    try { renderState(await (await fetch("/api/state")).json()); } catch (e) {}
  }

  function connect() {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    ws.onopen = () => { statusEl.textContent = "Claude 준비 중…"; };
    ws.onclose = (ev) => {
      setBusy(false); sendBtn.disabled = true;
      statusEl.textContent = ev.code === 4000
        ? "다른 탭에서 코치를 열어서 이 화면은 멈췄어요. 새로 연 탭에서 이어서 하세요"
        : "연결이 끊겼어요. 새로고침하면 이어서 할 수 있어요. 안 되면 바탕화면 아이콘을 다시 눌러주세요 (기록은 저장돼 있어요)";
    };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "ready") { if (!busy) setBusy(false); renderState(m.state); }
      else if (m.type === "busy") setBusy(true);
      else if (m.type === "text") addClaude(m.text);
      else if (m.type === "tool") addTool(m.id, m.summary);
      else if (m.type === "tool_done") { const n = tools.get(m.id); if (n) n.classList.add(m.error ? "err" : "ok"); refreshState(); }
      else if (m.type === "permission") addPermission(m);
      else if (m.type === "done") {
        setBusy(false);
        renderState(m.state);
        if (m.cost != null) add(el("div", "cost", `이번 답변 ${(m.ms / 1000).toFixed(0)}초`));
      }
    };
  }

  function submit(text) {
    text = (text ?? input.value).trim();
    if (!text || busy || !ws || ws.readyState !== 1) return;
    quick.innerHTML = "";
    addUser(text);
    ws.send(JSON.stringify({ type: "user", text }));
    input.value = "";
    autosize();
    setBusy(true);
  }

  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; }

  $("#form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  });
  stopBtn.onclick = () => ws && ws.send(JSON.stringify({ type: "interrupt" }));
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-cmd]");
    if (b) submit(b.dataset.cmd);
  });

  // 파일 올리기 (선택 · 끌어다 놓기)
  const drop = $("#drop"), fileInput = $("#file");
  async function upload(files) {
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      let j = null;
      try { const r = await fetch("/api/upload", { method: "POST", body: fd }); j = r.ok ? await r.json() : null; } catch (e) {}
      if (!j) { add(el("div", "cost", `⚠️ ${f.name} 을 올리지 못했어요 (50MB 까지 올릴 수 있어요)`)); continue; }
      add(el("div", "cost", `📎 ${j.saved} 에 올렸어요`));
      if (!busy) input.value = (input.value ? input.value + "\n" : "") + `${j.saved} 파일을 넣었어요.`;
    }
    autosize();
    refreshState();
  }
  fileInput.addEventListener("change", () => upload(fileInput.files));
  ["dragover", "dragenter"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));

  // 복사한 파일·캡처 이미지를 붙여넣으면(Ctrl+V / ⌘+V) 바로 올린다. 글자만 있으면 평소처럼 붙여넣는다.
  document.addEventListener("paste", (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (!files.length) return;
    e.preventDefault();
    const d = new Date(), p2 = (n) => String(n).padStart(2, "0");
    const stamp = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}-${p2(d.getMinutes())}-${p2(d.getSeconds())}`;
    // 캡처를 붙여넣으면 이름이 모두 image.png 라서 시각을 붙여 구분한다
    upload(files.map((f, i) => /^image\.\w+$/i.test(f.name)
      ? new File([f], `붙여넣은 이미지 ${stamp}${files.length > 1 ? "-" + (i + 1) : ""}.${f.name.split(".").pop()}`, { type: f.type })
      : f));
  });

  // ── 로그인 확인 → 통과하면 대화 연결 ──
  const gate = $("#gate"), gTitle = $("#gate-title"), gDesc = $("#gate-desc"), gSub = $("#gate-sub"), loginBtn = $("#login-btn");
  let polling = null;

  async function checkAuth() {
    try { return await (await fetch("/api/auth")).json(); } catch (e) { return null; }
  }

  function showGate(kind, a) {
    gate.hidden = false;
    if (kind === "plan") {
      gTitle.textContent = "유료 플랜이 필요해요";
      gDesc.textContent = `${a.email || "이 계정"} 은 무료 플랜이라 사용할 수 없어요. Claude Pro 이상으로 바꾼 뒤 아래 버튼을 눌러주세요.`;
      loginBtn.textContent = "플랜 바꿨어요 · 다시 확인";
      gSub.innerHTML = '<a href="https://claude.ai/upgrade" target="_blank" rel="noopener">플랜 확인하러 가기 →</a>';
    } else {
      gTitle.textContent = "Claude 계정으로 로그인해 주세요";
      loginBtn.textContent = "Claude 계정으로 로그인";
    }
  }

  async function startPolling() {
    if (polling) return;
    polling = setInterval(async () => {
      const a = await checkAuth();
      if (a && a.loginUrl && !gSub.querySelector("a")) {
        gSub.innerHTML = "";
        gSub.append("로그인 창이 안 열리면 ");
        const link = el("a", null, "여기를 눌러 직접 여세요");
        link.href = a.loginUrl; link.target = "_blank"; link.rel = "noopener";
        gSub.append(link);
      }
      if (a && !a.loggedIn && !a.loginRunning) {
        clearInterval(polling); polling = null;
        gSub.textContent = "로그인이 끝나지 않았어요. 위 버튼을 눌러 처음부터 다시 해주세요.";
        return;
      }
      if (a && a.loggedIn) {
        clearInterval(polling); polling = null;
        if (a.planOk) { gate.hidden = true; connect(); } else showGate("plan", a);
      }
    }, 2000);
  }

  loginBtn.onclick = async () => {
    const a = await checkAuth();
    if (a && a.loggedIn && a.planOk) { gate.hidden = true; connect(); return; }
    if (a && a.loggedIn && !a.planOk) { showGate("plan", a); return; }
    loginBtn.disabled = true;
    loginBtn.textContent = "브라우저에서 로그인을 마쳐주세요…";
    gSub.textContent = "로그인 창이 새로 열렸어요. 다 하면 이 화면으로 돌아오세요.";
    const r = await (await fetch("/api/login", { method: "POST" })).json();
    if (r.url) {
      gSub.innerHTML = "";
      gSub.append("로그인 창이 안 열리면 ");
      const link = el("a", null, "여기를 눌러 직접 여세요");
      link.href = r.url; link.target = "_blank"; link.rel = "noopener";
      gSub.append(link);
    }
    loginBtn.disabled = false;
    $("#code-box").hidden = false;
    startPolling();
  };

  $("#code-btn").onclick = async () => {
    const code = $("#code-input").value.trim();
    if (!code) return;
    const r = await (await fetch("/api/login/code", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }) })).json();
    gSub.textContent = r.ok ? "확인 중이에요…" : "로그인을 처음부터 다시 눌러주세요.";
    startPolling();
  };

  // 화면이 열려 있다고 서버에 알린다. 탭을 모두 닫으면 서버가 스스로 꺼진다.
  setInterval(() => { fetch("/api/ping").catch(() => {}); }, 30000);

  (async () => {
    const a = await checkAuth();
    if (a && a.loggedIn && a.planOk) connect();
    else if (a && a.loggedIn) showGate("plan", a);
    else showGate("login", a || {});
  })();
})();
