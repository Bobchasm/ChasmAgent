# Chasm Agent

## 1 简介

Chasm Agent 是一个本地可运行的 agent IDE，重点在于打通一条完整的 coding agent 链路：

用户选择本地项目 -> 输入开发任务 -> 模型规划与调用工具 -> 本地执行文件/命令操作 -> 结果回写 -> 会话持久化 -> 继续多轮迭代。

面向真实开发工作流：

- 是否能稳定访问本地工作区
- 是否能把模型输出转成可执行动作
- 是否能记录上下文、历史和记忆
- 是否能在 Web 页面里像 IDE 一样工作
- 是否能调试、恢复、继续任务

系统具备：

- 本地项目选择与目录浏览
- 文件树、文件打开、编辑、保存
- 文件和目录创建、删除
- agent 多轮工具调用
- 会话隔离和持久化
- 本地账号登录
- Markdown 渲染的对话展示
- Thinking / Tool / Report 折叠展示
- 左右栏拖拽缩放
- 历史会话与当前项目绑定

---

## 2 启动运行

### 2.1 环境

当前项目在 WSL / Linux 下运行。

如果是 conda 环境，可以参考：

```bash
conda env create -f environment.yml
conda activate coding-agent
pip install -e .
```

### 2.2 模型配置

DashScope / 百炼：

```bash
export CHASM_PROVIDER=dashscope
export DASHSCOPE_API_KEY=APIKEY
export DASHSCOPE_MODEL=qwen3.8-flash
```

OpenAI 兼容接口：

```bash
export OPENAI_API_KEY=APIKEY
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-5
```

### 2.3 启动 Web IDE

```bash
bash scripts/dev.sh
```

使用方式：

1. Web 端

终端启动:
```bash
chasm-agent serve --reload --host 0.0.0.0 --port 8000
```

浏览器访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

2. 运行单次任务：

```bash
chasm-agent run "你的编程任务"
```

3. 打开交互终端：

```bash
chasm-agent chat
```

---

## 3 总体架构

### 3.1 Web 服务层

核心入口 `src/coding_agent/server.py`。

负责：

- FastAPI 路由
- 登录认证
- 项目工作区切换
- 文件浏览和读写 API
- 会话创建、查询、停止、删除
- SSE 推送 agent 事件
- 连通 `CodingAgent`、`SessionStore`、`ToolRegistry`

### 3.2 Agent 编排层

核心逻辑 `src/coding_agent/agent.py`。

负责：

- 执行 Planning
- 执行 Reasoning
- 完成 Grounding 和 Acting
- 维护 Conversation Context
- 执行 Termination 判断
- 生成 Run Report
- 把每个阶段转成结构化 Agent Event

### 3.3 工具层

`src/coding_agent/tools/` 定义 Agent 的 Action Space。

定义了 agent 可执行的动作：

- `read_file`
- `write_file`
- `replace_text`
- `make_directory`
- `delete_path`
- `list_files`
- `search_text`
- `run_command`

### 3.4 记忆与存储层

`src/coding_agent/memory.py` 和 `src/coding_agent/storage.py` 提供长期持久化。

存储：

- 用户和登录态
- 项目路径
- session
- session 消息
- session 事件
- 会话级 memory 文件

### 3.5 前端 IDE 层

`src/coding_agent/web/static/app.js` + `app.css` + `templates/index.html`

把系统做成类 IDE 体验：

- 左侧文件树
- 中间编辑器
- 右侧 agent 对话
- 项目选择弹窗
- 会话列表
- 折叠的 Reasoning Trace 和 Tool Trace

---

## 4 技术栈

### 4.1 后端

- Python 3.11+
- FastAPI
- Uvicorn
- SQLite
- OpenAI Python SDK
- Typer
- Rich

### 4.2 前端

- 原生 HTML / CSS / JavaScript
- Ace Editor
- Marked
- DOMPurify

### 4.3 测试

- pytest

### 4.4 模型接入

系统默认支持 OpenAI 兼容接口，也支持 DashScope 的兼容模式。

配置入口在 `src/coding_agent/config.py`：

```python
api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
default_model = "qwen3.8-flash" if provider == "dashscope" else "gpt-5"
```

这意味着可以切换：

- OpenAI 官方接口
- 阿里云百炼 / DashScope 兼容接口

---

## 5 Agent 核心执行链路

### 5.1 设计目标

采用典型的 agentic workflow：

