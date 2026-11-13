from __future__ import annotations

import json, os, sqlite3, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import streamlit as st
from PIL import Image
from io import BytesIO

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
MEDIA_DIR = DATA_DIR / "media"
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)
DB = DATA_DIR / "studio.db"

st.set_page_config(page_title="Influencer Studio", page_icon="✨", layout="wide")

def setting(key: str, default: str = "") -> str:
    try:
        value = st.secrets.get(key, os.getenv(key, default))
    except Exception:
        value = os.getenv(key, default)
    return str(value or default)

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1), name TEXT, niche TEXT, bio TEXT, persona TEXT, reference_path TEXT, reference_uri TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY, created_at TEXT, prompt TEXT, caption TEXT, hashtags TEXT, status TEXT, image_path TEXT, image_uri TEXT, video_path TEXT, video_uri TEXT, ig_media_id TEXT, scheduled_at TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS metrics(id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT, fetched_at TEXT, views INTEGER DEFAULT 0, reach INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, saves INTEGER DEFAULT 0);
        """)
        c.execute("INSERT OR IGNORE INTO profile(id,name,niche,bio,persona,created_at) VALUES(1,'Ava','Lifestyle & fashion','A virtual creator sharing everyday style and inspiration.','Fictional adult woman, 25+, warm confident personality, natural expressions.',?)",(now(),))

def now(): return datetime.now(timezone.utc).isoformat()

def profile():
    with db() as c: return dict(c.execute("SELECT * FROM profile WHERE id=1").fetchone())

def save_profile(name,niche,bio,persona,reference_path=None,reference_uri=None):
    with db() as c:
        c.execute("UPDATE profile SET name=?,niche=?,bio=?,persona=?,reference_path=COALESCE(?,reference_path),reference_uri=COALESCE(?,reference_uri) WHERE id=1",(name,niche,bio,persona,reference_path,reference_uri))

def posts():
    with db() as c: return [dict(r) for r in c.execute("SELECT * FROM posts ORDER BY created_at DESC")]

def save_post(prompt,caption,hashtags):
    pid=uuid.uuid4().hex[:12]
    with db() as c: c.execute("INSERT INTO posts(id,created_at,prompt,caption,hashtags,status) VALUES(?,?,?,?,?,'draft')",(pid,now(),prompt,caption,hashtags))
    return pid

def update_post(pid, **fields):
    allowed={"status","image_path","image_uri","video_path","video_uri","ig_media_id","scheduled_at","error","caption","hashtags"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:return
    sql=", ".join(f"{k}=?" for k in fields)
    with db() as c:c.execute(f"UPDATE posts SET {sql} WHERE id=?",(*fields.values(),pid))

def upload_gcs(local_path: str, object_name: str) -> str:
    bucket_name=setting("GOOGLE_CLOUD_STORAGE_BUCKET")
    if not bucket_name: return ""
    from google.cloud import storage
    client=storage.Client(project=setting("GOOGLE_CLOUD_PROJECT") or None)
    blob=client.bucket(bucket_name).blob(object_name)
    blob.upload_from_filename(local_path)
    return f"gs://{bucket_name}/{object_name}"

def download_gcs(uri: str, destination: str):
    from google.cloud import storage
    path=uri.removeprefix("gs://")
    bucket, name=path.split("/",1)
    storage.Client(project=setting("GOOGLE_CLOUD_PROJECT") or None).bucket(bucket).blob(name).download_to_filename(destination)

def generate_portrait(prompt: str) -> bytes:
    from google import genai
    from google.genai import types
    key=setting("GEMINI_API_KEY")
    if not key: raise RuntimeError("Add GEMINI_API_KEY in Streamlit Secrets.")
    client=genai.Client(api_key=key)
    response=client.models.generate_content(
        model=setting("GEMINI_IMAGE_MODEL","gemini-3.1-flash-image"),
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE","TEXT"]),
    )
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part,"inline_data",None):
                return part.inline_data.data
    raise RuntimeError("The image model returned no image. Check model access and billing.")

def google_access_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request
    credentials,_=google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    return credentials.token

def generate_video(prompt: str, reference_uri: str) -> str:
    project=setting("GOOGLE_CLOUD_PROJECT")
    if not project: raise RuntimeError("Set GOOGLE_CLOUD_PROJECT in Streamlit Secrets.")
    if not reference_uri.startswith("gs://"): raise RuntimeError("A GCS reference image is required. Set GOOGLE_CLOUD_STORAGE_BUCKET and upload the portrait.")
    token=google_access_token()
    url=f"https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/global/interactions"
    body={
      "model":setting("GEMINI_VIDEO_MODEL","gemini-omni-1.2-flash"),
      "background":True,
      "input":[{"type":"text","text":prompt+" Use the supplied portrait as the identity reference. Preserve the same adult influencer's face, hair and defining features."},
               {"type":"image","uri":reference_uri,"mime_type":"image/jpeg"}],
      "response_format":[{"type":"video","delivery":"uri","gcs_uri":f"gs://{setting('GOOGLE_CLOUD_STORAGE_BUCKET')}/generated/","aspect_ratio":"9:16","resolution":"720p","duration":"8s"}]
    }
    r=requests.post(url,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},json=body,timeout=90)
    r.raise_for_status()
    interaction=r.json()
    iid=interaction["id"]
    poll=f"{url}/{iid}"
    for _ in range(80):
        time.sleep(10)
        result=requests.get(poll,headers={"Authorization":f"Bearer {token}"},timeout=60)
        result.raise_for_status()
        data=result.json()
        if data.get("status")=="completed":
            for step in data.get("steps",[]):
                if step.get("type")=="model_output":
                    for part in step.get("content",[]):
                        if part.get("type")=="video" and part.get("uri"): return part["uri"]
            raise RuntimeError("Video completed but no output URI was returned.")
        if data.get("status") in ("failed","cancelled"): raise RuntimeError(json.dumps(data))
    raise TimeoutError("Video generation is still processing. Try again later.")

def ig_request(method,path,params=None):
    token=setting("INSTAGRAM_ACCESS_TOKEN")
    if not token: raise RuntimeError("Add INSTAGRAM_ACCESS_TOKEN in Streamlit Secrets.")
    base=setting("INSTAGRAM_API_BASE_URL","https://graph.instagram.com").rstrip("/")
    p=dict(params or {}); p["access_token"]=token
    response=requests.request(method,f"{base}/{path.lstrip('/')}",params=p if method=="GET" else None,data=p if method!="GET" else None,timeout=60)
    if not response.ok: raise RuntimeError(response.text[:1200])
    return response.json()

def publish_reel(post):
    igid=setting("INSTAGRAM_USER_ID")
    if not igid: raise RuntimeError("Add INSTAGRAM_USER_ID in Streamlit Secrets.")
    video_url=post.get("video_uri","")
    if not video_url.startswith("https://"): raise RuntimeError("Instagram needs a publicly accessible HTTPS video URL. Configure public GCS delivery or a public media CDN.")
    container=ig_request("POST",f"{igid}/media",{"media_type":"REELS","video_url":video_url,"caption":post["caption"]+"\n\n"+post["hashtags"]})
    cid=container["id"]
    for _ in range(30):
        time.sleep(5)
        status=ig_request("GET",cid,{"fields":"status_code"})
        if status.get("status_code")=="FINISHED": break
        if status.get("status_code")=="ERROR": raise RuntimeError("Instagram rejected the video processing.")
    result=ig_request("POST",f"{igid}/media_publish",{"creation_id":cid})
    return result["id"]

def fetch_insights(media_id):
    data=ig_request("GET",f"{media_id}/insights",{"metric":"views,reach,likes,comments,shares,saved"})
    values={x["name"]:int(x.get("values",[{}])[0].get("value",0)) for x in data.get("data",[])}
    return values

init_db()
p=profile()
st.markdown("<style>.block-container{padding-top:2rem;max-width:1250px}.hero{padding:1.2rem 1.4rem;border:1px solid rgba(128,128,128,.25);border-radius:18px}</style>",unsafe_allow_html=True)
with st.sidebar:
    st.title("✨ Influencer Studio")
    page=st.radio("Workspace",["Dashboard","Create content","My influencer","Publishing & analytics","Setup"])
    st.caption("Your AI creator workspace")

if page=="Dashboard":
    st.title("Your creator studio")
    st.markdown(f"<div class='hero'><h2>Welcome back</h2><p>Build consistent short-form content for <b>{p['name']}</b>.</p></div>",unsafe_allow_html=True)
    items=posts()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Total drafts",len(items)); c2.metric("Videos ready",sum(bool(x["video_uri"] or x["video_path"]) for x in items)); c3.metric("Published",sum(x["status"]=="published" for x in items)); c4.metric("Needs review",sum(x["status"] in ("draft","ready","failed") for x in items))
    st.subheader("Recent content")
    for item in items[:5]:
        with st.container(border=True):
            st.write(f"**{item['created_at'][:10]} · {item['status'].title()}**")
            st.write(item["caption"])
            if item["video_path"] and Path(item["video_path"]).exists(): st.video(item["video_path"])
            elif item["image_path"] and Path(item["image_path"]).exists(): st.image(item["image_path"],width=240)
    st.info("Start in **My influencer** to save a reusable portrait, then create your first short video.")

elif page=="My influencer":
    st.title("Your influencer identity")
    st.write("Save one fictional adult persona and keep using its reference portrait in future content.")
    with st.form("profile"):
        name=st.text_input("Creator name",p["name"])
        niche=st.text_input("Niche",p["niche"])
        bio=st.text_area("Bio",p["bio"])
        persona=st.text_area("Identity description",p["persona"],help="Describe stable features, age 25+, hairstyle, skin tone, and personality.")
        save=st.form_submit_button("Save profile",type="primary")
    if save:
        save_profile(name,niche,bio,persona); st.success("Profile saved."); st.rerun()
    if p.get("reference_path") and Path(p["reference_path"]).exists(): st.image(p["reference_path"],caption="Saved reference portrait",width=300)
    st.subheader("Create or upload reference portrait")
    portrait_prompt=st.text_area("Portrait prompt",f"Photorealistic studio portrait of a fictional adult woman aged 25 or older. {p['persona']} Niche: {p['niche']}. Neutral uncluttered background, front-facing, natural light, consistent recognizable identity, head and shoulders.")
    c1,c2=st.columns(2)
    with c1:
        if st.button("Generate AI portrait",type="primary"):
            try:
                with st.spinner("Generating portrait..."):
                    raw=generate_portrait(portrait_prompt)
                    path=MEDIA_DIR/"influencer_reference.png"; path.write_bytes(raw)
                    uri=upload_gcs(str(path),"references/influencer_reference.png")
                    save_profile(name,niche,bio,persona,str(path),uri or "")
                st.success("Portrait saved as your reusable identity reference."); st.rerun()
            except Exception as e: st.error(str(e))
    with c2:
        uploaded=st.file_uploader("Or upload an existing portrait",type=["png","jpg","jpeg"])
        if uploaded and st.button("Save uploaded portrait"):
            try:
                img=Image.open(BytesIO(uploaded.getvalue())).convert("RGB")
                path=MEDIA_DIR/"influencer_reference.jpg"; img.save(path,quality=92)
                uri=upload_gcs(str(path),"references/influencer_reference.jpg")
                save_profile(name,niche,bio,persona,str(path),uri or "")
                st.success("Reference portrait saved."); st.rerun()
            except Exception as e: st.error(str(e))
    if p.get("reference_uri"): st.caption(f"Cloud reference: {p['reference_uri']}")

elif page=="Create content":
    st.title("Create an Instagram video")
    st.caption("Generate a concept and caption, then create a vertical video using your saved influencer portrait.")
    if not p.get("reference_path") or not Path(p["reference_path"]).exists():
        st.warning("Create or upload your influencer portrait first in My influencer.")
    topic=st.text_input("Video idea",placeholder="e.g. 3 easy summer outfit ideas")
    scene=st.text_area("What should happen in the video?", "The influencer smiles at the camera, walks naturally toward the camera, and shows the outfit in a bright modern studio. Natural motion, realistic hands, no text overlays.")
    duration=st.select_slider("Video length",options=["5 seconds","8 seconds","10 seconds","12 seconds","15 seconds"],value="8 seconds")
    if st.button("Create video",type="primary",disabled=not (p.get("reference_path") and Path(p["reference_path"]).exists())):
        try:
            with st.spinner("Preparing your video job..."):
                prompt=f"Create a vertical 9:16 Instagram Reel, {duration}. {scene} Topic: {topic}. Use the supplied reference image as the same adult influencer. Keep face, hair, age and identity consistent. High-quality social video, smooth natural motion, no captions, no logos."
                caption=f"{topic.strip().capitalize() or 'A little inspiration for today'} ✨"
                hashtags="#AIInfluencer #VirtualCreator #Lifestyle #Reels"
                pid=save_post(prompt,caption,hashtags)
                ref_uri=p.get("reference_uri","")
                if not ref_uri: ref_uri=upload_gcs(p["reference_path"],"references/influencer_reference.jpg")
                if not ref_uri: raise RuntimeError("Set GOOGLE_CLOUD_STORAGE_BUCKET and configure Google Cloud credentials to use image-referenced video generation.")
                video_uri=generate_video(prompt,ref_uri)
                local=MEDIA_DIR/f"{pid}.mp4"; download_gcs(video_uri,str(local))
                update_post(pid,status="ready",video_path=str(local),video_uri=video_uri)
            st.success("Your video is ready. Review it under Publishing & analytics.")
            st.video(str(local))
        except Exception as e:
            if "pid" in locals(): update_post(pid,status="failed",error=str(e))
            st.error(str(e))
    st.divider()
    st.subheader("Saved videos")
    for item in posts():
        if item["video_path"] and Path(item["video_path"]).exists():
            with st.expander(f"{item['created_at'][:10]} · {item['status']} · {item['id']}"):
                st.video(item["video_path"]); st.write(item["caption"])

elif page=="Publishing & analytics":
    st.title("Publishing & performance")
    items=posts()
    ready=[x for x in items if x.get("video_path") and Path(x["video_path"]).exists()]
    if not ready: st.info("Create a video first.")
    for item in ready:
        with st.container(border=True):
            st.write(f"**{item['created_at'][:10]} · {item['status'].title()}**")
            st.video(item["video_path"])
            caption=st.text_area("Caption",item["caption"],key=f"cap_{item['id']}")
            hashtags=st.text_input("Hashtags",item["hashtags"],key=f"hash_{item['id']}")
            if st.button("Save caption",key=f"save_{item['id']}"):
                update_post(item["id"],caption=caption,hashtags=hashtags); st.success("Saved.")
            if item["status"]!="published":
                if st.button("Publish Reel now",key=f"publish_{item['id']}",type="primary"):
                    try:
                        update_post(item["id"],caption=caption,hashtags=hashtags)
                        mid=publish_reel({**item,"caption":caption,"hashtags":hashtags})
                        update_post(item["id"],status="published",ig_media_id=mid,error="")
                        st.success(f"Published to Instagram. Media ID: {mid}"); st.rerun()
                    except Exception as e:
                        update_post(item["id"],error=str(e)); st.error(str(e))
            else:
                st.success(f"Published · Instagram media ID {item['ig_media_id']}")
                if st.button("Refresh insights",key=f"insights_{item['id']}"):
                    try:
                        vals=fetch_insights(item["ig_media_id"])
                        with db() as c:c.execute("INSERT INTO metrics(post_id,fetched_at,views,reach,likes,comments,shares,saves) VALUES(?,?,?,?,?,?,?,?)",(item["id"],now(),vals.get("views",0),vals.get("reach",0),vals.get("likes",0),vals.get("comments",0),vals.get("shares",0),vals.get("saved",0)))
                        st.success("Insights refreshed."); st.rerun()
                    except Exception as e: st.error(str(e))
                with db() as c: m=c.execute("SELECT * FROM metrics WHERE post_id=? ORDER BY fetched_at DESC LIMIT 1",(item["id"],)).fetchone()
                if m:
                    cols=st.columns(5)
                    for col,label,key in zip(cols,["Views","Reach","Likes","Comments","Shares"],["views","reach","likes","comments","shares"]): col.metric(label,m[key])
                    st.metric("Saves",m["saves"])

elif page=="Setup":
    st.title("Connect your services")
    st.write("Add credentials in Streamlit Cloud → App → Settings → Secrets, or in a local .streamlit/secrets.toml file. Never paste private keys into GitHub.")
    st.subheader("Google Cloud video and storage")
    st.code('''GOOGLE_CLOUD_PROJECT = "your-project-id"
GOOGLE_CLOUD_STORAGE_BUCKET = "your-public-or-accessible-bucket"
GEMINI_API_KEY = "your-gemini-api-key"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_VIDEO_MODEL = "gemini-omni-1.2-flash"''',language="toml")
    st.markdown("Enable Vertex AI and Cloud Storage APIs, configure Application Default Credentials / a service account for the app, grant it Vertex AI User and Storage Object Admin (or narrower equivalent) permissions, and create the bucket. The video model runs through Google Cloud Agent Platform; a Gemini API key alone is not enough.")
    st.subheader("Instagram")
    st.code('''INSTAGRAM_API_BASE_URL = "https://graph.instagram.com"
INSTAGRAM_ACCESS_TOKEN = "your-instagram-user-access-token"
INSTAGRAM_USER_ID = "your-instagram-professional-account-id"''',language="toml")
    st.markdown("Use an Instagram Creator or Business account and complete Meta's Instagram API login, permissions, and app review requirements. Reels publishing requires a publicly reachable HTTPS video URL. If your bucket is private, configure a public delivery layer or CDN before publishing.")
    st.subheader("Readiness")
    checks=[("Gemini API key",bool(setting("GEMINI_API_KEY"))),("Google Cloud project",bool(setting("GOOGLE_CLOUD_PROJECT"))),("Cloud Storage bucket",bool(setting("GOOGLE_CLOUD_STORAGE_BUCKET"))),("Instagram token",bool(setting("INSTAGRAM_ACCESS_TOKEN"))),("Instagram account ID",bool(setting("INSTAGRAM_USER_ID")))]
    for label,ok in checks: st.write(("✅ " if ok else "⬜ ")+label)
    st.warning("This starter stores app records and downloaded media on the app filesystem. For hosted production, move SQLite/media to managed persistent storage and use a secret manager. Do not expose the dashboard publicly without authentication.")
