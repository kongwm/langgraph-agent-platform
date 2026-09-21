-- 首次起容器时执行（docker-entrypoint-initdb.d）：
-- LangGraph checkpointer 的独立 database —— 框架表是"框架私产"，
-- 与业务库（Alembic 迁移线）物理隔离，互不污染。
CREATE DATABASE agent_platform_meta;
