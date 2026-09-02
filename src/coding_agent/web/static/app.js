const taskEl = document.getElementById("task");
const sendBtn = document.getElementById("send-btn");
const stopBtn = document.getElementById("stop-btn");
const refreshTreeBtn = document.getElementById("refresh-tree");
const saveFileBtn = document.getElementById("save-file");
const chatView = document.getElementById("chat-view");
const treeList = document.getElementById("tree-list");
const statusEl = document.getElementById("status");
const filePathInput = document.getElementById("file-path");
const projectInfo = document.getElementById("project-info");
const openProjectBtn = document.getElementById("open-project");
const projectModal = document.getElementById("project-modal");
const closeProjectModalBtn = document.getElementById("close-project-modal");
const browseUpBtn = document.getElementById("browse-up");
const browseGoBtn = document.getElementById("browse-go");
const browsePathInput = document.getElementById("browse-path");
const browseList = document.getElementById("browse-list");
const browsePathLabel = document.getElementById("browse-path-label");
const pathModalTitle = document.getElementById("path-modal-title");
const pathModalExtra = document.getElementById("path-modal-extra");
const pathModalName = document.getElementById("path-modal-name");
const newFileBtn = document.getElementById("new-file-btn");
const newFolderBtn = document.getElementById("new-folder-btn");
const refreshTreeSidebarBtn = document.getElementById("refresh-tree-sidebar");
const conversationToggle = document.getElementById("conversation-toggle");
const conversationMenu = document.getElementById("conversation-menu");
const newChatBtn = document.getElementById("new-chat");
const activeSessionLabel = document.getElementById("active-session-label");
const sessionPanel = document.querySelector(".session-panel");
const authModal = document.getElementById("auth-modal");
const authStatusEl = document.getElementById("auth-status");
const authNoteEl = document.getElementById("auth-note");
const authUserEl = document.getElementById("auth-user");
const loginUsername = document.getElementById("login-username");
const loginPassword = document.getElementById("login-password");
const registerUsername = document.getElementById("register-username");
const registerPassword = document.getElementById("register-password");
const loginBtn = document.getElementById("login-btn");
const registerBtn = document.getElementById("register-btn");
const authBootstrapBtn = document.getElementById("auth-bootstrap");
const logoutBtn = document.getElementById("logout-btn");
const bootstrapMarker = "chasm_bootstrap_done";
const layoutEl = document.querySelector(".layout");
const leftResizeHandle = document.getElementById("left-resize");
const rightResizeHandle = document.getElementById("right-resize");
const leftWidthKey = "chasm_left_panel_width";
const rightWidthKey = "chasm_right_panel_width";

let currentSession = null;
let currentEventSource = null;
let currentProjectRoot = "";
let selectedFile = "";
let editor = null;
let browseCurrentPath = "";
let currentUser = null;
const openFolders = new Set();
let pathModalMode = "project";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function setPanelWidth(side, value) {
  const key = side === "left" ? leftWidthKey : rightWidthKey;
  const min = side === "left" ? 200 : 320;
  const max = side === "left" ? 420 : 560;
  const next = `${clamp(value, min, max)}px`;
  document.documentElement.style.setProperty(side === "left" ? "--left-panel-width" : "--right-panel-width", next);
  localStorage.setItem(key, next);
}

function restorePanelWidths() {
  const left = localStorage.getItem(leftWidthKey);
  const right = localStorage.getItem(rightWidthKey);
  if (left) {
    document.documentElement.style.setProperty("--left-panel-width", left);
  }
  if (right) {
    document.documentElement.style.setProperty("--right-panel-width", right);
  }
}

function initResizablePanels() {
  restorePanelWidths();
  const setup = (handle, side) => {
    let dragging = false;
    let startX = 0;
    let startWidth = 0;

    handle.addEventListener("pointerdown", (ev) => {
      if (window.matchMedia("(max-width: 1200px)").matches) {
        return;
      }
      dragging = true;
      startX = ev.clientX;
      const styles = getComputedStyle(document.documentElement);
      startWidth = parseFloat(styles.getPropertyValue(side === "left" ? "--left-panel-width" : "--right-panel-width")) || (side === "left" ? 260 : 380);
      layoutEl.classList.add("resizing");
      handle.setPointerCapture(ev.pointerId);
      ev.preventDefault();
    });

    handle.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const delta = ev.clientX - startX;
      const nextWidth = side === "left" ? startWidth + delta : startWidth - delta;
      setPanelWidth(side, nextWidth);
    });

    const stop = () => {
      if (!dragging) return;
      dragging = false;
      layoutEl.classList.remove("resizing");
    };

    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
    window.addEventListener("pointerup", stop);
  };

  setup(leftResizeHandle, "left");
  setup(rightResizeHandle, "right");
}

