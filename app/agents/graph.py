"""
图装配 —— P10.1 最小版：单节点 agent 图（llm ⇄ tools 循环）
============================================================
P10.1 只求跑通"图 + 流式 + 工具"，结构刻意最小：
    START → agent ─(有 tool_calls)→ tools ─回边→ agent ─(无)→ END

与 backend/app/graph/engine.py（P8 对照版）的差异：
  - 这里用 prebuilt 的 ToolNode（P8 刻意手写工具节点做对比，P10 用生态件）
  - checkpointer 从外部注入（P10.1 先 MemorySaver，P10.2 换 AsyncPostgresSaver
    —— 持久化是"装配时决定"的，图结构零改动，这是框架分层的价值）
  - 流式用 stream_mode="messages"（框架原生 token 流）而非手写 writer 推送

P10.3 会在这里插入 input_guard 前置节点和 supervisor 结构。
"""

import json
from typing import AsyncGenerator

from langchain_core.messages import AIMessageChunk
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents.state import AgentState
from app.llm.provider import make_llm
from app.tools.builtin import TOOLS


def build_agent_graph(checkpointer=None, llm=None):
    """装配 agent 图。checkpointer/llm 参数化注入：
    持久化策略可替换（MemorySaver ↔ PG），测试可注入 FakeChatModel 不碰网络。
    """
    llm_with_tools = llm.bind_tools(TOOLS) if llm else make_llm("main").bind_tools(TOOLS)

    async def agent_node(state: AgentState) -> dict:
        """LLM 节点：调模型，返回新消息（add_messages reducer 自动合并）。"""
        writer = get_stream_writer()   # custom 流：给 SSE 层推工具事件用
        response = await llm_with_tools.ainvoke(state["messages"])
        # token 级流式由 stream_mode="messages" 负责；这里推非文本事件
        if response.tool_calls:
            for tc in response.tool_calls:
                writer({
                    "type": "tool_start",
                    "name": tc["name"],
                    "input": tc["args"],
                })
        return {"messages": [response]}

    async def tools_event_writer(state: AgentState) -> dict:
        """包一层 ToolNode：工具执行完把结果也推给 custom 流（SSE 用）。

        ToolNode 本身不推流，所以不能直接 add_node(tools_node)——
        这个包装是"用生态件 + 保留自定义事件通道"的最小代价。
        """
        writer = get_stream_writer()
        result = await ToolNode(TOOLS).ainvoke(state)
        for msg in result["messages"]:
            writer({
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": msg.content if isinstance(msg.content, str)
                else json.dumps(msg.content, ensure_ascii=False),
            })
        return result

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_event_writer)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        # 有 tool_calls → 去 tools；否则结束（LangGraph 最常见的路由判断）
        lambda s: "tools" if s["messages"][-1].tool_calls else END,
    )
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


async def stream_graph_events(graph, message_text: str, thread_config: dict) -> AsyncGenerator[dict, None]:
    """把图的一次运行转成统一事件流（SSE 层直接消费）。

    stream_mode 双通道（P8 同款思路，这里换成框架原生组合）：
      - "messages"：token 级 (chunk, metadata) 元组流 → text_delta
      - "custom"： 节点内 writer() 推的事件 → tool_start / tool_result
    """
    from langchain_core.messages import HumanMessage

    async for mode, chunk in graph.astream(
        {"messages": [HumanMessage(content=message_text)]},
        config=thread_config,
        stream_mode=["messages", "custom"],
    ):
        if mode == "custom":
            yield chunk                       # writer 推的 dict 原样透传
        else:
            msg, metadata = chunk
            # 只透传 AI 的 token 流（messages 模式也会吐 tool/human 消息）。
            # GLM 的 content 是块列表（thinking/text 混排）——只留 text 块，
            # thinking 块不进前端（同 backend 手写版对 thinking 的处理）
            if isinstance(msg, AIMessageChunk) and msg.content:
                if isinstance(msg.content, str):
                    yield {"type": "text_delta", "text": msg.content}
                elif isinstance(msg.content, list):
                    text = "".join(
                        b.get("text", "") for b in msg.content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                    if text:
                        yield {"type": "text_delta", "text": text}
