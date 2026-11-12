from __future__ import annotations

import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column, MetaData, String, Table, Text, create_engine, select, update,
)
from sqlalchemy.engine import Engine

from config import get_setting

metadata = MetaData()
profiles = Table(
    "influencer_profile", metadata,
    Column("id", String(20), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("niche", String(120), nullable=False),
    Column("bio", Text, nullable=False),
    Column("personality", Text, nullable=False),
    Column("style_mix", String(80), nullable=False),
)
drafts = Table(
    "content_drafts", metadata,
    Column("id", String(36), primary_key=True),
    Column("created_at", String(40), nullable=False),
    Column("scheduled_at", String(40), nullable=False),
    Column("status", String(20), nullable=False),
    Column("style", String(20), nullable=False),
    Column("topic", Text, nullable=False, default=""),
    Column("caption", Text, nullable=False),
    Column("hashtags", Text, nullable=False),
    Column("visual_prompt", Text, nullable=False),
    Column("alt_text", Text, nullable=False),
    Column("media_path", Text, nullable=False, default=""),
    Column("media_url", Text, nullable=False, default=""),
    Column("ig_media_id", String(120), nullable=False, default=""),
    Column("published_at", String(40), nullable=False, default=""),
    Column("error", Text, nullable=False, default=""),
)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_setting("DATABASE_URL", "").strip()
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
    Path("data").mkdir(exist_ok=True)
    return create_engine("sqlite:///data/influencer.db", connect_args={"check_same_thread": False})


def init_db() -> None:
    metadata.create_all(get_engine())
    with get_engine().begin() as conn:
        found = conn.execute(select(profiles.c.id).where(profiles.c.id == "main")).first()
        if not found:
            conn.execute(profiles.insert().values(
                id="main", name="Your Virtual Creator", niche="Lifestyle",
                bio="A fictional adult virtual creator sharing creative lifestyle inspiration.",
                personality="Warm, curious, optimistic and thoughtful. Write naturally, avoid exaggerated claims.",
                style_mix="Mixed: realistic + animated",
            ))


def load_profile() -> dict[str, Any]:
    with get_engine().connect() as conn:
        row = conn.execute(select(profiles).where(profiles.c.id == "main")).mappings().first()
    return dict(row) if row else {}


def save_profile(data: dict[str, Any]) -> None:
    values = {k: data[k] for k in ("name", "niche", "bio", "personality", "style_mix")}
    with get_engine().begin() as conn:
        exists = conn.execute(select(profiles.c.id).where(profiles.c.id == "main")).first()
        if exists:
            conn.execute(update(profiles).where(profiles.c.id == "main").values(**values))
        else:
            conn.execute(profiles.insert().values(id="main", **values))


def save_draft(data: dict[str, Any]) -> str:
    draft_id = str(uuid.uuid4())
    values = {k: data.get(k, "") for k in drafts.c.keys() if k != "id"}
    values["id"] = draft_id
    with get_engine().begin() as conn:
        conn.execute(drafts.insert().values(**values))
    return draft_id


def list_drafts(limit: int = 50) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(drafts).order_by(drafts.c.created_at.desc()).limit(limit)).mappings().all()
    return [dict(r) for r in rows]


def get_daily_draft(day_iso: str) -> dict[str, Any] | None:
    with get_engine().connect() as conn:
        rows = conn.execute(select(drafts).order_by(drafts.c.created_at.desc())).mappings().all()
    for row in rows:
        if str(row["created_at"]).startswith(day_iso):
            return dict(row)
    return None


def get_draft(draft_id: str) -> dict[str, Any] | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(drafts).where(drafts.c.id == draft_id)).mappings().first()
    return dict(row) if row else None


def update_draft(draft_id: str, **values: Any) -> None:
    allowed = {"status", "media_path", "media_url", "ig_media_id", "published_at", "error", "scheduled_at"}
    clean = {k: v for k, v in values.items() if k in allowed}
    if not clean:
        return
    with get_engine().begin() as conn:
        conn.execute(update(drafts).where(drafts.c.id == draft_id).values(**clean))


def due_approved_drafts(now_iso: str) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(drafts).where(drafts.c.status == "approved", drafts.c.scheduled_at <= now_iso)
            .order_by(drafts.c.scheduled_at.asc())
        ).mappings().all()
    return [dict(r) for r in rows]