function initEditor() {
  ace.config.set("basePath", "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.6/");
  ace.config.set("modePath", "https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.6/");
  editor = ace.edit("editor");
  editor.setTheme("ace/theme/textmate");
  editor.session.setMode("ace/mode/text");
  editor.session.setUseWrapMode(true);
  editor.setFontSize(14);
  editor.setShowPrintMargin(false);
  editor.setOptions({
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    highlightActiveLine: true,
    showGutter: true,
    displayIndentGuides: true,
  });
}

async function apiJson(url, options) {
  const resp = await fetch(url, options);
  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (err) {
    data = { raw: text };
  }
  if (!resp.ok) {
    const detail = data && (data.detail || data.message || data.raw);
    throw new Error(detail || resp.statusText);
  }
  return data;
}

function languageModeFor(path) {
  const lower = String(path).toLowerCase();
  if (lower.endsWith(".py")) return "ace/mode/python";
  if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs") || lower.endsWith(".jsx")) return "ace/mode/javascript";
  if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "ace/mode/typescript";
  if (lower.endsWith(".json")) return "ace/mode/json";
  if (lower.endsWith(".json5")) return "ace/mode/json5";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "ace/mode/yaml";
  if (lower.endsWith(".md")) return "ace/mode/markdown";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "ace/mode/html";
  if (lower.endsWith(".css")) return "ace/mode/css";
  if (lower.endsWith(".scss")) return "ace/mode/scss";
  if (lower.endsWith(".less")) return "ace/mode/less";
  if (lower.endsWith(".sh") || lower.endsWith(".bash") || lower.endsWith(".zsh")) return "ace/mode/sh";
  if (lower.endsWith(".c") || lower.endsWith(".h") || lower.endsWith(".cc") || lower.endsWith(".cpp") || lower.endsWith(".cxx") || lower.endsWith(".hpp") || lower.endsWith(".hh") || lower.endsWith(".ipp")) return "ace/mode/c_cpp";
  if (lower.endsWith(".java")) return "ace/mode/java";
  if (lower.endsWith(".go")) return "ace/mode/golang";
  if (lower.endsWith(".rs")) return "ace/mode/rust";
  if (lower.endsWith(".cs")) return "ace/mode/csharp";
  if (lower.endsWith(".php")) return "ace/mode/php";
  if (lower.endsWith(".rb")) return "ace/mode/ruby";
  if (lower.endsWith(".lua")) return "ace/mode/lua";
  if (lower.endsWith(".swift")) return "ace/mode/swift";
  if (lower.endsWith(".kt") || lower.endsWith(".kts")) return "ace/mode/kotlin";
  if (lower.endsWith(".scala")) return "ace/mode/scala";
  if (lower.endsWith(".sql")) return "ace/mode/sql";
  if (lower.endsWith(".xml") || lower.endsWith(".svg")) return "ace/mode/xml";
  if (lower.endsWith(".toml")) return "ace/mode/toml";
  if (lower.endsWith(".ini") || lower.endsWith(".cfg") || lower.endsWith(".conf")) return "ace/mode/ini";
  if (lower.endsWith(".properties")) return "ace/mode/properties";
  if (lower.endsWith(".rs.in")) return "ace/mode/rust";
  if (lower.endsWith(".ps1")) return "ace/mode/powershell";
  if (lower.endsWith(".r")) return "ace/mode/r";
  if (lower.endsWith(".dart")) return "ace/mode/dart";
  if (lower.endsWith(".pl") || lower.endsWith(".pm")) return "ace/mode/perl";
  if (lower.endsWith(".hs")) return "ace/mode/haskell";
  if (lower.endsWith(".el")) return "ace/mode/lisp";
  if (lower.endsWith(".vue")) return "ace/mode/html";
  if (lower.endsWith(".dockerfile") || lower.endsWith("dockerfile")) return "ace/mode/dockerfile";
  if (lower.endsWith(".mk") || lower.endsWith("makefile")) return "ace/mode/makefile";
  if (lower.endsWith(".toml")) return "ace/mode/toml";
  return "ace/mode/text";
}

