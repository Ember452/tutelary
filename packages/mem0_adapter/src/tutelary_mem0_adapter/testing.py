"""跑分与测试辅助：面向用户环境的 Mem0 工厂（需要 mem0ai + LLM API key）。"""

from __future__ import annotations

import os
from typing import Any

from tutelary.core.fakes import FakeBus


def make_mem0_factory() -> Any:
    """返回零参工厂：每轮以 mem0.Memory.from_config 构造全新 Mem0Adapter。

    需要 mem0ai 已安装且 LLM API key 可用（缺省读环境变量
    ``OPENAI_API_KEY``；自定义 mem0 配置请改本函数）。仅在有真实 mem0
    环境时使用——基准的 Mem0 行由此跑出，Mock LLM 等于伪造基准。
    """

    def factory() -> Any:
        from tutelary_mem0_adapter.provider import Mem0Adapter

        config: dict[str, Any] = {
            "llm": {"provider": "openai", "config": {"api_key": os.environ.get("OPENAI_API_KEY")}}
        }
        return Mem0Adapter(FakeBus(), mem0_config=config)

    return factory
