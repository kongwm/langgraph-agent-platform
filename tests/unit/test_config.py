"""配置单测：pydantic-settings 的类型校验与默认值。"""

from app.core.config import Settings


def test_settings_type_cast_and_defaults():
    """环境变量字符串被正确转型（port int / bool），缺省字段给默认值。"""
    s = Settings(
        _env_file=None,           # 测试不读 .env，参数直接注入
        database_url="postgresql://x/y",
        checkpoint_db_url="postgresql://x/z",
        port="9001",
    )
    assert s.port == 9001           # str → int
    assert s.app_env == "dev"       # 默认值
    assert s.model_main == "glm-5.3"


def test_settings_missing_required_fails_fast():
    """必填项缺失：启动即报错（企业级配置的 fail-fast 原则）。"""
    import pytest
    with pytest.raises(Exception):
        Settings(_env_file=None)    # database_url 缺失 → ValidationError
