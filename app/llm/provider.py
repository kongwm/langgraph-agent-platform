"""
LLM provider —— langchain-anthropic 接 GLM（Anthropic 兼容端点）
================================================================
从 platform/backend/app/graph/provider.py 原样搬运（P8 踩坑的成果）：

⚠️ 本机坑：langchain-anthropic 1.x 不再接受外部 http_client，内部自建
httpx client 且 trust_env=True —— 会读 macOS 系统代理（Clash），访问国内
端点被掐 TLS。只能 patch 它的默认 client 工厂，注入 trust_env=False。

⚠️ timeout 必须透传（None 时兜底 300s）—— 接管私有工厂就要接管它的全部
职责，丢了 timeout 实测会让流式读 stall 后无超时挂死 50 分钟+。
"""

import httpx2
import langchain_anthropic.chat_models as _cm
from langchain_anthropic import ChatAnthropic

from app.core.config import settings


def _trust_no_env_async_client(*, base_url=None, timeout=None, anthropic_proxy=None):
    """替换 langchain_anthropic._client_utils 的默认工厂：不读系统代理。"""
    return httpx2.AsyncClient(
        base_url=base_url, trust_env=False,
        timeout=timeout if timeout is not None else httpx2.Timeout(300.0),
    )


# 必须在首次实例化 ChatAnthropic 之前生效（顶层 patch 的写法保持）
_cm._get_default_async_httpx_client = _trust_no_env_async_client


def make_llm(role: str = "main") -> ChatAnthropic:
    """按角色建模型：main = 主模型（agent 推理），cheap = 便宜模型（辅助任务）。

    对应 backend 的 llm/roles.py 成本路由思想：标题生成/护栏判定走便宜模型，
    只有 agent 主循环用主模型。
    """
    model = settings.model_main if role == "main" else settings.model_cheap
    return ChatAnthropic(
        model=model,
        base_url=settings.anthropic_base_url,
        api_key=settings.anthropic_api_key,
        max_tokens=settings.max_tokens,
    )
