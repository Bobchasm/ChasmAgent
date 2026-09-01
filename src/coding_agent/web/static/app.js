const taskEl = document.getElementById("task");
const runBtn = document.getElementById("run-btn");
const refreshTreeBtn = document.getElementById("refresh-tree");
const saveFileBtn = document.getElementById("save-file");
const sessionView = document.getElementById("session-view");
const treeView = document.getElementById("tree-view");
const statusEl = document.getElementById("status");
const filePathInput = document.getElementById("file-path");
const fileContentEl = document.getElementById("file-content");

let currentSession = null;

async function loadTree() {
  const resp = await fetch("/api/tree");
  const data = await resp.json();
  treeView.textContent = data.files.join("\n");
}

treeView.addEventListener("click", async (ev) => {
  const line = window.getSelection().toString() || ev.target.textContent.trim();
  const path = line.trim();
  if (!path) return;
  await openFile(path);
});

async function openFile(path) {
  const resp = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
  if (!resp.ok) {
    alert('无法打开文件: ' + path);
    return;
  }
  const data = await resp.json();
  filePathInput.value = data.path;
  fileContentEl.value = data.content;
}

async function saveFile() {
  const path = filePathInput.value.trim();
  if (!path) return alert('请先选择或填写文件路径');
  const resp = await fetch('/api/file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content: fileContentEl.value }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    alert('保存失败: ' + (err.detail || resp.statusText));
    return;
  }
  const j = await resp.json();
  alert(j.message || 'saved');
}

async function pollSession() {
  if (!currentSession) return;
  const resp = await fetch(`/api/sessions/${currentSession}`);
  if (!resp.ok) return;
  const data = await resp.json();
  statusEl.textContent = data.status;
  sessionView.textContent = JSON.stringify(data.events, null, 2);
}

runBtn.addEventListener("click", async () => {
  const task = taskEl.value.trim();
  if (!task) return alert('请输入任务描述');
  statusEl.textContent = "starting";
  const resp = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, mode: document.getElementById("mode").value }),
  });
  const data = await resp.json();
  currentSession = data.session_id;
  await pollSession();
});

refreshTreeBtn.addEventListener("click", async () => {
  await loadTree();
});

saveFileBtn.addEventListener('click', saveFile);

loadTree();
setInterval(pollSession, 1200);
