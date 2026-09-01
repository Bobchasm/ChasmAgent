const taskEl = document.getElementById("task");
const runBtn = document.getElementById("run-btn");
const refreshTreeBtn = document.getElementById("refresh-tree");
const saveFileBtn = document.getElementById("save-file");
const sessionView = document.getElementById("session-view");
const treeList = document.getElementById("tree-list");
const sessionList = document.getElementById("session-list");
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

let currentSession = null;
let currentEventSource = null;
let currentProjectRoot = "";
let selectedFile = "";
let editor = null;
let browseCurrentPath = "";

function initEditor() {
  editor = ace.edit("editor");
  editor.setTheme("ace/theme/monokai");
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
    details.open = true;
    const summary = document.createElement("summary");
    summary.className = "folder-summary";
    summary.textContent = dirName;
    details.appendChild(summary);
    const child = document.createElement("div");
    child.className = "tree-children";
    renderTreeNode(node.dirs.get(dirName), child, path);
    details.appendChild(child);
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

openProjectBtn.addEventListener("click", openProjectModal);
closeProjectModalBtn.addEventListener("click", () => setProjectModal(false));
browseUpBtn.addEventListener("click", async () => {
  if (browseCurrentPath) {
    const parent = browseCurrentPath === "/" ? "/" : browseCurrentPath.split("/").slice(0, -1).join("/") || "/";
    await loadBrowse(parent);
  }
});
browseGoBtn.addEventListener("click", async () => {
  const path = browsePathInput.value.trim();
  if (!path) return;
  await loadBrowse(path);
});
useProjectBtn.addEventListener("click", async () => {
  const path = browsePathInput.value.trim();
  if (!path) return;
  await chooseProject(path);
  setProjectModal(false);
});
saveFileBtn.addEventListener("click", saveFile);
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
loadProject().then(loadTree).then(loadSessions).catch((err) => {
  console.error(err);
  projectInfo.textContent = "failed to load project";
});
