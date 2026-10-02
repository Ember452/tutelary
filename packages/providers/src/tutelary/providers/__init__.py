"""Tutelary LLM 多协议流式适配：OpenAI 兼容 + Anthropic + 韧性包装。

只依赖 core 与 httpx；全部测试经 httpx MockTransport 脚本化 SSE，
离线运行（AGENTS §4.7）。
"""

from tutelary.providers.errors import ProviderError

__all__ = ["ProviderError"]
