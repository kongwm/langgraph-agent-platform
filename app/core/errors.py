"""
统一异常体系 —— 所有错误都转成 SSE error 事件，不让流断在半路
================================================================
SSE 是长连接：节点抛异常如果直接冒泡，客户端收到的是连接断开而不是
错误信息。约定：图运行中的业务异常包装为 AgentError，chat 路由捕获后
yield error 事件再正常收尾；未知异常记日志 + 通用错误文案（不漏内部细节）。
"""


class AgentError(Exception):
    """业务可预期错误（配置缺失、会话不存在、LLM 调用失败等）。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class ThreadAccessDenied(AgentError):
    """thread 不属于当前用户（P10.4 鉴权：防越权恢复别人的中断）。"""

    def __init__(self, thread_id: str):
        super().__init__("thread_access_denied", f"会话 {thread_id} 不存在或无权访问")
