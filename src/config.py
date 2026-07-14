import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
CACHE_DIR = Path(os.getenv("CACHE_DIR", "./data/cache"))

PROVIDER_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    "ollama": {
        "base_url": None,
        "default_model": "qwen2.5",
    },
}


def get_llm_config():
    provider = LLM_PROVIDER
    cfg = PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["deepseek"])
    return {
        "provider": provider,
        "api_key": LLM_API_KEY,
        "model": LLM_MODEL or cfg["default_model"],
        "base_url": OLLAMA_BASE_URL if provider == "ollama" else cfg["base_url"],
    }
