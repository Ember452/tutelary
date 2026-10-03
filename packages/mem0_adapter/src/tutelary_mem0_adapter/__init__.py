"""Tutelary 官方 Mem0 adapter——以第三方姿态验证契约中立（docs/01 §5）。

顶层导入名 ``tutelary_mem0_adapter``（langchain-openai 之于 langchain 的
形态）：只依赖 tutelary-core，mem0ai 是可选 extra、惰性导入——真实
mem0 需要外部 LLM，适配逻辑因此用注入客户端离线测试。
"""

from tutelary_mem0_adapter.errors import Mem0AdapterError, Mem0UnavailableError
from tutelary_mem0_adapter.provider import Mem0Adapter

__all__ = ["Mem0Adapter", "Mem0AdapterError", "Mem0UnavailableError"]
