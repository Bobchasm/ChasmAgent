# Chasm Agent

仓库地址：[https://github.com/Bobchasm/ChasmAgent.git](https://github.com/Bobchasm/ChasmAgent.git)

## 快速运行
1. 安装 Miniconda。
2. 进入项目根目录，执行 `bash scripts/bootstrap.sh`。
3. 激活环境：`conda activate coding-agent`。

## 模型配置
1. 复制 `.env.example` 为 `.env`。
2. 在环境变量中填写 `OPENAI_API_KEY` 或 `DASHSCOPE_API_KEY`。
3. 如使用 DashScope 兼容接口，设置 `CHASM_PROVIDER=dashscope`，`OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`。

## 启动方式
1. 启动 Web 端：`chasm-agent serve --reload --host 0.0.0.0 --port 8000`，浏览器访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
2. 运行单次任务：`chasm-agent run "你的编程任务"`
3. 打开交互终端：`chasm-agent chat`

## 功能说明
1. 本地 coding agent 工作流：`plan -> reason -> tool -> observe -> done`
2. 文件读写、文本替换、目录浏览、文本搜索、命令执行
3. SQLite 持久化的用户、会话、消息、事件和记忆
4. Web IDE 界面、文件树、代码编辑器和 Markdown 对话渲染
5. OpenAI 兼容接口和 DashScope 兼容接口
