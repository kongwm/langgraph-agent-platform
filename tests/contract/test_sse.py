"""
SSE 契约测试 —— 与 platform/backend 契约对齐的回归保险
======================================================
用 httpx ASGITransport 直连 FastAPI app（不起端口、不碰网络），
LLM 用 fake 注入 —— 图路由走真实代码路径。

契约锚点（前端 src/api/chat.ts 依赖）：
  首帧 message_start{session_id} → 中间 text_delta/tool_* → 终帧 done{session_id}
"""

import json

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.agents.graph import build_agent_graph
from app.main import app, app_state
from langgraph.checkpoint.memory import InMemorySaver


from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeChatModel(BaseChatModel):
    """真 BaseChatModel 子类（不是裸对象）：ainvoke 自动触发 langchain 回调，
    stream_mode="messages" 才能捕获 —— 框架靠回调取 token 流，这是它的契约。"""

    reply: str = "测试回复。"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        """实现 _stream 才会触发 on_llm_new_token 回调 —— langgraph 的
        stream_mode="messages" 只听这个（非流式 _generate 不吐 token 事件）。"""
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        for token in ["测试", "回复。"]:
            msg = AIMessageChunk(content=token)
            if run_manager:
                run_manager.on_llm_new_token(token, chunk=msg)
            yield ChatGenerationChunk(message=msg)

    @property
    def _llm_type(self):
        return "fake"


@pytest.mark.asyncio
async def test_sse_event_sequence():
    # 替换 app_state 里的图为 fake 版（路由从 app_state 取图 —— 装配可测性的回报）
    app_state.graph = build_agent_graph(checkpointer=InMemorySaver(), llm=FakeChatModel())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/chat/stream",
            json={"content": "你好"},
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    # 解析 SSE 帧：event 行 + data 行
    events: list[tuple[str, dict]] = []
    for block in resp.text.split("\n\n"):
        lines = block.strip().splitlines()
        if not lines:
            continue
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))

    names = [e for e, _ in events]
    # 契约：首帧 message_start，终帧 done，中间至少一条 text_delta
    assert names[0] == "message_start"
    assert names[-1] == "done"
    assert "text_delta" in names
    assert events[0][1]["session_id"] == events[-1][1]["session_id"]
    assert events[-1][1]["wall_ms"] >= 0