1. Planning：根据用户任务和历史上下文生成短计划
2. Reasoning：结合当前对话状态判断下一步动作
3. Grounding：把自然语言意图映射到本地工具调用
4. Acting：执行文件读写、搜索、目录操作或命令运行
5. Observation：把工具结果回填给模型作为下一轮输入
6. Reflection：任务结束后生成总结、经验和后续建议
7. Termination：根据完成状态、最大轮数、错误和用户停止信号结束循环

这条链路对应 OS Agent / Coding Agent 中常见的 `Planning -> Grounding -> Action -> Observation -> Reflection` 模式。

### 5.2 Agent Loop

核心在 `CodingAgent.run()`：

```python
for turn in range(1, self.max_turns + 1):
    if self.should_stop and self.should_stop():
        ...
    state.compact(self.max_history_messages)
    self._emit("turn_start", turn=turn, messages=len(state.messages))
    response = self.llm.complete(state.messages, self.tools.specs())
```

- 设置 maximum turns，控制 Agent Loop 的执行边界
- 每轮前压缩 Conversation Context，控制上下文规模
- 每轮通过 Agent Event 输出 Reasoning Trace 和执行状态

### 5.3 Planning 阶段

系统支持一个轻量 Planner。相关逻辑在 `agent.py` 的 `_plan_task()`。

如果开启 planning，会先向模型发一个规划提示词，要求只返回 JSON：

```python
def planner_prompt() -> str:
    return """
    You are a planning agent for a local coding workspace.
    Create a short actionable plan before editing code.
    Return only JSON with keys:
    - goal
    - steps
    - risks
    - success_criteria
    """
```

Planner 在 Agent Loop 开始前提供短计划，包含 Goal、Steps、Risks 和 Success Criteria。

### 5.4 Reflection 阶段

任务完成后进入 Reflection：

```python
def reflection_prompt() -> str:
    return """
    You are a review agent for a local coding workspace.
    Summarize the outcome after execution.
    Return only JSON with keys:
    - summary
    - lessons
    - next_steps
    - files
    - status
    """
```

Reflection 的输出用于：

- 任务完成后自动总结
- 把经验变成可复用信息
- 给下次会话提供更稳定的上下文

### 5.5 Termination 条件

当前 Termination 条件主要包括：

- 达到 maximum turns
- LLM invocation error
- User Stop Signal
- Tool failure 达到恢复边界

这些条件用于控制 Agent Loop 的稳定退出。

---

## 6 工具系统设计

### 6.1 Tool Schema 与 Action Space

所有工具统一在 `src/coding_agent/tools/registry.py` 中声明 Tool Schema，再分发到具体实现。

这样做的好处是：

- LLM 看到统一的 Action Space 描述
- Acting 阶段在本地 Python 中完成
- 新增或删除工具不会改变 Agent Loop

### 6.2 文件系统工具

`src/coding_agent/tools/filesystem.py` 现在包括：

- `read_file`
- `write_file`
- `replace_text`
- `make_directory`
- `delete_path`
- `list_files`
- `search_text`

其中删除是递归安全删除：

```python
def delete_path(root: Path, path: str) -> str:
    target = ensure_within_root(root, path)
    if target == root:
        raise ValueError("refusing to delete workspace root")
    if not target.exists():
        raise FileNotFoundError(path)
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()
```

这体现了两个原则：

- 允许删非空目录，满足真实 IDE 场景
- 所有删除都限制在 workspace 内，防止越界

### 6.3 Acting：命令工具

`run_command` 允许 agent 在工作区里运行本地命令。

Acting 阶段通常需要连续完成多个动作：

- 跑测试
- 看报错
- 修复
- 再跑一遍

### 6.4 Observation：Agent Event 回填

每个 Tool Call 和 Tool Result 都会转成结构化 Agent Event，构成 Tool Trace：

- `tool_call`
- `tool_result`
- `tool_error`

前端据此折叠显示 Tool Trace，后端也可以据此完成日志分析和运行复盘。

---

## 7 Grounding 与模型输出解析

### 7.1 Grounding 的必要性

兼容模型可能采用多种方式表达 Action。

有些模型会：

- 返回标准 tool_calls
- 将 Tool Call 写入文本
- 在文本中混合 Reasoning 内容

`src/coding_agent/llm.py` 负责完成输出归一化，将模型表达映射到统一的 Tool Call 结构。

### 7.2 关键逻辑

```python
if not getattr(message, "tool_calls", None):
    parsed_calls = self._parse_tool_calls_from_text(content)
    if parsed_calls:
        ...
```

该 Grounding 过程包括：

- 接收标准 Tool Call
- 解析非标准文本格式
- 提取 Reasoning 内容并形成独立事件

