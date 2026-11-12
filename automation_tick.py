from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime, time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.content_agent import generate_content
from config import get_setting
from database.db import due_approved_drafts, get_daily_draft, init_db, load_profile, save_draft, update_draft
from instagram.publisher import publish_image_post
from utils import local_now, local_today

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def create_daily_draft() -> None:
    today = local_today()
    if get_daily_draft(today.isoformat()):
        logging.info("A draft already exists for %s", today)
        return
    if not get_setting("GROQ_API_KEY", "").strip():
        logging.warning("GROQ_API_KEY is missing; skipping automatic AI draft generation.")
        return
    profile = load_profile()
    styles = ["realistic", "animated"]
    style = styles[today.toordinal() % 2]
    content = generate_content(profile, style, "")
    schedule_time = get_setting("DEFAULT_POST_TIME", "18:30")
    scheduled = datetime.combine(today, time.fromisoformat(schedule_time), tzinfo=local_now().tzinfo).isoformat()
    save_draft({
        "created_at": local_now().isoformat(),
        "scheduled_at": scheduled,
        "status": "pending",
        "style": style,
        "topic": "Daily AI-generated idea",
        **content,
    })
    logging.info("Created today's %s draft", style)


def publish_due() -> None:
    now = local_now().isoformat()
    for draft in due_approved_drafts(now):
        try:
            if not draft.get("media_url"):
                logging.warning("Skipping draft %s: no public media URL", draft["id"])
                continue
            media_id = publish_image_post(draft)
            update_draft(draft["id"], status="published", ig_media_id=media_id,
                         published_at=local_now().isoformat(), error="")
            logging.info("Published draft %s as Instagram media %s", draft["id"], media_id)
        except Exception as exc:
            update_draft(draft["id"], status="failed", error=str(exc))
            logging.exception("Publishing failed for draft %s", draft["id"])


def main() -> None:
    init_db()
    create_daily_draft()
    publish_due()


if __name__ == "__main__":
    main()