function sessionTitle(task) {
  let text = String(task || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "New Chat";
  }
  text = text.replace(/^https?:\/\/\S+\s*/g, "");
  text = text.replace(/^[/\\][^\s，。！？!?;；:：]+/g, "");
  const prefixes = [
    /^你好[，,]?\s*/,
    /^请你[，,]?\s*/,
    /^请帮我[，,]?\s*/,
    /^帮我[，,]?\s*/,
    /^麻烦你[，,]?\s*/,
    /^能不能[，,]?\s*/,
    /^希望你[，,]?\s*/,
    /^现在[，,]?\s*/,
    /^然后[，,]?\s*/,
  ];
  for (const pattern of prefixes) {
    text = text.replace(pattern, "");
  }
  text = text.replace(/[，。！？!?;；:：]+$/, "").trim();
  for (const sep of ["。", ".", "！", "!", "？", "?", ";", "；", "\n", "，", ",", "：", ":"]) {
    const idx = text.indexOf(sep);
    if (idx >= 6 && idx <= 22) {
      text = text.slice(0, idx);
      break;
    }
  }
  if (text.length > 18) {
    text = text.slice(0, 18).trim();
  }
  return text || "New Chat";
}

function setProjectModal(open) {
  projectModal.classList.toggle("hidden", !open);
}

function setPathModalMode(mode) {
  pathModalMode = mode;
  pathModalExtra.classList.toggle("hidden", mode === "project");
  if (mode === "project") {
    pathModalTitle.textContent = "Project Picker";
  } else if (mode === "new-file") {
    pathModalTitle.textContent = "New File";
  } else if (mode === "new-folder") {
    pathModalTitle.textContent = "New Folder";
  } else if (mode === "save-as") {
    pathModalTitle.textContent = "Save As";
  }
}

function setAuthModal(open) {
  authModal.classList.toggle("hidden", !open);
}

function setConversationMenu(open) {
  conversationMenu.classList.toggle("hidden", !open);
}

async function loadProject() {
  const data = await apiJson("/api/project");
  currentProjectRoot = data.project_root;
  projectInfo.textContent = `root: ${data.project_root}`;
}

async function openProjectModal() {
  setPathModalMode("project");
  browseCurrentPath = currentProjectRoot || "";
  browsePathInput.value = browseCurrentPath;
  await loadBrowse(browseCurrentPath);
  setProjectModal(true);
}

async function openPathDialog(mode, initialPath = "") {
  setPathModalMode(mode);
  browseCurrentPath = currentProjectRoot || "";
  browsePathInput.value = initialPath || browseCurrentPath;
  pathModalName.value = "";
  await loadBrowse(browseCurrentPath);
  setProjectModal(true);
}

