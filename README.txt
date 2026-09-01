仓库地址：git@github.com:Bobchasm/ChasmAgent.git

运行方式：
1. 安装 Miniconda 后执行 `bash scripts/bootstrap.sh`
2. `conda activate coding-agent`
3. 复制 `.env.example` 为 `.env`，填写 `OPENAI_API_KEY`
4. 启动 Web 端：`chasm-agent serve --reload`
5. 命令行模式：`chasm-agent run "你的编程任务"`

环境变量：
`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`
可选：`CHASM_WORKSPACE`、`CHASM_LOG_LEVEL`、`CHASM_MAX_TURNS`

特色：
本项目不依赖现成 agent 框架，核心逻辑包括本地工具执行、上下文管理、循环终止、错误处理、日志和 Web 界面。
支持读文件、写文件、文本替换、目录浏览、文本搜索、命令执行。
Web 界面提供任务输入、会话状态、workspace 视图和结果展示。

