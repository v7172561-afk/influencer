from __future__ import annotations

import hmac
from datetime import date, datetime, time, timedelta
from pathlib import Path

import streamlit as st

from agents.content_agent import generate_content
from config import get_setting, is_configured
from database.db import (
    get_daily_draft,
    init_db,
    list_drafts,
    load_profile,
    save_draft,
    save_profile,
    update_draft,
)
from instagram.publisher import publish_image_post
from media.storage import save_and_upload_media
from utils import local_now, local_today, safe_filename

st.set_page_config(page_title="One AI Influencer Studio", page_icon="✨", layout="wide")
init_db()


def password_gate() -> None:
    expected = get_setting("DASHBOARD_PASSWORD", "")
    if not expected:
        st.warning(
            "DASHBOARD_PASSWORD is not set. This is okay for local testing, but set it "
            "before deploying a public Streamlit app."
        )
        return
    if st.session_state.get("authenticated"):
        return
    st.title("✨ One AI Influencer Studio")
    st.caption("Private owner dashboard")
    entered = st.text_input("Dashboard password", type="password")
    if st.button("Unlock", type="primary"):
        if hmac.compare_digest(entered, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Incorrect password")
    st.stop()


password_gate()

profile = load_profile()
with st.sidebar:
    st.title("✨ Influencer Studio")
    st.caption("Single-influencer MVP")
    page = st.radio(
        "Workspace",
        ["Overview", "Influencer profile", "Create daily draft", "Approval queue", "Settings"],
    )
    st.divider()
    st.write(f"**Influencer:** {profile['name']}")
    st.write(f"**Niche:** {profile['niche']}")
    if st.button("Lock dashboard"):
        st.session_state["authenticated"] = False
        st.rerun()


def render_overview() -> None:
    st.title("Your AI influencer at a glance")
    drafts = list_drafts(limit=100)
    today = local_today().isoformat()
    pending = sum(1 for d in drafts if d["status"] == "pending")
    approved = sum(1 for d in drafts if d["status"] == "approved")
    published = sum(1 for d in drafts if d["status"] == "published")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Drafts", len(drafts))
    c2.metric("Awaiting approval", pending)
    c3.metric("Approved", approved)
    c4.metric("Published", published)

    st.subheader("Today's content")
    daily = get_daily_draft(today)
    if daily:
        st.write(f"**Status:** {daily['status'].title()}  ·  **Style:** {daily['style'].title()}")
        st.write(daily["caption"])
        if daily.get("media_path") and Path(daily["media_path"]).exists():
            st.image(daily["media_path"], width=350)
        if daily.get("media_url"):
            st.caption("Media is uploaded to public storage and ready for Instagram to fetch.")
        st.info("Open Approval queue to review the image, caption and publishing time.")
    else:
        st.info("No draft has been created today. Open **Create daily draft** to make one.")

    st.subheader("How the workflow works")
    st.markdown(
        "1. Generate a daily content draft.\n"
        "2. Create or upload its visual (realistic or animated).\n"
        "3. Review and approve it.\n"
        "4. The scheduled worker publishes approved posts through Meta's API."
    )


def render_profile() -> None:
    st.title("Influencer profile")
    st.caption("Use a fictional adult persona. Keep the identity and visual style consistent.")
    with st.form("profile_form"):
        name = st.text_input("Influencer name", value=profile["name"])
        niche = st.text_input("Niche", value=profile["niche"])
        bio = st.text_area("Public bio", value=profile["bio"], height=90)
        personality = st.text_area("Personality and writing voice", value=profile["personality"], height=130)
        style_mix = st.selectbox(
            "Visual styles",
            ["Mixed: realistic + animated", "Realistic only", "Animated only"],
            index=["Mixed: realistic + animated", "Realistic only", "Animated only"].index(profile["style_mix"]),
        )
        if st.form_submit_button("Save influencer profile", type="primary"):
            save_profile({"name": name.strip(), "niche": niche.strip(), "bio": bio.strip(),
                          "personality": personality.strip(), "style_mix": style_mix})
            st.success("Profile saved.")
            st.rerun()


def render_create() -> None:
    st.title("Create a daily content draft")
    st.write("Create the idea, caption and visual prompt. Add the actual image before approval.")
    available_styles = {
        "Mixed: realistic + animated": ["realistic", "animated"],
        "Realistic only": ["realistic"],
        "Animated only": ["animated"],
    }
    default_style = "realistic" if local_today().toordinal() % 2 == 0 else "animated"
    styles = available_styles.get(profile["style_mix"], ["realistic", "animated"])
    chosen_style = st.selectbox("Today's visual style", styles, index=styles.index(default_style) if default_style in styles else 0)
    topic = st.text_input("Optional topic or campaign theme", placeholder="e.g. minimalist summer outfit ideas")
    suggested_time = time(18, 30)
    publish_date = st.date_input("Target publishing date", value=local_today())
    publish_time = st.time_input("Target publishing time (local time)", value=suggested_time)
    if st.button("Generate draft", type="primary"):
        with st.spinner("Preparing the content draft..."):
            try:
                content = generate_content(profile, chosen_style, topic)
                scheduled = datetime.combine(publish_date, publish_time, tzinfo=local_now().tzinfo).isoformat()
                draft_id = save_draft({
                    "created_at": local_now().isoformat(),
                    "scheduled_at": scheduled,
                    "status": "pending",
                    "style": chosen_style,
                    "topic": topic,
                    **content,
                })
                st.session_state["new_draft_id"] = draft_id
                st.success("Draft created. Upload its visual in the Approval queue.")
            except Exception as exc:
                st.error(f"Could not create the draft: {exc}")
    new_id = st.session_state.get("new_draft_id")
    if new_id:
        st.info(f"Draft ID: {new_id}")
        st.button("Open approval queue", on_click=lambda: st.session_state.update({"_open_queue": True}))
        if st.session_state.pop("_open_queue", False):
            st.info("Choose Approval queue from the sidebar.")


def render_queue() -> None:
    st.title("Approval queue")
    drafts = list_drafts(limit=50)
    if not drafts:
        st.info("No drafts yet. Generate one first.")
        return
    status_filter = st.selectbox("Filter", ["All", "pending", "approved", "published", "failed"])
    filtered = drafts if status_filter == "All" else [d for d in drafts if d["status"] == status_filter]
    if not filtered:
        st.info("Nothing in this filter.")
        return
    for draft in filtered:
        with st.expander(
            f"{draft['created_at'][:16]} · {draft['style'].title()} · {draft['status'].upper()} · {draft['id'][:8]}",
            expanded=draft["status"] in ("pending", "failed"),
        ):
            left, right = st.columns([1, 1])
            with left:
                st.markdown("**Caption**")
                st.write(draft["caption"])
                st.write(draft["hashtags"])
                st.markdown("**Visual prompt**")
                st.text_area("Prompt", value=draft["visual_prompt"], height=150, key=f"prompt_{draft['id']}")
            with right:
                if draft.get("media_path") and Path(draft["media_path"]).exists():
                    st.image(draft["media_path"], use_container_width=True)
                elif draft.get("media_url"):
                    st.image(draft["media_url"], use_container_width=True)
                else:
                    st.warning("No image uploaded yet.")
                uploaded = st.file_uploader(
                    "Upload the final image", type=["jpg", "jpeg", "png"],
                    key=f"upload_{draft['id']}",
                )
                if uploaded and st.button("Save image", key=f"save_image_{draft['id']}"):
                    try:
                        media_path, media_url = save_and_upload_media(
                            draft["id"], uploaded.getvalue(), uploaded.name, uploaded.type
                        )
                        update_draft(draft["id"], media_path=media_path, media_url=media_url)
                        if media_url:
                            st.success("Image saved to Supabase public storage.")
                        else:
                            st.warning("Image saved locally only. Configure Supabase Storage before cloud publishing.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Image upload failed: {exc}")
            st.caption(f"Scheduled: {draft['scheduled_at']} · Status: {draft['status']}")
            if draft.get("error"):
                st.error(draft["error"])
            c1, c2 = st.columns(2)
            if draft["status"] in ("pending", "failed"):
                if c1.button("Approve post", key=f"approve_{draft['id']}", type="primary"):
                    if not draft.get("media_url"):
                        st.error("Upload the image to Supabase public storage before approval for cloud publishing.")
                    else:
                        update_draft(draft["id"], status="approved", error="")
                        st.success("Approved. The scheduled worker can publish it at the selected time.")
                        st.rerun()
            if draft["status"] == "approved":
                if c1.button("Publish now", key=f"publish_{draft['id']}"):
                    try:
                        result = publish_image_post(draft)
                        update_draft(draft["id"], status="published", ig_media_id=result,
                                     published_at=local_now().isoformat(), error="")
                        st.success("Published to Instagram.")
                        st.rerun()
                    except Exception as exc:
                        update_draft(draft["id"], status="failed", error=str(exc))
                        st.error(f"Publishing failed: {exc}")
                if c2.button("Revoke approval", key=f"revoke_{draft['id']}"):
                    update_draft(draft["id"], status="pending")
                    st.rerun()


def render_settings() -> None:
    st.title("Connections and deployment")
    st.subheader("Service readiness")
    checks = [
        ("Groq API key", is_configured("GROQ_API_KEY")),
        ("Supabase URL + service key", is_configured("SUPABASE_URL") and is_configured("SUPABASE_SERVICE_ROLE_KEY")),
        ("Supabase database URL", is_configured("DATABASE_URL")),
        ("Instagram access token", is_configured("INSTAGRAM_ACCESS_TOKEN")),
        ("Instagram professional account ID", is_configured("INSTAGRAM_USER_ID")),
        ("Dashboard password", is_configured("DASHBOARD_PASSWORD")),
    ]
    for label, ready in checks:
        st.write(("✅ " if ready else "⬜ ") + label)
    st.info("Secrets are read from Streamlit secrets locally/deployed, or from environment variables in the automation worker. Never commit real tokens to GitHub.")
    st.subheader("Instagram connection")
    st.markdown(
        "1. Create a Meta developer app and add the Instagram API / Instagram Login product.\n"
        "2. Use an Instagram **Creator** or Business professional account.\n"
        "3. Grant the publishing permission (`instagram_business_content_publish`) and complete any required app setup/review.\n"
        "4. Put the resulting access token and Instagram professional account ID in Streamlit secrets and GitHub Actions secrets.\n"
        "5. The image must be available through a public URL when Meta fetches it; this starter uses a public Supabase Storage bucket."
    )
    st.warning("The starter uses manually provisioned Meta credentials, not a self-service OAuth connect flow. Keep the app private and protect secrets. App Review/permissions may be needed before use beyond your own app roles.")
    st.subheader("Free-first boundaries")
    st.markdown(
        "- Text and captions can use Groq's free allowance, subject to account/model rate limits.\n"
        "- Image generation is not included in the free cloud architecture. Create visuals locally (for example, with ComfyUI if your computer can run it) and upload the final image.\n"
        "- Streamlit is the dashboard, not the scheduler. GitHub Actions runs the hourly automation tick. Scheduled runs can be delayed.\n"
        "- Supabase is used for persistent database records and public media URLs. Monitor free-plan quotas and pause behavior."
    )


if page == "Overview":
    render_overview()
elif page == "Influencer profile":
    render_profile()
elif page == "Create daily draft":
    render_create()
elif page == "Approval queue":
    render_queue()
else:
    render_settings()
