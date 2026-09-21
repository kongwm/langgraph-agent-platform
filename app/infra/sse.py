"""
SSE 封装 —— 契约与 platform/backend 完全一致（前端零改动的关键）
==================================================================
帧格式：`event: <事件名>\ndata: <json>\n\n`（POST + text/event-stream）
事件序列：message_start → text_delta / tool_start / tool_result / ask_user
          / error → done（终态，带 trace/usage）

契约测试（tests/contract/）对齐 backend 的序列快照，改契约必先改测试。
"""

import json
from typing import AsyncGenerator

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",   # 告诉 nginx 别缓冲（虽然是本地直连，习惯养成）
}


def sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def sse_response(event_gen: AsyncGenerator[tuple[str, dict], None]):
    """把 (event, data) 元组流编码成 StreamingHttpResponse 的字节流。"""
    from fastapi.responses import StreamingResponse

    async def byte_stream():
        async for event, data in event_gen:
            yield sse_frame(event, data).encode("utf-8")

    return StreamingResponse(byte_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
