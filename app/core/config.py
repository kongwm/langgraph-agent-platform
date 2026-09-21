"""
配置 —— pydantic-settings 分层加载（企业级标准做法）
====================================================
和 platform/backend 的手写 os.environ.get 对比：
  - 类型校验/默认值/别名声明式表达，配错启动即报错（而不是运行到一半炸）
  - 分层覆盖：.env（基础）→ .env.{APP_ENV}（环境叠加）→ 真实环境变量（最高）
  - secret 字段 repr 自动打码，日志里不会漏 key

本模块是唯一读环境变量的地方（同 backend 约定），其他模块只 import settings。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置。字段名即环境变量名（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        # 分层顺序：后者覆盖前者。APP_ENV 缺省 dev → 叠加 .env.dev
        env_file=(".env", ".env.dev", ".env.prod"),
        env_file_encoding="utf-8",
        extra="ignore",          # .env 里有别的段（如 backend 拷来的 key）不报错
    )

    # --- 运行环境 ---
    app_env: str = "dev"         # dev / prod
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # --- LLM（GLM Anthropic 兼容端点） ---
    anthropic_base_url: str = "https://open.bigmodel.cn/api/anthropic"
    anthropic_api_key: str = ""
    model_main: str = "glm-5.3"        # 主模型（agent 推理）
    model_cheap: str = "glm-4.5-air"   # 便宜模型（标题/护栏判定等辅助角色）
    max_tokens: int = 16000

    # --- 数据库（同容器两个库，见 docker-compose.yml / docker/init.sql） ---
    database_url: str                        # 业务库（无默认值：缺配置启动即失败）
    checkpoint_db_url: str                   # 框架库（LangGraph checkpointer 私产）

    # --- 预留：P10.5 可观测（默认关闭，不外发数据） ---
    langsmith_api_key: str = ""
    otel_endpoint: str = ""


@lru_cache          # 进程内单例：所有模块共享同一份（且只解析一次 env 文件）
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
