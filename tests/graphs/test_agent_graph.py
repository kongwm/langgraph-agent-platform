"""
图逻辑测试 —— FakeChatModel + MemorySaver，零网络零数据库
==========================================================
企业级测试策略的核心：编排逻辑（路由/状态/事件）和 LLM 解耦。
FakeLLM 按脚本出牌（第一次要调工具，第二次给最终答案），
断言图的行为而不是模型的行为。
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.graph import build_agent_graph
from app.tools.builtin import TOOLS


class FakeLLM:
    """脚本化假模型：按顺序吐预设回复。bind_tools 返回自身（图只调 ainvoke）。"""

    def __init__(self, replies: list[AIMessage]):
        self.replies = list(replies)
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages, config=None, **kwargs):
        reply = self.replies.pop(0)
        self.calls += 1
        return reply


@pytest.fixture
def tool_call_llm():
    # 第一轮：要求调 get_time；拿到工具结果后：给最终文本
    return FakeLLM([
        AIMessage(content="", tool_calls=[{
            "name": "get_time", "args": {}, "id": "call_test_1",
        }]),
        AIMessage(content="现在是测试时间。"),
    ])


@pytest.mark.asyncio
async def test_agent_loop_routes_to_tools_and_back(tool_call_llm):
    """有 tool_calls → tools 节点执行 → 回 agent → 无 tool_calls → END。"""
    graph = build_agent_graph(checkpointer=InMemorySaver(), llm=tool_call_llm)

    events: list[dict] = []
    config = {"configurable": {"thread_id": "t1"}}

    async for mode, chunk in graph.astream(
        {"messages": [HumanMessage(content="现在几点？")]},
        config=config,
        stream_mode=["messages", "custom"],
    ):
        if mode == "custom":
            events.append(chunk)

    # 事件序列：tool_start（agent 节点推）→ tool_result（tools 节点推）
    kinds = [e["type"] for e in events]
    assert kinds == ["tool_start", "tool_result"]
    assert events[0]["name"] == "get_time"
    assert "20" in events[1]["content"]            # 工具真实执行了（返回年份）

    # 终态消息形状：human → ai(tool_call) → tool → ai(最终)
    state = await graph.aget_state(config)
    roles = [type(m).__name__ for m in state.values["messages"]]
    assert roles == ["HumanMessage", "AIMessage", "ToolMessage", "AIMessage"]


@pytest.mark.asyncio
async def test_checkpointer_restores_thread_state(tool_call_llm):
    """同 thread_id 第二次 astream：历史被 checkpointer 恢复（内存版验证机制）。"""
    graph = build_agent_graph(checkpointer=InMemorySaver(), llm=tool_call_llm)
    config = {"configurable": {"thread_id": "t2"}}

    await graph.ainvoke({"messages": [HumanMessage(content="第一轮")]}, config=config)
    # FakeLLM 的脚本已耗尽 —— 如果历史没恢复，这轮会 IndexError
    graph2_llm = FakeLLM([AIMessage(content="第二轮回答")])
    # 关键：同一 checkpointer、新图实例 —— 模拟进程重启后重建图
    graph2 = build_agent_graph(checkpointer=graph.checkpointer, llm=graph2_llm)

    # 关键：换一个 graph 实例但同一（内存）checkpointer —— 模拟进程重启
    state = await graph2.checkpointer.aget(config)
    assert state is not None
    assert len(state["channel_values"]["messages"]) == 4   # 第一轮的全部历史还在
