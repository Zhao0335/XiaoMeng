/* 小萌管理面板 · vanilla JS
   ===========================
   - WS 协议复刻 run_live2d.py 的 auth_required → login_request → code_sent → verify_code → auth_ok
   - 通过后切到主视图，根据 tab 渲染对应配置编辑器
   - 敏感字段（••••••••）默认 mask，眼睛图标向后端请求 reveal
   - 历史快照：每次 save 自动生成，UI 抽屉可预览 diff + 一键恢复
   - 自动填充：input 的最近 5 次值存到 localStorage，下次以 datalist 给建议
*/

(function () {
  "use strict";

  // ─── 状态 ──────────────────────────────────────────────
  let ws = null;
  let state = {
    qq: null,
    level: null,
    activeKey: "qq_config",
    files: [],              // [{key, path, kind}]
    cache: {},              // key → 后端返回的 {kind, data, raw_text}
    pendingSnapshotName: null,
  };

  // ─── DOM 引用 ──────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const els = {
    viewLogin: $("#view-login"),
    viewMain:  $("#view-main"),
    stepQQ:    $("#step-qq"),
    stepCode:  $("#step-code"),
    inputQQ:   $("#input-qq"),
    inputCode: $("#input-code"),
    btnSendCode: $("#btn-send-code"),
    btnVerify: $("#btn-verify"),
    btnBack:   $("#btn-back"),
    sentQQ:    $("#sent-qq"),
    loginMsg:  $("#login-msg"),
    tabs:      $("#tabs"),
    userQQ:    $("#user-qq"),
    userLevel: $("#user-level"),
    editorTitle: $("#editor-title"),
    editorBody: $("#editor-body"),
    btnSave:    $("#btn-save"),
    btnReload:  $("#btn-reload"),
    btnHistory: $("#btn-history"),
    btnCloseHistory: $("#btn-close-history"),
    historyDrawer: $("#history-drawer"),
    historyList: $("#history-list"),
    historyDiff: $("#history-diff"),
    statusMsg:  $("#status-msg"),
  };

  // ─── 工具 ──────────────────────────────────────────────
  function status(text, kind = "") {
    els.statusMsg.textContent = text;
    els.statusMsg.className = "status-msg " + kind;
    if (text) setTimeout(() => {
      if (els.statusMsg.textContent === text) {
        els.statusMsg.textContent = "";
        els.statusMsg.className = "status-msg";
      }
    }, 4000);
  }

  function loginMsg(text, ok = false) {
    els.loginMsg.textContent = text || "";
    els.loginMsg.className = "login-msg " + (ok ? "ok" : "");
  }

  function send(obj) {
    if (!ws || ws.readyState !== 1) {
      status("连接断开，刷新页面重试", "fail");
      return;
    }
    ws.send(JSON.stringify(obj));
  }

  // localStorage 自动填充
  function autofillKey(jsonPath) {
    return "xm-autofill-" + jsonPath;
  }
  function rememberAutofill(jsonPath, value) {
    if (!value || value === "••••••••") return;
    const k = autofillKey(jsonPath);
    let list = [];
    try { list = JSON.parse(localStorage.getItem(k) || "[]"); } catch (_) {}
    list = [value, ...list.filter((v) => v !== value)].slice(0, 5);
    localStorage.setItem(k, JSON.stringify(list));
  }
  function getAutofill(jsonPath) {
    try {
      return JSON.parse(localStorage.getItem(autofillKey(jsonPath)) || "[]");
    } catch (_) { return []; }
  }

  // 敏感字段
  function isSensitiveKey(key) {
    const lower = String(key).toLowerCase();
    return ["api_key", "apikey", "token", "password", "secret"].some((p) => lower.includes(p));
  }

  // ─── WS 连接 + 鉴权 ────────────────────────────────────
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/admin/ws`);

    ws.onopen = () => loginMsg("已连接，请输入 QQ 号");
    ws.onerror = () => loginMsg("WebSocket 错误，请刷新");
    ws.onclose = () => {
      if (state.qq) status("连接已断开，请刷新页面", "fail");
      else loginMsg("连接已断开");
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      handleMsg(msg);
    };
  }

  function handleMsg(msg) {
    switch (msg.type) {
      case "auth_required":
        loginMsg("");
        return;
      case "code_sent":
        els.sentQQ.textContent = msg.qq;
        els.stepQQ.classList.add("hidden");
        els.stepCode.classList.remove("hidden");
        els.inputCode.focus();
        loginMsg("验证码已发到 QQ 私聊，5 分钟内有效", true);
        return;
      case "auth_fail":
        loginMsg(msg.reason || "鉴权失败");
        return;
      case "auth_ok":
        state.qq = msg.qq;
        state.level = msg.level;
        els.userQQ.textContent = msg.qq;
        els.userLevel.textContent = msg.label || msg.level;
        els.viewLogin.classList.add("hidden");
        els.viewMain.classList.remove("hidden");
        return;
      case "files":
        state.files = msg.items;
        loadKey(state.activeKey);
        return;
      case "config":
        state.cache[msg.key] = { kind: msg.kind, data: msg.data, raw_text: msg.raw_text, error: msg.error };
        if (msg.key === state.activeKey) renderEditor();
        return;
      case "revealed":
        applyRevealed(msg.key, msg.path, msg.value);
        return;
      case "saved":
        status(`✓ 已保存 ${msg.key}（快照 ${msg.snapshot || "—"}）`, "ok");
        // 重新拉一遍以同步 mask 状态
        send({ type: "load", key: msg.key });
        return;
      case "history":
        renderHistory(msg.key, msg.items);
        return;
      case "snapshot":
        renderDiff(msg.name, msg.text);
        return;
      case "restored":
        status(`已从快照恢复 ${msg.key}`, "ok");
        send({ type: "load", key: msg.key });
        return;
      case "error":
        status(`✗ ${msg.message}`, "fail");
        return;
    }
  }

  // ─── 登录流程 ──────────────────────────────────────────
  els.btnSendCode.addEventListener("click", () => {
    const qq = parseInt(els.inputQQ.value.trim(), 10);
    if (!qq || qq < 10000) { loginMsg("请输入有效的 QQ 号"); return; }
    send({ type: "login_request", qq });
  });
  els.btnBack.addEventListener("click", () => {
    els.stepCode.classList.add("hidden");
    els.stepQQ.classList.remove("hidden");
    loginMsg("");
  });
  els.btnVerify.addEventListener("click", () => {
    const qq = parseInt(els.inputQQ.value.trim(), 10);
    const code = els.inputCode.value.trim();
    if (!/^\d{6}$/.test(code)) { loginMsg("验证码应为 6 位数字"); return; }
    send({ type: "verify_code", qq, code });
  });
  els.inputCode.addEventListener("keydown", (e) => {
    if (e.key === "Enter") els.btnVerify.click();
  });
  els.inputQQ.addEventListener("keydown", (e) => {
    if (e.key === "Enter") els.btnSendCode.click();
  });

  // ─── Tabs ──────────────────────────────────────────────
  els.tabs.addEventListener("click", (e) => {
    if (e.target.tagName !== "BUTTON") return;
    const key = e.target.dataset.tab;
    if (!key || key === state.activeKey) return;
    [...els.tabs.children].forEach((t) => t.classList.toggle("active", t.dataset.tab === key));
    state.activeKey = key;
    loadKey(key);
    els.historyDrawer.classList.add("hidden");
  });

  function loadKey(key) {
    const f = state.files.find((x) => x.key === key) || { kind: "json", path: key };
    const tabBtn = els.tabs.querySelector(`[data-tab="${key}"]`);
    els.editorTitle.textContent = tabBtn ? tabBtn.textContent : key;
    els.editorBody.innerHTML = '<p class="placeholder">加载中…</p>';
    send({ type: "load", key });
  }

  // ─── 编辑器渲染 ────────────────────────────────────────
  function renderEditor() {
    const key = state.activeKey;
    const c = state.cache[key];
    if (!c) { els.editorBody.innerHTML = '<p class="placeholder">无数据</p>'; return; }

    if (key === "qq_permissions") {
      renderPermissions(c.data);
    } else if (c.kind === "json") {
      renderJsonTree(c.data, key);
    } else if (c.kind === "json_broken") {
      els.editorBody.innerHTML = `
        <p style="color:var(--pink-400)">⚠ JSON 解析失败：${escapeHtml(c.error)}</p>
        <textarea id="raw-text" style="width:100%;min-height:400px;font-family:monospace">${escapeHtml(c.data)}</textarea>
      `;
    } else {
      renderMarkdownEditor(c.data || "");
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[m]);
  }

  // JSON tree
  function renderJsonTree(data, key) {
    const root = document.createElement("div");
    root.className = "json-tree";
    root.appendChild(buildNode(data, "", true));
    els.editorBody.innerHTML = "";
    els.editorBody.appendChild(root);
  }

  function buildNode(value, path, isRoot) {
    if (Array.isArray(value)) {
      const wrap = document.createElement("div");
      value.forEach((item, idx) => {
        const itemPath = path + `[${idx}]`;
        if (typeof item === "object" && item !== null) {
          const card = document.createElement("div");
          card.className = "array-item";
          const rm = document.createElement("button");
          rm.className = "item-remove";
          rm.textContent = "×";
          rm.onclick = () => { value.splice(idx, 1); renderEditor(); };
          card.appendChild(rm);
          card.appendChild(buildNode(item, itemPath, false));
          wrap.appendChild(card);
        } else {
          wrap.appendChild(buildScalar(idx + "", item, itemPath, value, idx));
        }
      });
      const add = document.createElement("button");
      add.className = "btn-add";
      add.textContent = "＋ 添加项";
      add.onclick = () => {
        const template = value.length ? structuredClone(value[value.length - 1]) : "";
        value.push(template);
        renderEditor();
      };
      wrap.appendChild(add);
      return wrap;
    }

    if (typeof value === "object" && value !== null) {
      const wrap = document.createElement("div");
      Object.keys(value).forEach((k) => {
        const sub = value[k];
        const subPath = path ? `${path}.${k}` : k;
        if (typeof sub === "object" && sub !== null) {
          const det = document.createElement("details");
          if (isRoot) det.open = true;
          const sum = document.createElement("summary");
          sum.textContent = k + (Array.isArray(sub) ? ` [${sub.length}]` : "");
          det.appendChild(sum);
          det.appendChild(buildNode(sub, subPath, false));
          wrap.appendChild(det);
        } else {
          wrap.appendChild(buildScalar(k, sub, subPath, value, k));
        }
      });
      return wrap;
    }
    // 顶层标量（理论上不会出现）
    return buildScalar("(value)", value, path, null, null);
  }

  function buildScalar(label, value, jsonPath, parent, parentKey) {
    const row = document.createElement("div");
    row.className = "field-row";

    const keyEl = document.createElement("div");
    keyEl.className = "field-key";
    keyEl.textContent = label;
    row.appendChild(keyEl);

    let inputEl;
    if (typeof value === "boolean") {
      inputEl = document.createElement("select");
      ["true", "false"].forEach((v) => {
        const o = document.createElement("option");
        o.value = v; o.textContent = v;
        inputEl.appendChild(o);
      });
      inputEl.value = String(value);
      inputEl.onchange = () => { parent[parentKey] = inputEl.value === "true"; };
    } else if (typeof value === "number") {
      inputEl = document.createElement("input");
      inputEl.type = "number";
      inputEl.value = value;
      inputEl.onchange = () => {
        const n = Number(inputEl.value);
        if (!Number.isNaN(n)) parent[parentKey] = n;
      };
    } else {
      inputEl = document.createElement("input");
      inputEl.type = "text";
      inputEl.value = value === null ? "" : String(value);
      inputEl.setAttribute("list", "autofill-" + jsonPath.replace(/[^a-zA-Z0-9]/g, "_"));
      // datalist
      const dl = document.createElement("datalist");
      dl.id = inputEl.getAttribute("list");
      getAutofill(jsonPath).forEach((v) => {
        const o = document.createElement("option");
        o.value = v;
        dl.appendChild(o);
      });
      row.appendChild(dl);
      inputEl.onchange = () => {
        parent[parentKey] = inputEl.value;
        rememberAutofill(jsonPath, inputEl.value);
      };
    }
    row.appendChild(inputEl);

    // 敏感字段：眼睛图标
    if (isSensitiveKey(label) && typeof value === "string") {
      const eye = document.createElement("button");
      eye.className = "field-eye";
      eye.textContent = "👁";
      eye.title = "临时显示原值";
      eye.onclick = () => {
        const segs = parseJsonPath(jsonPath);
        send({ type: "reveal", key: state.activeKey, path: segs });
        inputEl.dataset.revealPath = jsonPath;
      };
      row.appendChild(eye);
    } else {
      const spacer = document.createElement("span");
      row.appendChild(spacer);
    }
    return row;
  }

  function parseJsonPath(p) {
    // "models[0].api_key" → ["models", 0, "api_key"]
    const out = [];
    const re = /([^.\[\]]+)|\[(\d+)\]/g;
    let m;
    while ((m = re.exec(p))) {
      if (m[2] !== undefined) out.push(parseInt(m[2], 10));
      else out.push(m[1]);
    }
    return out;
  }

  function applyRevealed(key, path, value) {
    // path 是数组，转回字符串去找 input
    if (key !== state.activeKey) return;
    const jsonPath = path.map((s, i) => typeof s === "number" ? `[${s}]` : (i === 0 ? s : `.${s}`)).join("");
    const target = [...els.editorBody.querySelectorAll("input")].find(
      (el) => el.dataset.revealPath === jsonPath
    );
    if (target) {
      target.type = "text";
      target.value = value == null ? "" : String(value);
      // 同步到内存模型
      const segs = path;
      let cur = state.cache[key].data;
      for (let i = 0; i < segs.length - 1; i++) cur = cur[segs[i]];
      cur[segs[segs.length - 1]] = value;
    }
  }

  // 权限编辑
  function renderPermissions(data) {
    const root = document.createElement("div");
    ["admins", "blacklist", "whitelist"].forEach((section) => {
      const sec = document.createElement("div");
      sec.className = "perm-section";
      const h = document.createElement("h3");
      h.textContent = ({
        admins: "管理员", blacklist: "黑名单", whitelist: "白名单",
      })[section];
      sec.appendChild(h);

      const listEl = document.createElement("div");
      const entries = data[section] || {};
      Object.keys(entries).forEach((qq) => {
        const info = entries[qq] || {};
        const row = document.createElement("div");
        row.className = "perm-row";
        const qqEl = document.createElement("div");
        qqEl.className = "perm-qq";
        qqEl.textContent = qq;
        const nickEl = document.createElement("div");
        nickEl.className = "perm-nick";
        nickEl.textContent = info.nickname || "—";
        const rm = document.createElement("button");
        rm.textContent = "×";
        rm.title = "移除";
        rm.onclick = () => {
          delete entries[qq];
          renderEditor();
        };
        row.appendChild(qqEl);
        row.appendChild(nickEl);
        row.appendChild(rm);
        listEl.appendChild(row);
      });
      sec.appendChild(listEl);

      // 添加
      const addRow = document.createElement("div");
      addRow.className = "perm-add";
      const qqInput = document.createElement("input");
      qqInput.placeholder = "QQ 号";
      qqInput.type = "number";
      const nickInput = document.createElement("input");
      nickInput.placeholder = "昵称（可选）";
      const addBtn = document.createElement("button");
      addBtn.className = "btn-add";
      addBtn.textContent = "＋";
      addBtn.onclick = () => {
        const qq = qqInput.value.trim();
        if (!qq) return;
        data[section] = data[section] || {};
        data[section][qq] = {
          nickname: nickInput.value.trim(),
          added_at: new Date().toISOString(),
          added_by: state.qq,
        };
        renderEditor();
      };
      addRow.appendChild(qqInput);
      addRow.appendChild(nickInput);
      addRow.appendChild(addBtn);
      sec.appendChild(addRow);

      root.appendChild(sec);
    });
    els.editorBody.innerHTML = "";
    els.editorBody.appendChild(root);
  }

  // Markdown 编辑
  function renderMarkdownEditor(text) {
    const wrap = document.createElement("div");
    wrap.className = "md-editor";
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.id = "md-textarea";
    const preview = document.createElement("div");
    preview.className = "md-preview";
    const render = () => {
      preview.innerHTML = simpleMd(ta.value);
      state.cache[state.activeKey].data = ta.value;
    };
    ta.addEventListener("input", render);
    wrap.appendChild(ta);
    wrap.appendChild(preview);
    els.editorBody.innerHTML = "";
    els.editorBody.appendChild(wrap);
    render();
  }

  // 极简 Markdown（只用于预览，不追求完整）
  function simpleMd(src) {
    let h = escapeHtml(src);
    h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    h = h.replace(/^- (.+)$/gm, "<li>$1</li>");
    h = h.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
    h = h.replace(/\n\n/g, "</p><p>");
    return `<p>${h}</p>`;
  }

  // ─── 保存 ──────────────────────────────────────────────
  els.btnSave.addEventListener("click", () => {
    const key = state.activeKey;
    const c = state.cache[key];
    if (!c) return;
    let payload;
    if (key === "qq_permissions" || (c.kind === "json" && key !== "qq_permissions")) {
      payload = c.data;
    } else if (c.kind === "json_broken") {
      const ta = document.getElementById("raw-text");
      try { payload = JSON.parse(ta.value); }
      catch (e) { status("✗ JSON 解析失败：" + e.message, "fail"); return; }
    } else {
      const ta = document.getElementById("md-textarea");
      payload = ta ? ta.value : c.data;
    }
    send({ type: "save", key, data: payload });
    status("保存中…");
  });

  els.btnReload.addEventListener("click", () => loadKey(state.activeKey));

  // ─── 历史 ──────────────────────────────────────────────
  els.btnHistory.addEventListener("click", () => {
    els.historyDrawer.classList.remove("hidden");
    send({ type: "history", key: state.activeKey });
  });
  els.btnCloseHistory.addEventListener("click", () => {
    els.historyDrawer.classList.add("hidden");
    els.historyDiff.innerHTML = "";
  });

  function renderHistory(key, items) {
    els.historyList.innerHTML = "";
    if (!items.length) {
      els.historyList.innerHTML = '<li style="color:var(--ink-soft);text-align:center">（暂无快照）</li>';
      return;
    }
    items.forEach((it) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <div><span class="ts">${escapeHtml(it.pretty)}</span><span class="size">${it.size} B</span></div>
        <div class="actions">
          <button data-act="preview">预览 diff</button>
          <button data-act="restore">恢复</button>
        </div>
      `;
      li.querySelector('[data-act="preview"]').onclick = () => {
        [...els.historyList.children].forEach((x) => x.classList.remove("active"));
        li.classList.add("active");
        state.pendingSnapshotName = it.name;
        send({ type: "diff", name: it.name });
      };
      li.querySelector('[data-act="restore"]').onclick = () => {
        if (!confirm(`确定从 ${it.pretty} 的快照恢复？当前内容会先打一份新快照。`)) return;
        send({ type: "restore", key, name: it.name });
      };
      els.historyList.appendChild(li);
    });
  }

  function renderDiff(name, snapshotText) {
    const cur = state.cache[state.activeKey];
    if (!cur) return;
    const curText = cur.raw_text || (typeof cur.data === "string" ? cur.data : JSON.stringify(cur.data, null, 2));
    els.historyDiff.innerHTML = lineDiff(snapshotText, curText);
  }

  function lineDiff(a, b) {
    const aL = a.split("\n");
    const bL = b.split("\n");
    const out = [];
    const n = Math.max(aL.length, bL.length);
    for (let i = 0; i < n; i++) {
      if (aL[i] === bL[i]) { out.push(escapeHtml(aL[i] ?? "")); }
      else {
        if (aL[i] !== undefined) out.push(`<span class="del">- ${escapeHtml(aL[i])}</span>`);
        if (bL[i] !== undefined) out.push(`<span class="ins">+ ${escapeHtml(bL[i])}</span>`);
      }
    }
    return out.join("\n");
  }

  // ─── 吉祥物 SVG fallback ───────────────────────────────
  window.makeMascotFallback = function () {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <radialGradient id="g" cx="50%" cy="40%">
            <stop offset="0%" stop-color="#FFE4F1"/>
            <stop offset="100%" stop-color="#FFB6D9"/>
          </radialGradient>
        </defs>
        <circle cx="50" cy="55" r="38" fill="url(#g)"/>
        <circle cx="38" cy="48" r="4" fill="#4A2B3F"/>
        <circle cx="62" cy="48" r="4" fill="#4A2B3F"/>
        <path d="M40 65 Q50 73 60 65" stroke="#4A2B3F" stroke-width="2.5" fill="none" stroke-linecap="round"/>
        <circle cx="30" cy="60" r="5" fill="#FF8FAB" opacity="0.55"/>
        <circle cx="70" cy="60" r="5" fill="#FF8FAB" opacity="0.55"/>
        <path d="M50 18 Q42 8 38 18 Q50 12 50 18 Q50 12 62 18 Q58 8 50 18" fill="#FF8FAB"/>
      </svg>
    `;
    return wrap.firstElementChild;
  };

  // ─── 启动 ──────────────────────────────────────────────
  connect();
})();
