"""
结构化日志 —— structlog JSON 输出（企业级可观测的地基）
====================================================
对比 platform/backend 的 logging.getLogger + 人读格式：
  - JSON 每行一条记录：字段可检索、可被日志系统（ELK/Loki）直接索引
  - contextvars 自动注入：一个请求里所有日志带同一 trace_id，不用层层传参
  - prod 用 JSON，dev 友好输出用 console 渲染（env 切换，代码零改动）
"""

import contextvars
import logging
import uuid

import structlog

from app.core.config import settings

# 请求级上下文：chat 每轮 SSE 请求开始时 set_trace()，后续所有日志自动携带
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def set_trace(trace_id: str | None = None) -> str:
    tid = trace_id or uuid.uuid4().hex[:12]
    _trace_id.set(tid)
    return tid


def get_trace() -> str:
    return _trace_id.get()


def _inject_trace_id(logger, method: str, event_dict: dict) -> dict:
    """structlog processor：每条日志自动带 trace_id（排查请求的锚点）。"""
    event_dict["trace_id"] = _trace_id.get()
    return event_dict


def setup_logging() -> None:
    """main.py lifespan 里调用一次。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_trace_id,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            # dev：彩色控制台（人读）；prod：JSON（机器读）
            structlog.dev.ConsoleRenderer()
            if settings.app_env == "dev"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
