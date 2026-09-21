"""
图状态 —— LangGraph StateGraph 的核心概念
==========================================
P10.1 最小版：一个 messages key + add_messages reducer。

对比 backend 手写版的"列表自己拼"：
  - reducer（add_messages）让每个节点只追加/更新自己的消息，框架负责合并
  - Annotated[list, add_messages] 是 LangGraph 的标准消息状态写法，
    supervisor 多智能体（P10.3）会在这个骨架上加 next/worker 字段
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """total=False：所有 key 可缺省 —— checkpoint 恢复时状态是逐步长出来的。"""

    # 消息历史（add_messages reducer：按 id 合并追加，不是整体覆盖）
    messages: Annotated[list, add_messages]
