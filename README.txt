仓库地址：git@github.com:Bobchasm/ChasmAgent.git

运行方式：
1. 安装 Miniconda 后执行 `bash scripts/bootstrap.sh`
2. `conda activate coding-agent`
3. 复制 `.env.example` 为 `.env`，填写 `OPENAI_API_KEY` 或 `DASHSCOPE_API_KEY`
4. 启动 Web 端：`chasm-agent serve --reload`
5. 命令行单次任务：`chasm-agent run "你的编程任务"`
6. 交互式终端：`chasm-agent chat`

环境变量：
DashScope 推荐：`CHASM_PROVIDER=dashscope`、`DASHSCOPE_API_KEY`、`OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`OPENAI_MODEL=qwen3.8-flash`
可选：`CHASM_ENABLE_THINKING=1`、`CHASM_WORKSPACE`、`CHASM_LOG_LEVEL`、`CHASM_MAX_TURNS`
也兼容 `OPENAI_API_KEY` + OpenAI/OpenAI-compatible 网关。

特色：
本项目不依赖现成 agent 框架，核心逻辑包括本地工具执行、上下文管理、循环终止、错误处理、日志、记忆、会话历史和 Web 界面。
支持读文件、写文件、文本替换、目录浏览、文本搜索、命令执行。
Web 界面提供任务输入、会话状态、会话历史、workspace 视图、文件编辑和结果流。
