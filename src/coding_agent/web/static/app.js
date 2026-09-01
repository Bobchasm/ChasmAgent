const taskEl = document.getElementById("task");
const runBtn = document.getElementById("run-btn");
const refreshTreeBtn = document.getElementById("refresh-tree");
const saveFileBtn = document.getElementById("save-file");
const sessionView = document.getElementById("session-view");
const treeView = document.getElementById("tree-view");
const sessionList = document.getElementById("session-list");
const statusEl = document.getElementById("status");
const filePathInput = document.getElementById("file-path");
const fileContentEl = document.getElementById("file-content");

let currentSession = null;
let currentEventSource = null;

async function loadTree() {
  const resp = await fetch("/api/tree");
  if (!resp.ok) return;
  const data = await resp.json();
  treeView.textContent = data.files.join("\n");
}

async function loadSessions() {
  const resp = await fetch("/api/sessions?limit=20");
  if (!resp.ok) return;
  const data = await resp.json();
  sessionList.innerHTML = "";
  data.sessions.forEach((session) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-item" + (session.id === currentSession ? " active" : "");
    item.innerHTML = `<div>${escapeHtml(session.task.slice(0, 60))}</div><div class="session-meta">${session.status} · ${session.updated_at}</div>`;
    item.addEventListener("click", () => openSession(session.id));
    sessionList.appendChild(item);
  });
}

async function openFile(path) {
  const resp = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
  if (!resp.ok) {
    alert("无法打开文件: " + path);
    return;
  }
  const data = await resp.json();
  filePathInput.value = data.path;
  fileContentEl.value = data.content;
}

async function saveFile() {
  const path = filePathInput.value.trim();
  if (!path) {
    alert("请先选择或填写文件路径");
    return;
  }
  const resp = await fetch("/api/file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content: fileContentEl.value }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    alert("保存失败: " + (err.detail || resp.statusText));
    return;
  }
  const data = await resp.json();
  alert(data.message || "saved");
}

function bindTreeClick() {
  treeView.addEventListener("click", async (ev) => {
    const text = window.getSelection().toString() || ev.target.textContent.trim();
    const path = text.trim();
    if (!path) return;
    await openFile(path);
  });
}

function renderSessionEvents(events) {
  sessionView.textContent = JSON.stringify(events, null, 2);
}

async function openSession(sessionId) {
  currentSession = sessionId;
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  const resp = await fetch(`/api/sessions/${sessionId}`);
  if (!resp.ok) return;
  const data = await resp.json();
  statusEl.textContent = data.status;
  const events = data.events.slice();
  renderSessionEvents(events);
  await loadSessions();

  currentEventSource = new EventSource(`/api/sessions/${sessionId}/events`);
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
      renderSessionEvents(events);
      if (obj.kind === "final") {
        statusEl.textContent = "done";
      }
      loadSessions();
    } catch (err) {
      console.error("sse parse", err);
    }
  };
}

runBtn.addEventListener("click", async () => {
  const task = taskEl.value.trim();
  if (!task) {
    alert("请输入任务描述");
    return;
  }
  statusEl.textContent = "starting";
  const resp = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, mode: document.getElementById("mode").value }),
  });
  const data = await resp.json();
  await openSession(data.session_id);
});

refreshTreeBtn.addEventListener("click", async () => {
  await loadTree();
  await loadSessions();
});

saveFileBtn.addEventListener("click", saveFile);

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

bindTreeClick();
loadTree();
loadSessions();
