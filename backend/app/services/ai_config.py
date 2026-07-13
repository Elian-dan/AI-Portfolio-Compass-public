from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AIProviderConfig


def scene_key(workflow_type: str) -> str:
    return f"workflow_{workflow_type}"


def get_ai_scene_config(db: Session, scene: str, default_model: str, default_prompt: str, default_provider: str = "deepseek") -> dict[str, str]:
    item = db.get(AIProviderConfig, scene)
    return {
        "scene": scene,
        "provider": default_provider,
        "model": (item.model if item and item.model else default_model),
        "system_prompt": (item.system_prompt if item and item.system_prompt else default_prompt),
    }


def list_ai_scene_configs(db: Session, defaults: list[dict[str, str]]) -> list[dict[str, Any]]:
    saved = {item.scene: item for item in db.scalars(select(AIProviderConfig)).all()}
    rows: list[dict[str, Any]] = []
    for default in defaults:
        scene = default["scene"]
        item = saved.get(scene)
        rows.append({
            "scene": scene,
            "label": default["label"],
            "provider": default.get("provider", "deepseek"),
            "model": item.model if item and item.model else default["model"],
            "system_prompt": item.system_prompt if item and item.system_prompt else default["system_prompt"],
            "default_model": default["model"],
            "default_prompt": default["system_prompt"],
            "updated_at": item.updated_at if item else None,
        })
    return rows


def save_ai_scene_configs(db: Session, scenes: list[dict[str, Any]], valid_scenes: set[str]) -> list[AIProviderConfig]:
    now = datetime.now(timezone.utc)
    saved: list[AIProviderConfig] = []
    for payload in scenes:
        scene = str(payload.get("scene") or "").strip()
        if scene not in valid_scenes:
            continue
        item = db.get(AIProviderConfig, scene)
        if not item:
            item = AIProviderConfig(scene=scene, provider=str(payload.get("provider") or "deepseek"), updated_at=now)
        item.provider = str(payload.get("provider") or item.provider or "deepseek").strip()[:80]
        item.model = str(payload.get("model") or "").strip()[:120]
        item.system_prompt = str(payload.get("system_prompt") or "")[:20000]
        item.updated_at = now
        db.add(item)
        saved.append(item)
    db.commit()
    for item in saved:
        db.refresh(item)
    return saved