async function chooseProject(path) {
  const data = await apiJson("/api/project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  currentProjectRoot = data.project_root;
  selectedFile = "";
  openFolders.clear();
  await loadProject();
  await loadTree();
  await loadSessions();
}

async function loadAuthStatus() {
  const data = await apiJson("/api/auth/status");
  currentUser = data.user || null;
  authUserEl.textContent = currentUser ? currentUser.username : "guest";
  authNoteEl.textContent = data.bootstrap_available ? "Bootstrap the local account to start using the workspace." : "Use your account to keep sessions and history.";
  if (data.authenticated) {
    setAuthModal(false);
    await loadProject();
    await loadTree();
    await loadSessions();
    return;
  }
  if (data.bootstrap_available && !localStorage.getItem(bootstrapMarker)) {
    await submitAuth("/api/auth/bootstrap", {});
    localStorage.setItem(bootstrapMarker, "1");
    return;
  }
  setAuthModal(true);
  if (data.bootstrap_available) {
    authStatusEl.textContent = "Local account available";
  } else {
    authStatusEl.textContent = "Please sign in";
  }
}

async function submitAuth(endpoint, payload) {
  const data = await apiJson(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  currentUser = data.user || null;
  authUserEl.textContent = currentUser ? currentUser.username : "guest";
  authStatusEl.textContent = `Signed in as ${currentUser ? currentUser.username : "guest"}`;
  localStorage.setItem(bootstrapMarker, "1");
  setAuthModal(false);
  await loadProject();
  await loadTree();
  await loadSessions();
}

function buildTree(entries) {
  const root = { dirs: new Map(), files: [] };
  for (const entry of entries) {
    const path = typeof entry === "string" ? entry : entry.path;
    const kind = typeof entry === "string" ? "file" : entry.kind || "file";
    const parts = path.split("/").filter(Boolean);
    let node = root;
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      if (i === parts.length - 1) {
        if (kind === "dir") {
          if (!node.dirs.has(part)) {
            node.dirs.set(part, { dirs: new Map(), files: [] });
          }
        } else {
          node.files.push(part);
        }
      } else {
        if (!node.dirs.has(part)) {
          node.dirs.set(part, { dirs: new Map(), files: [] });
        }
        node = node.dirs.get(part);
      }
    }
  }
  return root;
}

function createTreeDeleteButton(path, kind) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "tree-action";
  button.title = `Delete ${kind}`;
  button.textContent = "×";
  button.addEventListener("click", async (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (!confirm(`Delete this ${kind}?`)) {
      return;
    }
    await apiJson(`/api/path?path=${encodeURIComponent(path)}`, { method: "DELETE" });
    if (selectedFile === path || selectedFile.startsWith(`${path}/`)) {
      selectedFile = "";
      filePathInput.value = "";
      editor.setValue("", -1);
      editor.session.setMode("ace/mode/text");
    }
    for (const folder of Array.from(openFolders)) {
      if (folder === path || folder.startsWith(`${path}/`)) {
        openFolders.delete(folder);
      }
    }
    await loadTree();
  });
  return button;
}

function createTreeRefreshButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost small-btn";
  button.textContent = "Refresh";
  button.addEventListener("click", async () => {
    await loadProject();
    await loadTree();
  });
  return button;
}

function createFileButton(name, path) {
  const item = document.createElement("div");
  item.className = "file-item" + (selectedFile === path ? " active" : "");
  item.setAttribute("role", "button");
  item.tabIndex = 0;
  const label = document.createElement("span");
  label.className = "tree-label";
  label.textContent = name;
  const actions = document.createElement("span");
  actions.className = "tree-actions";
  actions.appendChild(createTreeDeleteButton(path, "file"));
  item.appendChild(label);
  item.appendChild(actions);
  item.addEventListener("click", () => openFile(path));
  item.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      openFile(path);
    }
  });
  return item;
}

function renderTreeNode(node, container, prefix = "") {
  const dirNames = Array.from(node.dirs.keys()).sort((a, b) => a.localeCompare(b));
  const fileNames = node.files.slice().sort((a, b) => a.localeCompare(b));

  dirNames.forEach((dirName) => {
    const path = prefix ? `${prefix}/${dirName}` : dirName;
    const details = document.createElement("details");
    details.dataset.path = path;
    details.open = openFolders.has(path);
    const summary = document.createElement("summary");
    summary.className = "folder-summary";
    const label = document.createElement("span");
    label.className = "tree-label";
    label.textContent = dirName;
    const actions = document.createElement("span");
    actions.className = "tree-actions";
    actions.appendChild(createTreeDeleteButton(path, "folder"));
    summary.appendChild(label);
    summary.appendChild(actions);
    details.appendChild(summary);
    const child = document.createElement("div");
    child.className = "tree-children";
    renderTreeNode(node.dirs.get(dirName), child, path);
    details.appendChild(child);
    details.addEventListener("toggle", () => {
      if (details.open) {
        openFolders.add(path);
      } else {
        openFolders.delete(path);
      }
    });
    container.appendChild(details);
  });

  fileNames.forEach((fileName) => {
    const path = prefix ? `${prefix}/${fileName}` : fileName;
    container.appendChild(createFileButton(fileName, path));
  });
}

async function loadTree() {
  const data = await apiJson("/api/tree");
  treeList.innerHTML = "";
  const entries = data.entries || (data.files || []).map((path) => ({ path, kind: "file" }));
  if (!entries.length) {
    treeList.textContent = "(empty)";
    return;
  }
  const root = buildTree(entries);
  renderTreeNode(root, treeList);
}

