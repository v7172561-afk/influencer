from __future__ import annotations

import time

import requests

from config import get_setting


def publish_image_post(draft: dict) -> str:
    token = get_setting("INSTAGRAM_ACCESS_TOKEN", "").strip()
    ig_user_id = get_setting("INSTAGRAM_USER_ID", "").strip()
    version = get_setting("META_GRAPH_VERSION", "v27.0").strip()
    base = get_setting("INSTAGRAM_API_BASE_URL", "https://graph.instagram.com").rstrip("/")
    if not token or not ig_user_id:
        raise RuntimeError("Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID in secrets first.")
    image_url = str(draft.get("media_url") or "").strip()
    if not image_url.startswith("https://"):
        raise RuntimeError("Instagram needs a publicly reachable HTTPS image URL. Upload the image to Supabase Storage first.")

    root = f"{base}/{version}"
    session = requests.Session()
    create = session.post(
        f"{root}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": f"{draft['caption']}\n\n{draft['hashtags']}", "access_token": token},
        timeout=45,
    )
    _raise_for_meta(create, "Creating Instagram media container")
    creation_id = create.json().get("id")
    if not creation_id:
        raise RuntimeError(f"Meta did not return a media container ID: {create.text[:500]}")

    # Wait for Meta to fetch/process the public image before publishing.
    for _ in range(24):
        status = session.get(
            f"{root}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        if status.ok:
            body = status.json()
            state = body.get("status_code")
            if state == "FINISHED":
                break
            if state in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media processing failed: {body}")
        time.sleep(5)
    else:
        raise TimeoutError("Instagram media processing did not finish within two minutes. Try again later.")

    publish = session.post(
        f"{root}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=45,
    )
    _raise_for_meta(publish, "Publishing Instagram post")
    media_id = publish.json().get("id")
    if not media_id:
        raise RuntimeError(f"Meta did not return a published media ID: {publish.text[:500]}")
    return str(media_id)


def _raise_for_meta(response: requests.Response, action: str) -> None:
    try:
        body = response.json()
    except ValueError:
        body = {"body": response.text[:500]}
    if not response.ok or "error" in body:
        raise RuntimeError(f"{action} failed (HTTP {response.status_code}): {body}")
