const taskEl = document.getElementById("task");
const runBtn = document.getElementById("run-btn");
const refreshTreeBtn = document.getElementById("refresh-tree");
const saveFileBtn = document.getElementById("save-file");
const sessionView = document.getElementById("session-view");
const treeList = document.getElementById("tree-list");
const sessionList = document.getElementById("session-list");
const statusEl = document.getElementById("status");
const filePathInput = document.getElementById("file-path");
const fileContentEl = document.getElementById("file-content");
const projectPathInput = document.getElementById("project-path");
const openProjectBtn = document.getElementById("open-project");
const projectInfo = document.getElementById("project-info");

let currentSession = null;
let currentEventSource = null;
let currentProjectRoot = "";
let selectedFile = "";

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

async function loadProject() {
  const data = await apiJson("/api/project");
  currentProjectRoot = data.project_root;
  projectPathInput.value = currentProjectRoot;
  projectInfo.textContent = `root: ${data.project_root}`;
}

async function openProject() {
  const path = projectPathInput.value.trim();
  if (!path) {
    alert("请输入项目路径");
    return;
  }
  await apiJson("/api/project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  await loadProject();
  await loadTree();
  await loadSessions();
}

async function loadTree() {
  const data = await apiJson("/api/tree");
  treeList.innerHTML = "";
  if (!data.files.length) {
    treeList.textContent = "(empty)";
    return;
  }
  data.files.forEach((file) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "file-item" + (file === selectedFile ? " active" : "");
    item.textContent = file;
    item.addEventListener("click", () => openFile(file));
    treeList.appendChild(item);
  });
}

async function loadSessions() {
  const data = await apiJson("/api/sessions?limit=20");
  sessionList.innerHTML = "";
  data.sessions.forEach((session) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-item" + (session.id === currentSession ? " active" : "");
    item.innerHTML = `<div>${escapeHtml(session.task.slice(0, 60))}</div><div class="session-meta">${escapeHtml(session.project_root || "")} · ${session.status} · ${session.updated_at}</div>`;
    item.addEventListener("click", () => openSession(session.id));
    sessionList.appendChild(item);
  });
}

async function openFile(path) {
  const data = await apiJson(`/api/file?path=${encodeURIComponent(path)}`);
  selectedFile = path;
  filePathInput.value = data.path;
  fileContentEl.value = data.content;
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
    body: JSON.stringify({ path, content: fileContentEl.value }),
  });
  alert(data.message || "saved");
  await loadTree();
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
  const data = await apiJson(`/api/sessions/${sessionId}`);
  statusEl.textContent = data.status;
  renderSessionEvents(data.events.slice());
  await loadSessions();

  currentEventSource = new EventSource(`/api/sessions/${sessionId}/events`);
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
  const data = await apiJson("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      mode: document.getElementById("mode").value,
      project_root: currentProjectRoot,
    }),
  });
  await openSession(data.session_id);
});

refreshTreeBtn.addEventListener("click", async () => {
  await loadProject();
  await loadTree();
  await loadSessions();
});

openProjectBtn.addEventListener("click", openProject);
saveFileBtn.addEventListener("click", saveFile);

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

loadProject().then(loadTree).then(loadSessions).catch((err) => {
  console.error(err);
  projectInfo.textContent = "failed to load project";
});