function renderConversationList(sessions) {
  conversationMenu.innerHTML = "";
  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "conversation-item" + (session.id === currentSession ? " active" : "");
    const title = session.title || sessionTitle(session.task);
    item.title = session.task;
    const main = document.createElement("div");
    main.className = "conversation-main";
    const titleEl = document.createElement("div");
    titleEl.className = "conversation-title";
    titleEl.textContent = title;
    titleEl.title = "Rename conversation";
    titleEl.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const next = prompt("Conversation title", session.title || title);
      if (!next) {
        return;
      }
      try {
        const updated = await apiJson(`/api/sessions/${session.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: next }),
        });
        if (currentSession === session.id) {
          activeSessionLabel.textContent = `${updated.title || next} · ${updated.project_root}`;
        }
        await loadSessions();
      } catch (err) {
        alert(err.message || String(err));
      }
    });
    const meta = document.createElement("div");
    meta.className = "session-meta";
    meta.textContent = `${session.project_root || ""} · ${session.status} · ${session.updated_at}`;
    main.appendChild(titleEl);
    main.appendChild(meta);
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "conversation-delete";
    deleteBtn.title = "Delete conversation";
    deleteBtn.textContent = "×";
    main.appendChild(deleteBtn);
    item.appendChild(main);
    item.addEventListener("click", () => {
      setConversationMenu(false);
      openSession(session.id);
    });
    deleteBtn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm("Delete this conversation?")) {
        return;
      }
      await apiJson(`/api/sessions/${session.id}`, { method: "DELETE" });
      if (currentSession === session.id) {
        currentSession = null;
        activeSessionLabel.textContent = "No conversation selected";
        statusEl.textContent = "idle";
        renderChat([]);
        if (currentEventSource) {
          currentEventSource.close();
          currentEventSource = null;
        }
      }
      await loadSessions();
    });
    conversationMenu.appendChild(item);
  });
}

async function loadSessions() {
  const data = await apiJson("/api/sessions?limit=20");
  renderConversationList(data.sessions);
}

async function openFile(path) {
  const data = await apiJson(`/api/file?path=${encodeURIComponent(path)}`);
  selectedFile = path;
  filePathInput.value = data.path;
  editor.session.setMode(languageModeFor(path));
  editor.setValue(data.content, -1);
  await loadTree();
}

async function saveFile() {
  const path = filePathInput.value.trim();
  if (!path) {
    await openPathDialog("save-as", currentProjectRoot || "");
    return;
  }
  const data = await apiJson("/api/file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content: editor.getValue() }),
  });
  alert(data.message || "saved");
  await loadTree();
}

function addChatBubble(kind, title, content) {
  const bubble = document.createElement("div");
  bubble.className = `chat-message ${kind}`;
  const label = document.createElement("div");
  label.className = "chat-label";
  label.textContent = title;
  const body = document.createElement("div");
  body.className = "chat-body";
  if (kind === "assistant" && window.marked) {
    const rendered = window.marked.parse(String(content || ""), { breaks: true, gfm: true });
    body.innerHTML = window.DOMPurify ? window.DOMPurify.sanitize(rendered) : rendered;
  } else {
    body.textContent = content;
  }
  bubble.appendChild(label);
  bubble.appendChild(body);
  chatView.appendChild(bubble);
}

function renderFoldedEvent(kind, title, content, open = false) {
  const details = document.createElement("details");
  details.className = `event-details ${kind}`;
  details.open = open;
  const summary = document.createElement("summary");
  summary.innerHTML = `<span class="event-summary-title">${escapeHtml(title)}</span><span class="event-summary-pill">${kind}</span>`;
  const body = document.createElement("div");
  body.className = "event-text";
  if (kind === "assistant" && window.marked) {
    const rendered = window.marked.parse(String(content || ""), { breaks: true, gfm: true });
    body.innerHTML = window.DOMPurify ? window.DOMPurify.sanitize(rendered) : rendered;
  } else {
    body.textContent = content || "";
  }
  details.appendChild(summary);
  details.appendChild(body);
  return details;
}

function createTurnBlock(turnIndex, running) {
  const details = document.createElement("details");
  details.className = "turn-details";
  details.open = false;
  const summary = document.createElement("summary");
  summary.className = "turn-summary";
  const state = running
    ? '<span class="thinking-spinner"></span><span>Thinking</span>'
    : '<span class="turn-done">Done</span>';
  summary.innerHTML = `<span class="turn-label">Turn ${turnIndex}</span><span class="turn-state">${state}</span>`;
  const body = document.createElement("div");
  body.className = "turn-body";
  details.appendChild(summary);
  details.appendChild(body);
  chatView.appendChild(details);
  return body;
}

function setRunning(running) {
  sendBtn.disabled = running;
  stopBtn.disabled = !running;
  sendBtn.textContent = running ? "Sending..." : "Send";
  statusEl.textContent = running ? "running" : statusEl.textContent;
}

function renderChat(events, status = "") {
  chatView.innerHTML = "";
  if (!events.length) {
    const placeholder = document.createElement("div");
    placeholder.className = "subtle";
    placeholder.textContent = "No conversation loaded.";
    chatView.appendChild(placeholder);
    return;
  }
  const running = status === "running";
  let turnIndex = 0;
  let currentTurnBody = null;
  events.forEach((event) => {
    const payload = event.payload || {};
    if (event.kind === "task") {
      turnIndex = 0;
      currentTurnBody = null;
      addChatBubble("user", "You", payload.task || "");
    } else if (event.kind === "plan") {
      chatView.appendChild(renderFoldedEvent("plan", "Plan", payload.text || "", false));
    } else if (event.kind === "turn_start") {
      turnIndex += 1;
      currentTurnBody = createTurnBlock(turnIndex, running);
    } else if (event.kind === "reasoning") {
      if (!currentTurnBody) {
        turnIndex += 1;
        currentTurnBody = createTurnBlock(turnIndex, running);
      }
      const details = document.createElement("details");
      details.className = "event-details reasoning";
      details.open = false;
      const summary = document.createElement("summary");
      summary.innerHTML = '<span class="event-summary-title">Reasoning</span><span class="event-summary-pill">hidden</span>';
      const body = document.createElement("div");
      body.className = "event-text";
      body.textContent = payload.text || "";
      details.appendChild(summary);
      details.appendChild(body);
      currentTurnBody.appendChild(details);
    } else if (event.kind === "tool_call") {
      if (!currentTurnBody) {
        turnIndex += 1;
        currentTurnBody = createTurnBlock(turnIndex, running);
      }
      currentTurnBody.appendChild(renderFoldedEvent("tool", `Tool: ${payload.name || ""}`, JSON.stringify(payload.args || {}, null, 2)));
    } else if (event.kind === "tool_result") {
      if (!currentTurnBody) {
        turnIndex += 1;
        currentTurnBody = createTurnBlock(turnIndex, running);
      }
      currentTurnBody.appendChild(renderFoldedEvent("tool", `Result: ${payload.name || ""}`, payload.output || ""));
    } else if (event.kind === "tool_error") {
      if (!currentTurnBody) {
        turnIndex += 1;
        currentTurnBody = createTurnBlock(turnIndex, running);
      }
      currentTurnBody.appendChild(renderFoldedEvent("error", `Tool error: ${payload.name || ""}`, payload.error || ""));
    } else if (event.kind === "final") {
      addChatBubble("assistant", "Assistant", payload.text || "");
    } else if (event.kind === "reflection") {
      const reflection = payload.reflection || {};
      const lines = [];
      if (reflection.summary) lines.push(reflection.summary);
      if (reflection.lessons && reflection.lessons.length) {
        lines.push("");
        lines.push("Lessons:");
        reflection.lessons.forEach((item) => lines.push(`- ${item}`));
      }
      if (reflection.next_steps && reflection.next_steps.length) {
        lines.push("");
        lines.push("Next:");
        reflection.next_steps.forEach((item) => lines.push(`- ${item}`));
      }
      chatView.appendChild(renderFoldedEvent("assistant", "Reflection", lines.join("\n")));
    } else if (event.kind === "report") {
      const report = event.payload.report || {};
      chatView.appendChild(renderFoldedEvent(
        "tool",
        "Report",
        `status: ${report.status || ""}\nturns: ${report.turns || 0}\ntool calls: ${report.tool_calls || 0}\ntool failures: ${report.tool_failures || 0}\nduration: ${report.duration_ms || 0} ms`,
      ));
    }
  });
  if (running && turnIndex === 0) {
    createTurnBlock(1, true);
  }
  chatView.scrollTop = chatView.scrollHeight;
}

async function openSession(sessionId) {
  currentSession = sessionId;
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  const data = await apiJson(`/api/sessions/${sessionId}`);
  if (data.project_root && data.project_root !== currentProjectRoot) {
    await chooseProject(data.project_root);
  }
  statusEl.textContent = data.status;
  activeSessionLabel.textContent = `${data.title || sessionTitle(data.task)} · ${data.project_root}`;
  setRunning(data.status === "running");
  renderChat(data.events.slice(), data.status);
  await loadSessions();

  currentEventSource = new EventSource(`/api/sessions/${sessionId}/events?since=${data.events.length}`);
  const events = data.events.slice();
  currentEventSource.onmessage = (ev) => {
    try {
      const obj = JSON.parse(ev.data);
      if (obj.kind === "end") {
        currentEventSource.close();
        currentEventSource = null;
        loadSessions();
        return;
      }
      events.push(obj);
      renderChat(events, statusEl.textContent);
      if (obj.kind === "final") {
        const finalStatus = obj.payload && obj.payload.text === "Terminated: stopped by user." ? "stopped" : "done";
        statusEl.textContent = finalStatus;
        setRunning(false);
        renderChat(events, finalStatus);
      }
      loadSessions();
    } catch (err) {
      console.error("sse parse", err);
    }
  };
}

async function loadBrowse(path) {
  const data = await apiJson(`/api/browse?path=${encodeURIComponent(path || "")}`);
  browseCurrentPath = data.path;
  browsePathInput.value = data.path;
  browsePathLabel.textContent = data.path;
  browseList.innerHTML = "";

  if (data.parent) {
    const up = document.createElement("button");
    up.type = "button";
    up.className = "browse-item dir";
    up.textContent = "..";
    up.addEventListener("click", async () => {
      try {
        await loadBrowse(data.parent);
      } catch (err) {
        browsePathLabel.textContent = err.message || String(err);
      }
    });
    browseList.appendChild(up);
  }

  data.entries.forEach((entry) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `browse-item ${entry.kind}`;
    item.textContent = entry.kind === "dir" ? `▸ ${entry.name}` : entry.name;
    item.addEventListener("click", async () => {
      if (entry.kind === "dir") {
        try {
          await loadBrowse(entry.path);
        } catch (err) {
          browsePathLabel.textContent = err.message || String(err);
        }
      } else {
        browsePathInput.value = entry.path;
        browsePathLabel.textContent = entry.path;
      }
    });
    browseList.appendChild(item);
  });
}

sendBtn.addEventListener("click", async () => {
  const task = taskEl.value.trim();
  if (!task) {
    alert("请输入任务描述");
    return;
  }
  try {
    setRunning(true);
    if (currentSession) {
      await apiJson(`/api/sessions/${currentSession}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: task }),
      });
      taskEl.value = "";
      await openSession(currentSession);
      return;
    }
    const data = await apiJson("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task,
        mode: document.getElementById("mode").value,
        project_root: currentProjectRoot,
      }),
    });
    taskEl.value = "";
    await openSession(data.session_id);
  } catch (err) {
    setRunning(false);
    addChatBubble("error", "Error", err.message || String(err));
  }
});

