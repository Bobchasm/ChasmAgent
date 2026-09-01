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
const useProjectBtn = document.getElementById("use-project");
const browsePathInput = document.getElementById("browse-path");
const browseList = document.getElementById("browse-list");
const browsePathLabel = document.getElementById("browse-path-label");
const conversationToggle = document.getElementById("conversation-toggle");
const conversationMenu = document.getElementById("conversation-menu");
const newChatBtn = document.getElementById("new-chat");
const activeSessionLabel = document.getElementById("active-session-label");
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

let currentSession = null;
let currentEventSource = null;
let currentProjectRoot = "";
let selectedFile = "";
let editor = null;
let browseCurrentPath = "";
let currentUser = null;
const openFolders = new Set();

function initEditor() {
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
  if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "ace/mode/javascript";
  if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "ace/mode/typescript";
  if (lower.endsWith(".json")) return "ace/mode/json";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "ace/mode/yaml";
  if (lower.endsWith(".md")) return "ace/mode/markdown";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "ace/mode/html";
  if (lower.endsWith(".css")) return "ace/mode/css";
  if (lower.endsWith(".sh")) return "ace/mode/sh";
  if (lower.endsWith(".toml")) return "ace/mode/toml";
  return "ace/mode/text";
}

function setProjectModal(open) {
  projectModal.classList.toggle("hidden", !open);
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
  browseCurrentPath = currentProjectRoot || "";
  browsePathInput.value = browseCurrentPath;
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

function buildTree(files) {
  const root = { dirs: new Map(), files: [] };
  for (const file of files) {
    const parts = file.split("/").filter(Boolean);
    let node = root;
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      if (i === parts.length - 1) {
        node.files.push(part);
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

function createFileButton(name, path) {
  const item = document.createElement("button");
  item.type = "button";
  item.className = "file-item" + (selectedFile === path ? " active" : "");
  item.textContent = name;
  item.addEventListener("click", () => openFile(path));
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
    summary.textContent = dirName;
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
  if (!data.files.length) {
    treeList.textContent = "(empty)";
    return;
  }
  const root = buildTree(data.files);
  renderTreeNode(root, treeList);
}

function renderConversationList(sessions) {
  conversationMenu.innerHTML = "";
  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "conversation-item" + (session.id === currentSession ? " active" : "");
    item.innerHTML = `<div class="conversation-main"><div>${escapeHtml(session.task.slice(0, 60))}</div><div class="session-meta">${escapeHtml(session.project_root || "")} · ${session.status} · ${session.updated_at}</div></div><button type="button" class="conversation-delete" title="Delete conversation">×</button>`;
    item.addEventListener("click", () => {
      setConversationMenu(false);
      openSession(session.id);
    });
    const deleteBtn = item.querySelector(".conversation-delete");
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
    alert("请先选择或填写文件路径");
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

function addThinkingDetails(content, active = false) {
  const details = document.createElement("details");
  details.className = "thought-details";
  const summary = document.createElement("summary");
  summary.innerHTML = `<span class="thinking-state">${active ? '<span class="thinking-spinner"></span>' : ""}<span>Thinking</span></span>`;
  const body = document.createElement("div");
  body.className = "thought-text";
  body.textContent = content || "";
  details.appendChild(summary);
  details.appendChild(body);
  chatView.appendChild(details);
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
  let sawActiveTurn = false;
  events.forEach((event) => {
    const payload = event.payload || {};
    if (event.kind === "task") {
      addChatBubble("user", "You", payload.task || "");
    } else if (event.kind === "turn_start") {
      sawActiveTurn = true;
      const indicator = document.createElement("div");
      indicator.className = "thinking-badge";
      if (running) {
        indicator.innerHTML = '<span class="thinking-spinner"></span><span>Thinking</span>';
      } else {
        indicator.textContent = "Done";
        indicator.classList.add("done");
      }
      chatView.appendChild(indicator);
    } else if (event.kind === "reasoning") {
      addThinkingDetails(payload.text || "", running);
    } else if (event.kind === "tool_call") {
      addChatBubble("tool", `Tool: ${payload.name || ""}`, JSON.stringify(payload.args || {}, null, 2));
    } else if (event.kind === "tool_result") {
      addChatBubble("tool", `Result: ${payload.name || ""}`, payload.output || "");
    } else if (event.kind === "tool_error") {
      addChatBubble("error", `Tool error: ${payload.name || ""}`, payload.error || "");
    } else if (event.kind === "final") {
      addChatBubble("assistant", "Assistant", payload.text || "");
    }
  });
  if (running && !sawActiveTurn) {
    const indicator = document.createElement("div");
    indicator.className = "thinking-badge";
    indicator.innerHTML = '<span class="thinking-spinner"></span><span>Thinking</span>';
    chatView.appendChild(indicator);
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
  activeSessionLabel.textContent = `${data.task} · ${data.project_root}`;
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
    up.addEventListener("click", () => loadBrowse(data.parent));
    browseList.appendChild(up);
  }

  data.entries.forEach((entry) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `browse-item ${entry.kind}`;
    item.textContent = entry.kind === "dir" ? `▸ ${entry.name}` : entry.name;
    item.addEventListener("click", () => {
      if (entry.kind === "dir") {
        loadBrowse(entry.path);
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
    await loadBrowse(path);
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
useProjectBtn.addEventListener("click", async () => {
  const path = browsePathInput.value.trim();
  if (!path) return;
  await chooseProject(path);
  setProjectModal(false);
});
conversationToggle.addEventListener("click", () => {
  conversationMenu.classList.toggle("hidden");
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
setRunning(false);
loadAuthStatus().catch((err) => {
  console.error(err);
  authStatusEl.textContent = "Failed to load auth state";
  setAuthModal(true);
});