这对你后面答辩很有帮助，因为可以讲成“做了模型输出鲁棒性适配”。

---

## 8 Context 与 Memory 管理

### 8.1 三层 Context

当前系统采用三层 Context 结构：

1. Current Session Context：当前 session messages
2. Persistent Memory：会话级 memory 文件
3. Historical Context：历史 session 检索 archive

### 8.2 Persistent Memory

`src/coding_agent/memory.py` 里的 `MemoryStore` 用本地 JSON 保存：

- summary
- facts
- recent_tasks
- touched_files

这些信息为后续 Reasoning 提供持续上下文：

- 最近碰过哪些文件
- 这次任务做了什么
- 之后重新打开同一项目时应该从哪续

### 8.3 Historical Context Retrieval

`MemoryArchive` 会从 SQLite 中检索同用户、同项目的历史 Session，按关键词生成 Historical Context。采用轻量关键词检索。

### 8.4 Session Isolation

每个 session 都绑定自己的：

- project_root
- messages
- events
- memory namespace

`new chat` 会创建独立的 Session Context，Reasoning 不会读取其他会话的私有上下文。

---

## 9 Session State 与持久化

### 9.1 SQLite 作为 Session State 中心

`src/coding_agent/storage.py` 是整个系统的状态库。

表包括：

- `users`
- `auth_sessions`
- `projects`
- `sessions`
- `session_messages`
- `session_events`


### 9.2 session 标题

系统自动为会话生成短标题。

`server.py` 里有一个简单的标题提取器：

```python
def _session_title(task: str) -> str:
    text = " ".join((task or "").split())
    ...
    if len(text) > 26:
        text = text[:26].rstrip()
    return text or "New Chat"
```

创建 session 时会写入这个短标题，长任务原文仍然保存在 `task` 字段里。

### 9.3 Session State 持久化

创建 session 后，服务端会把：

- 任务
- 标题
- 项目路径
- 消息
- 事件

都写进数据库，所以刷新页面或重启进程不会丢。

---

## 10 Web IDE 前端

### 10.1 三栏布局

界面是明确按 IDE 思路做的：

- 左侧：文件树
- 中间：Ace Editor
- 右侧：agent 对话

这比“聊天页 + 按钮”更适合 coding agent。

### 10.2 文件树

文件树从项目根开始渲染，子目录默认收起，点击才展开。

支持：

- 刷新
- 新建文件
- 新建目录
- 删除文件
- 删除空目录
- 删除非空目录

### 10.3 编辑器

编辑器使用 Ace Editor，并根据文件后缀切换语法模式。

目前支持的常见类型包括：

- Python
- JavaScript / TypeScript
- C / C++ 头文件与源文件
- Java
- Go
- Rust
- HTML / CSS / Markdown
- Shell
- YAML / JSON / TOML
- SQL
- 以及若干常见配置类文件

### 10.4 Agent Interaction Panel

Agent Interaction Panel 支持：

- Markdown 渲染
- Reasoning Trace 折叠
- Tool Trace 折叠
- Run Report 折叠
- 会话列表
- 删除会话
- 新建对话

现在对话显示会把非核心信息折叠起来，主对话流更干净。

### 10.5 Reasoning Trace 与 Turn

前端已经把每一轮封装成：

- `Turn 1`
- `Turn 2`
- `Turn 3`

每个 Turn 内部再展开：

- Reasoning
- Tool Call
- Observation / Tool Result
- Tool Error

这比单独丢一个“Thinking”小点更适合解释 agent 的循环结构，也解决了之前重复转圈的问题。

---

## 11 核心功能

1. 本地可执行的 agent IDE

系统包含的不只是聊天，还把：

- 文件浏览
- 编辑器
- 工具调用
- 会话管理
- 持久化记忆

做成了完整闭环。

2. 分层记忆

这里保存的内容不止聊天历史，还包括：

- session 记忆
- 历史检索
- 项目上下文

更贴近真实 coding agent 的记忆结构。

3. 结构化 Agent Event Stream

把 Reasoning Trace、Tool Trace 和 Run Report 都转成 Agent Event，再由前端分层展示。

4. 模型输出鲁棒适配

对 OpenAI 兼容接口做了额外解析，能适应不同厂商的输出差异。

5. 安全工作区边界

所有文件操作都限制在工作区内部，删除目录也必须经过边界校验。

---


### 优化方向

- 用向量检索替代轻量关键词检索
- 给工具执行增加更细的权限控制
- 增加 diff 级别补丁编辑
- 把 Planning、Acting、Reflection 做成更显式的多智能体协作
- 增加任务级评测与成功率统计
