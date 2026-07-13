from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AIRuntimeConfig


DEFAULT_CONFIG_ID = "default"


@dataclass(frozen=True)
class AIProviderTemplate:
    provider: str
    label: str
    default_base_url: str
    default_model: str
    models: tuple[str, ...]
    openai_compatible: bool = True
    help_text: str = ""


PROVIDER_TEMPLATES: tuple[AIProviderTemplate, ...] = (
    AIProviderTemplate(
        "deepseek",
        "DeepSeek",
        "https://api.deepseek.com",
        "deepseek-v4-flash",
        ("deepseek-v4-flash", "deepseek-v4-pro"),
        help_text="DeepSeek 官方当前模型；deepseek-chat 与 deepseek-reasoner 兼容别名将于 2026-07-24 23:59（北京时间）弃用。",
    ),
    AIProviderTemplate("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini", ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini")),
    AIProviderTemplate("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", ("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001")),
    AIProviderTemplate("moonshot", "Moonshot / Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k", ("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k")),
    AIProviderTemplate("qwen", "通义千问 Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", ("qwen-plus", "qwen-turbo", "qwen-max")),
    AIProviderTemplate("siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-72B-Instruct", ("Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3", "THUDM/glm-4-9b-chat")),
    AIProviderTemplate("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", ("glm-4-flash", "glm-4-plus", "glm-4-air")),
    AIProviderTemplate("custom_openai_compatible", "自定义 OpenAI 兼容接口", "", "", (), True, "适用于 Ollama、vLLM、LiteLLM 或其它兼容 /chat/completions 的服务。"),
)


def provider_templates_payload() -> list[dict[str, Any]]:
    return [
        {
            "provider": item.provider,
            "label": item.label,
            "default_base_url": item.default_base_url,
            "default_model": item.default_model,
            "models": list(item.models),
            "openai_compatible": item.openai_compatible,
            "help_text": item.help_text,
        }
        for item in PROVIDER_TEMPLATES
    ]


def get_provider_template(provider: str) -> AIProviderTemplate:
    normalized = str(provider or "").strip().lower()
    return next((item for item in PROVIDER_TEMPLATES if item.provider == normalized), PROVIDER_TEMPLATES[0])


def active_ai_runtime(db: Session | None = None) -> dict[str, Any]:
    item = db.get(AIRuntimeConfig, DEFAULT_CONFIG_ID) if db else None
    if item:
        template = get_provider_template(item.provider)
        return {
            "provider": item.provider or template.provider,
            "display_name": item.display_name or template.label,
            "base_url": item.base_url or template.default_base_url,
            "model": item.model or template.default_model,
            "api_key": item.api_key or "",
            "enabled": bool(item.enabled),
            "has_api_key": bool((item.api_key or "").strip()),
            "last_test_status": item.last_test_status,
            "last_test_message": item.last_test_message,
            "updated_at": item.updated_at,
            "source": "database",
        }
    return env_ai_runtime()


def env_ai_runtime() -> dict[str, Any]:
    settings = get_settings()
    provider = (settings.ai_provider or "deepseek").strip().lower()
    template = get_provider_template(provider)
    if provider == "deepseek":
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url or template.default_base_url
        model = settings.deepseek_model or template.default_model
    else:
        api_key = ""
        base_url = template.default_base_url
        model = template.default_model
    return {
        "provider": provider,
        "display_name": template.label,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "enabled": provider != "local",
        "has_api_key": bool(api_key),
        "last_test_status": "",
        "last_test_message": "",
        "updated_at": None,
        "source": "env",
    }


def ai_runtime_config_payload(db: Session, scenes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    runtime = active_ai_runtime(db)
    return {
        "runtime": public_runtime(runtime),
        "providers": provider_templates_payload(),
        "scenes": scenes or [],
    }


def public_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": runtime.get("provider", ""),
        "display_name": runtime.get("display_name", ""),
        "base_url": runtime.get("base_url", ""),
        "model": runtime.get("model", ""),
        "enabled": bool(runtime.get("enabled")),
        "has_api_key": bool(runtime.get("has_api_key")),
        "masked_api_key": mask_api_key(str(runtime.get("api_key") or "")),
        "last_test_status": runtime.get("last_test_status") or "",
        "last_test_message": runtime.get("last_test_message") or "",
        "updated_at": runtime.get("updated_at"),
        "source": runtime.get("source", ""),
    }


def save_ai_runtime_config(db: Session, payload: dict[str, Any]) -> AIRuntimeConfig:
    provider = str(payload.get("provider") or "deepseek").strip().lower()
    template = get_provider_template(provider)
    item = db.get(AIRuntimeConfig, DEFAULT_CONFIG_ID)
    if not item:
        item = AIRuntimeConfig(config_id=DEFAULT_CONFIG_ID)
    item.provider = template.provider if provider != "custom_openai_compatible" else provider
    item.display_name = str(payload.get("display_name") or template.label).strip()[:120]
    item.base_url = str(payload.get("base_url") or template.default_base_url).strip().rstrip("/")
    item.model = str(payload.get("model") or template.default_model).strip()[:160]
    if "api_key" in payload and str(payload.get("api_key") or "").strip():
        item.api_key = str(payload.get("api_key") or "").strip()
    elif "api_key" in payload and payload.get("api_key") == "":
        item.api_key = ""
    item.enabled = bool(payload.get("enabled", True))
    item.updated_at = datetime.now(timezone.utc)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def mark_ai_runtime_test(db: Session, status: str, message: str) -> None:
    item = db.get(AIRuntimeConfig, DEFAULT_CONFIG_ID)
    if not item:
        return
    item.last_test_status = status[:40]
    item.last_test_message = message[:1000]
    item.updated_at = datetime.now(timezone.utc)
    db.add(item)
    db.commit()


def runtime_can_call_external(runtime: dict[str, Any]) -> bool:
    return bool(runtime.get("enabled") and runtime.get("has_api_key") and runtime.get("base_url") and runtime.get("model"))


def mask_api_key(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:3]}****{text[-4:]}"