loginBtn.addEventListener("click", async () => {
  try {
    await submitAuth("/api/auth/login", {
      username: loginUsername.value.trim(),
      password: loginPassword.value,
    });
  } catch (err) {
    authStatusEl.textContent = err.message || String(err);
  }
});

registerBtn.addEventListener("click", async () => {
  try {
    await submitAuth("/api/auth/register", {
      username: registerUsername.value.trim(),
      password: registerPassword.value,
    });
  } catch (err) {
    authStatusEl.textContent = err.message || String(err);
  }
});

authBootstrapBtn.addEventListener("click", async () => {
  try {
    await submitAuth("/api/auth/bootstrap", {});
  } catch (err) {
    authStatusEl.textContent = err.message || String(err);
  }
});

logoutBtn.addEventListener("click", async () => {
  try {
    await apiJson("/api/auth/logout", { method: "POST" });
    currentUser = null;
    authUserEl.textContent = "guest";
    setAuthModal(true);
    authStatusEl.textContent = "Signed out";
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }
    renderChat([]);
  } catch (err) {
    authStatusEl.textContent = err.message || String(err);
  }
});

refreshTreeBtn.addEventListener("click", async () => {
  await loadProject();
  await loadTree();
  await loadSessions();
});

if (refreshTreeSidebarBtn) {
  refreshTreeSidebarBtn.addEventListener("click", async () => {
    await loadProject();
    await loadTree();
  });
}

