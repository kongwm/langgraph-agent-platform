"""
内置工具 —— @tool 装饰器风格（LangChain 生态的标准写法）
=========================================================
对比 backend 的"JSON Schema 字典 + 手写分发器"：schema 从函数签名和
docstring 自动生成，函数即工具（注册/分发/说明三合一）。
P10.1 精选两个够用（时间 + 计算），工具链后续阶段再扩。
"""

import datetime

from langchain_core.tools import tool


@tool
def get_time() -> str:
    """获取当前日期和时间。用户问现在几点/今天日期时调用。"""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S %A")


@tool
def calculate(expression: str) -> str:
    """计算数学表达式，需要精确数值计算时调用，不要心算。

    Args:
        expression: Python 语法的数学表达式，例如 '(28 * 9/5) + 32'
    """
    import json

    # 教学级安全：只放行数字和运算符（backend 同款最小措施）
    if not all(c in "0123456789+-*/(). %//" for c in expression):
        return json.dumps({"error": "表达式包含不支持的字符"}, ensure_ascii=False)
    try:
        return json.dumps({"result": eval(expression)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"计算失败: {e}"}, ensure_ascii=False)


TOOLS = [get_time, calculate]
