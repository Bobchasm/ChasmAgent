const taskEl = document.getElementById("task");
const runBtn = document.getElementById("run-btn");
const refreshBtn = document.getElementById("refresh-btn");
const sessionView = document.getElementById("session-view");
const resultView = document.getElementById("result-view");
const treeView = document.getElementById("tree-view");
const statusEl = document.getElementById("status");

let currentSession = null;

async function loadTree() {
  const resp = await fetch("/api/tree");
  const data = await resp.json();
  treeView.textContent = [data.root, "", ...data.files].join("\n");
}

async function pollSession() {
  if (!currentSession) return;
  const resp = await fetch(`/api/sessions/${currentSession}`);
  if (!resp.ok) return;
  const data = await resp.json();
  statusEl.textContent = data.status;
  sessionView.textContent = JSON.stringify(data.events, null, 2);
  resultView.textContent = data.result || "";
}

runBtn.addEventListener("click", async () => {
  const task = taskEl.value.trim();
  if (!task) return;
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

refreshBtn.addEventListener("click", async () => {
  await loadTree();
  await pollSession();
});

loadTree();
setInterval(pollSession, 1200);
