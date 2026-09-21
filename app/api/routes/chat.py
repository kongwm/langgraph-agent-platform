"""
对话路由 —— POST /api/chat/stream（SSE，契约同 backend）
=========================================================
P10.1 版本：新消息 → 图运行 → 事件流。
P10.2 会加 resume 字段分流（interrupt 恢复）和 done 的 usage 统计。
鉴权（P10.4）会在这里加 Depends(get_current_user)。
"""

import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.agents.graph import stream_graph_events
from app.core.logging import get_logger, set_trace
from app.core.errors import AgentError

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    conversation_id: str | None = None   # 空 = 新会话，服务端生成
    content: str = ""
    # P10.2 预留：resume 非空 = 恢复 interrupt 的答案而不是新输入
    resume: dict | None = None


async def run_chat(body: ChatRequest) -> AsyncGenerator[tuple[str, dict], None]:
    """SSE 事件生成器：一个 (event, data) 元组 = 一帧。"""
    trace_id = set_trace()
    conversation_id = body.conversation_id or uuid.uuid4().hex
    started = time.perf_counter()

    from app.main import app_state   # 图和 checkpointer 的持有者（lifespan 里装配）

    yield "message_start", {"session_id": conversation_id, "trace_id": trace_id}

    try:
        thread_config = {"configurable": {"thread_id": conversation_id}}
        n_tokens_in = n_tokens_out = 0

        async for ev in stream_graph_events(app_state.graph, body.content, thread_config):
            kind = ev.get("type")
            if kind == "text_delta":
                yield "text_delta", {"text": ev["text"]}
            elif kind == "tool_start":
                yield "tool_start", {"name": ev["name"], "input": ev["input"]}
            elif kind == "tool_result":
                yield "tool_result", {
                    "tool_use_id": ev["tool_use_id"], "content": ev["content"],
                }
            else:
                logger.warning("未知事件类型", event=ev)

        yield "done", {
            "session_id": conversation_id,
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "trace_id": trace_id,
            # P10.5 会接 OTel span 聚合出完整 trace；先给锚点字段保住契约形状
            "usage": {"input_tokens": n_tokens_in, "output_tokens": n_tokens_out},
        }
    except AgentError as e:
        logger.error("业务错误", code=e.code, message=e.message)
        yield "error", {"code": e.code, "message": e.message}
    except Exception:
        # 未知异常：日志带 trace_id 全量记录，对外只给通用文案（不漏内部细节）
        logger.exception("未预期错误")
        yield "error", {"code": "internal", "message": "服务内部错误，请稍后重试"}


@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request):
    from app.infra.sse import sse_response

    return await sse_response(run_chat(body))