openProjectBtn.addEventListener("click", openProjectModal);
closeProjectModalBtn.addEventListener("click", () => setProjectModal(false));
browseUpBtn.addEventListener("click", async () => {
  if (browseCurrentPath) {
    const parent = browseCurrentPath === "/" ? "/" : browseCurrentPath.split("/").slice(0, -1).join("/") || "/";
    try {
      await loadBrowse(parent);
    } catch (err) {
      browsePathLabel.textContent = err.message || String(err);
    }
  }
});
browseGoBtn.addEventListener("click", async () => {
  const path = browsePathInput.value.trim();
  if (!path) return;
  try {
    if (pathModalMode === "project") {
      await chooseProject(path);
      setProjectModal(false);
      return;
    }
    const name = pathModalName.value.trim();
    const joinPath = (base, child) => `${base.replace(/\/$/, "")}/${child}`.replace(/\/+/g, "/");
    if (pathModalMode === "new-file") {
      if (!name) return;
      const target = joinPath(path || currentProjectRoot || "", name);
      await apiJson("/api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: target, content: "" }),
      });
      await openFile(target);
      setProjectModal(false);
      await loadTree();
      return;
    }
    if (pathModalMode === "new-folder") {
      if (!name) return;
      const target = joinPath(path || currentProjectRoot || "", name);
      await apiJson("/api/folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: target }),
      });
      setProjectModal(false);
      await loadTree();
      return;
    }
    if (pathModalMode === "save-as") {
      if (!name) return;
      const target = joinPath(path || currentProjectRoot || "", name);
      await apiJson("/api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: target, content: editor.getValue() }),
      });
      filePathInput.value = target;
      selectedFile = target;
      setProjectModal(false);
      await loadTree();
    } else {
      await loadBrowse(path);
    }
  } catch (err) {
    browsePathLabel.textContent = err.message || String(err);
  }
});
browsePathInput.addEventListener("keydown", async (ev) => {
  if (ev.key !== "Enter") {
    return;
  }
  ev.preventDefault();
  const path = browsePathInput.value.trim();
  if (!path) return;
  try {
    await loadBrowse(path);
  } catch (err) {
    browsePathLabel.textContent = err.message || String(err);
  }
});
newFileBtn.addEventListener("click", async () => {
  await openPathDialog("new-file");
});
newFolderBtn.addEventListener("click", async () => {
  await openPathDialog("new-folder");
});
conversationToggle.addEventListener("click", () => {
  conversationMenu.classList.toggle("hidden");
});
sessionPanel.addEventListener("click", (ev) => {
  if (conversationMenu.classList.contains("hidden")) {
    return;
  }
  if (conversationToggle.contains(ev.target) || conversationMenu.contains(ev.target)) {
    return;
  }
  setConversationMenu(false);
});
newChatBtn.addEventListener("click", async () => {
  currentSession = null;
  activeSessionLabel.textContent = "No conversation selected";
  statusEl.textContent = "idle";
  taskEl.value = "";
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  renderChat([]);
  await loadSessions();
});
saveFileBtn.addEventListener("click", saveFile);
stopBtn.addEventListener("click", async () => {
  if (!currentSession) {
    return;
  }
  try {
    await apiJson(`/api/sessions/${currentSession}/stop`, { method: "POST" });
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }
    statusEl.textContent = "stopped";
    setRunning(false);
    taskEl.value = "";
    const data = await apiJson(`/api/sessions/${currentSession}`);
    renderChat(data.events.slice(), "stopped");
    await loadSessions();
  } catch (err) {
    addChatBubble("error", "Error", err.message || String(err));
  }
});
projectModal.addEventListener("click", (ev) => {
  if (ev.target === projectModal) {
    setProjectModal(false);
  }
});

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

initEditor();
initResizablePanels();
setRunning(false);
loadAuthStatus().catch((err) => {
  console.error(err);
  authStatusEl.textContent = "Failed to load auth state";
  setAuthModal(true);
});
