"""어댑터 선택.

3단계에서 ollama_adapter를 여기에 추가한다(D08). 루프는 바뀌지 않는다.
"""

from __future__ import annotations

from ..contracts import AdapterError

AVAILABLE = ("openai", "mock")


def build(provider: str, model: str | None):
    if provider == "openai":
        from .openai_adapter import DEFAULT_MODEL, OpenAIAdapter

        return OpenAIAdapter(model=model or DEFAULT_MODEL)
    if provider == "mock":
        from .mock_adapter import DEFAULT_DEMO_SCRIPT, MockAdapter

        return MockAdapter(DEFAULT_DEMO_SCRIPT)
    raise AdapterError("unknown_provider", f"{provider}는 없는 provider입니다. 사용 가능: {', '.join(AVAILABLE)}")
