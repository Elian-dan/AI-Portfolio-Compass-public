from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import engine
from .models import Deal, PositionSnapshot, SyncTask, TradeReview


DEMO_DATA_VERSION = "demo_seed_20260714_v1"
DEMO_POSITION_COUNT = 21
DEMO_DEAL_COUNT = 24
DEMO_REVIEW_COUNT = 24


def ensure_demo_data() -> bool:
    """Populate or upgrade the isolated demo workspace during backend startup."""
    settings = get_settings()
    if not _is_demo_workspace(settings.workspace, settings.database_url):
        return False

    with Session(engine) as db:
        version_is_current = db.get(SyncTask, DEMO_DATA_VERSION) is not None
        position_count = db.scalar(select(func.count()).select_from(PositionSnapshot)) or 0
        deal_count = db.scalar(select(func.count()).select_from(Deal)) or 0
        review_count = db.scalar(select(func.count()).select_from(TradeReview)) or 0
        if (
            version_is_current
            and position_count >= DEMO_POSITION_COUNT
            and deal_count >= DEMO_DEAL_COUNT
            and review_count >= DEMO_REVIEW_COUNT
        ):
            return False

    project_dir = Path(__file__).resolve().parents[2]
    seed_script = project_dir / "scripts" / "seed_demo.py"
    env = os.environ.copy()
    env["APP_WORKSPACE"] = "demo"
    env["DATABASE_URL"] = settings.database_url

    engine.dispose()
    result = subprocess.run(
        [sys.executable, str(seed_script)],
        cwd=str(project_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    engine.dispose()
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "未知错误").strip()
        raise RuntimeError(f"演示数据自动初始化失败：{message[:500]}")
    return True


def _is_demo_workspace(workspace: str, database_url: str) -> bool:
    if not database_url.startswith("sqlite:///"):
        return False
    return workspace == "demo" or "demo" in database_url.lower()
