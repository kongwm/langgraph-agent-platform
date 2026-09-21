# P10：LangGraph 企业级 Agent 平台

与 `platform/backend`（手写编排，P1-P8.5）并列的第二个平台：**全 LangGraph 实现**，
目标是看企业级项目长什么样——重点不在"能不能对话"（P8 已证明两边都能），
而在框架真正擅长的部分：**持久化状态、原生中断、多智能体、工程化基建**。

## 阶段路线（详见 docs/project-plan.md P10 章节）

| 阶段 | 内容 | 状态 |
|---|---|---|
| P10.1 | 骨架：pydantic-settings 分层配置 / structlog JSON 日志 / SSE 契约（同 backend，前端零改动）/ 最小 agent 图 | ✅ |
| P10.2 | AsyncPostgresSaver 持久化（独立 meta 库）/ interrupt() HITL / time-travel | ✅（checkpointer 部分；HITL/回放待续） |
| P10.3 | supervisor 多智能体（手写 StateGraph + subgraph） | 🔜 |
| P10.4 | API key 鉴权 + 多用户 thread 归属隔离 | 🔜 |
| P10.5 | OTel 自建 trace / guardrails 图内前置节点 / 评测流水线 | 🔜 |

## 运行

```bash
# 1. 数据库（PG 17，端口 25432，与 backend 的 15432 互不影响）
docker compose up -d

# 2. 依赖（USTC 镜像 + no_proxy，网络坑见 docs）
no_proxy='*' .venv/bin/pip install -i https://pypi.mirrors.ustc.edu.cn/simple -r requirements.txt

# 3. 配置
cp .env.example .env   # 填 ANTHROPIC_API_KEY（GLM 兼容端点）

# 4. 起服务（占 8000 端口 —— 和 backend 互斥，跑这个时停掉 backend）
.venv/bin/uvicorn app.main:app --reload --port 8000

# 5. 测试（默认跳过需要 PG 的 integration 标记）
.venv/bin/pytest
```

## 快速验证

```bash
curl http://127.0.0.1:8000/api/healthz

# 流式对话（SSE 契约同 backend）
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "demo", "content": "现在几点了？"}'

# 持久化验证：杀进程重启后，同 conversation_id 再问"刚才我说了什么"
```

## 结构（分层）

```
app/
├── core/      基建：config(pydantic-settings) / logging(structlog) / errors
├── api/       路由：chat(SSE) / threads(待续)
├── agents/    LangGraph：state / graph 装配（checkpointer+llm 参数化注入）
├── llm/       provider（monkeypatch 绕系统代理，P8 成果搬运）
├── tools/     @tool 装饰器风格工具
└── infra/     sse 封装（契约锚点）
tests/
├── unit/      配置校验
├── graphs/    图逻辑（FakeLLM + MemorySaver，零网络）
└── contract/  SSE 契约（ASGITransport 直连 app）
```

## 与 backend 的关键差异（学习对照点）

| 维度 | backend（手写） | 本仓（LangGraph） |
|---|---|---|
| 编排 | while 循环 + 手写 stop_reason 判断 | StateGraph + 条件边 |
| 状态持久化 | 手写 repository 落消息表 | AsyncPostgresSaver（框架自动 checkpoint） |
| 工具 | JSON Schema 字典 + 分发器 | @tool 装饰器 + ToolNode |
| 流式 | 手写 writer 推 custom 事件 | stream_mode 双通道（messages + custom） |
| 配置 | os.environ.get | pydantic-settings 分层 + fail-fast |
| 测试 | 脚本式离线测试 | pytest 三层（unit/graphs/contract） |
