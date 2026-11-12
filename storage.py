from __future__ import annotations

import mimetypes
from pathlib import Path

from config import get_setting
from utils import safe_filename


def save_and_upload_media(draft_id: str, content: bytes, original_name: str, mime_type: str | None):
    ext_name = safe_filename(original_name)
    local_dir = Path("data/media")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / f"{draft_id}{Path(ext_name).suffix}"
    local_path.write_bytes(content)

    url = ""
    supabase_url = get_setting("SUPABASE_URL", "").strip()
    service_key = get_setting("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bucket = get_setting("SUPABASE_BUCKET", "influencer-media").strip()
    if supabase_url and service_key:
        from supabase import create_client
        client = create_client(supabase_url, service_key)
        storage_path = f"posts/{draft_id}{Path(ext_name).suffix}"
        content_type = mime_type or mimetypes.guess_type(ext_name)[0] or "image/jpeg"
        client.storage.from_(bucket).upload(
            storage_path,
            content,
            file_options={"content-type": content_type, "upsert": "true", "cache-control": "3600"},
        )
        url = client.storage.from_(bucket).get_public_url(storage_path)
    return str(local_path), url
