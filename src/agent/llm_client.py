from typing import Optional

from openai import OpenAI

from src.config import get_llm_config


def _build_client():
    cfg = get_llm_config()
    if cfg["provider"] == "ollama":
        return OpenAI(base_url=cfg["base_url"], api_key="ollama")
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


def chat(
    messages: list,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    cfg = get_llm_config()
    client = _build_client()
    model = model or cfg["model"]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def list_available_models() -> list:
    cfg = get_llm_config()
    try:
        client = _build_client()
        models = client.models.list()
        return [m.id for m in models]
    except Exception:
        return [cfg["model"]]
