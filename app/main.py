"""
入口 —— lifespan 装配（企业级标准：资源生命周期归框架管）
==========================================================
对比 backend 的 @app.on_event（已废弃的写法）：
  async with lifespan(app): 里的资源随进程退出优雅释放，
  图/checkpointer 都是显式构造后挂到 app_state，不依赖模块级全局。

P10.1 用 InMemorySaver；P10.2 换 AsyncPostgresSaver（图结构零改动）。
"""

import contextlib
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@dataclass
class AppState:
    """进程级单例容器：路由通过 app.state 访问，不用模块级全局变量。"""
    graph: Any = None
    checkpointer: Any = None


app_state = AppState()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # --- 持久化策略：P10.2 = AsyncPostgresSaver（agent_platform_meta 库） ---
    # checkpointer 表（checkpoints/checkpoint_blobs/checkpoint_writes）是框架
    # 私产：setup() 自建自管，不进业务库的 Alembic 迁移线 —— 物理隔离。
    # async with 自管连接池，退出时优雅释放（对比 backend 的手写 repository 池）。
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from app.agents.graph import build_agent_graph

    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_db_url) as checkpointer:
        await checkpointer.setup()   # 幂等：建框架表（生产可锁版本后跳过）

        app_state.checkpointer = checkpointer
        app_state.graph = build_agent_graph(checkpointer)
        logger.info(
            "服务就绪",
            env=settings.app_env,
            model=settings.model_main,
            checkpointer=type(checkpointer).__name__,
        )
        yield
        app_state.graph = None


app = FastAPI(title="Agent Platform (P10)", version="0.1.0", lifespan=lifespan)

# 与 backend 相同的 CORS（前端 Vite dev server）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import chat  # noqa: E402  (路由导入放 app 定义后，避免循环依赖)

app.include_router(chat.router)


@app.get("/api/healthz")
async def healthz():
    """健康检查：进程活着 + 图已装配。P10.2 会加 DB 连通检查。"""
    return {
        "status": "ok",
        "engine": "langgraph",
        "graph_ready": app_state.graph is not None,
        "checkpointer": type(app_state.checkpointer).__name__,
    }
