from __future__ import annotations

import json, os, sqlite3, time, uuid, hashlib, secrets, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests
import boto3
from botocore.config import Config
import base64
import streamlit as st
import extra_streamlit_components as stx
from PIL import Image
from io import BytesIO
from cryptography.fernet import Fernet

APP_DIR = Path(__file__).parent
AUTH_DIR = APP_DIR / "data"
AUTH_DIR.mkdir(parents=True, exist_ok=True)
AUTH_DB = AUTH_DIR / "auth.sqlite3"
SESSION_COOKIE = "influencer_studio_session"
OAUTH_STATE_COOKIE = "influencer_instagram_oauth_state"

st.set_page_config(page_title="Influencer Studio", page_icon="✨", layout="wide")

def setting(key: str, default: str = "") -> str:
    try:
        visitor_secrets=st.session_state.get("visitor_api_secrets",{})
        if visitor_secrets.get(key):
            return str(visitor_secrets[key])
    except Exception:
        pass
    try:
        value = st.secrets.get(key, os.getenv(key, default))
    except Exception:
        value = os.getenv(key, default)
    return str(value or default)

def auth_db():
    con = sqlite3.connect(AUTH_DB)
    con.row_factory = sqlite3.Row
    return con

def init_auth_db():
    with auth_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS oauth_states(state_hash TEXT PRIMARY KEY, created_at REAL NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS sessions(session_hash TEXT PRIMARY KEY, instagram_user_id TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS guest_usage(id INTEGER PRIMARY KEY AUTOINCREMENT, guest_id TEXT NOT NULL, kind TEXT NOT NULL, created_at REAL NOT NULL)")

def create_oauth_state():
    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    with auth_db() as c:
        c.execute("DELETE FROM oauth_states WHERE created_at < ?", (time.time()-600,))
        c.execute("INSERT INTO oauth_states(state_hash, created_at) VALUES(?, ?)", (digest, time.time()))
    return state

def consume_oauth_state(state):
    if not state:
        return False
    digest = hashlib.sha256(state.encode()).hexdigest()
    with auth_db() as c:
        row = c.execute("SELECT created_at FROM oauth_states WHERE state_hash=?", (digest,)).fetchone()
        c.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest,))
    return bool(row and float(row["created_at"]) >= time.time()-600)

def create_browser_session(instagram_user_id):
    raw = secrets.token_urlsafe(40)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    now_ts = time.time()
    expiry = now_ts + 30*24*60*60
    with auth_db() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now_ts,))
        c.execute("INSERT INTO sessions(session_hash, instagram_user_id, created_at, expires_at) VALUES(?, ?, ?, ?)", (digest, str(instagram_user_id), now_ts, expiry))
    return raw

def resolve_browser_session(raw):
    if not raw:
        return None
    digest = hashlib.sha256(str(raw).encode()).hexdigest()
    with auth_db() as c:
        row = c.execute("SELECT instagram_user_id FROM sessions WHERE session_hash=? AND expires_at>?", (digest, time.time())).fetchone()
    return str(row["instagram_user_id"]) if row else None

def revoke_browser_session(raw):
    if not raw:
        return
    digest = hashlib.sha256(str(raw).encode()).hexdigest()
    with auth_db() as c:
        c.execute("DELETE FROM sessions WHERE session_hash=?", (digest,))

def check_generation_limit(kind):
    limits={"image":5,"video":2}
    limit=limits.get(kind,3)
    cutoff=time.time()-86400
    with auth_db() as c:
        c.execute("DELETE FROM guest_usage WHERE created_at < ?",(cutoff-86400,))
        count=c.execute("SELECT COUNT(*) FROM guest_usage WHERE guest_id=? AND kind=? AND created_at>=?",(guest_id,kind,cutoff)).fetchone()[0]
        if count>=limit:
            raise RuntimeError(f"Daily guest limit reached: {limit} {kind} generations per browser workspace. Try again later.")
        c.execute("INSERT INTO guest_usage(guest_id,kind,created_at) VALUES(?,?,?)",(guest_id,kind,time.time()))

def configure_workspace(instagram_user_id):
    global tenant, DATA_DIR, MEDIA_DIR, DB
    tenant = hashlib.sha256(("instagram:"+str(instagram_user_id)).encode()).hexdigest()[:24]
    DATA_DIR = AUTH_DIR / tenant
    MEDIA_DIR = DATA_DIR / "media"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    DB = DATA_DIR / "studio.db"

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
        CREATE TABLE IF NOT EXISTS instagram_connections(id INTEGER PRIMARY KEY CHECK(id=1), instagram_user_id TEXT, username TEXT, encrypted_token TEXT, expires_at TEXT, connected_at TEXT);
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

def hf_client():
    access = setting("HF_ACCESS_KEY")
    secret_key = setting("HF_SECRET_KEY")
    if not access or not secret_key:
        raise RuntimeError("Add HF_ACCESS_KEY and HF_SECRET_KEY in Streamlit Secrets.")
    return boto3.client(
        "s3",
        endpoint_url=setting("HF_ENDPOINT", "https://varun20014k.s3.hf.co"),
        aws_access_key_id=access,
        aws_secret_access_key=secret_key,
        config=Config(
            region_name=setting("HF_REGION", "us-east-1"),
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )

def hf_bucket():
    return setting("HF_BUCKET", "animedubhindi-storage")

def upload_gcs(local_path: str, object_name: str) -> str:
    hf_client().upload_file(local_path, hf_bucket(), object_name)
    return f"hf://{hf_bucket()}/{object_name}"

def download_gcs(uri: str, destination: str):
    if not uri.startswith("hf://"):
        raise RuntimeError("This media item is not stored in the configured Hugging Face bucket.")
    bucket_name, key = uri.removeprefix("hf://").split("/", 1)
    hf_client().download_file(bucket_name, key, destination)

def generate_portrait(prompt: str, aspect_ratio: str = "4:5") -> bytes:
    check_generation_limit("image")
    from google import genai
    from google.genai import types
    key=setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY")
    if not key: raise RuntimeError("Add GEMINI_API_KEY in Streamlit Secrets.")
    client=genai.Client(api_key=key)
    response=client.models.generate_content(
        model=setting("GEMINI_IMAGE_MODEL","gemini-3.1-flash-image"),
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE","TEXT"],image_config=types.ImageConfig(aspect_ratio=aspect_ratio)),
    )
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part,"inline_data",None):
                return part.inline_data.data
    raise RuntimeError("The image model returned no image. Check model access and billing.")

def generate_social_copy(topic: str, media_type: str = "Reel") -> dict:
    from google import genai
    from google.genai import types
    key=setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Add GOOGLE_API_KEY in Streamlit Secrets to generate captions.")
    client=genai.Client(api_key=key)
    response=client.models.generate_content(
        model=setting("GEMINI_TEXT_MODEL","gemini-3.1-flash"),
        contents=f"Create social media copy for a fictional adult AI influencer. Topic: {topic}. Format: {media_type}. Return concise JSON only with keys title, caption, hashtags. Caption should sound natural and engaging, include a clear hook, and avoid claiming the person is real. Hashtags should be 5-10 relevant hashtags as a space-separated string.",
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        result=json.loads(response.text or "{}")
    except Exception:
        result={}
    return {"title":str(result.get("title") or topic[:70]),"caption":str(result.get("caption") or topic),"hashtags":str(result.get("hashtags") or "#AIInfluencer #VirtualCreator #Reels")}

def google_access_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request
    credentials,_=google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    return credentials.token

def generate_video(prompt: str, reference_uri: str = "", local_reference_path: str = "") -> bytes:
    check_generation_limit("video")
    client=__import__("google.genai",fromlist=["Client"]).Client(api_key=setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY"))
    if reference_uri or local_reference_path:
        if reference_uri.startswith("hf://"):
            local_ref=MEDIA_DIR/"video_reference_source"
            download_gcs(reference_uri,str(local_ref))
        elif local_reference_path and Path(local_reference_path).exists():
            local_ref=Path(local_reference_path)
        else:
            raise RuntimeError("The saved reference portrait is unavailable. Please upload it again.")
        with Image.open(local_ref) as source:
            image_buffer=BytesIO()
            source.convert("RGB").save(image_buffer,format="JPEG",quality=95)
            image_bytes=image_buffer.getvalue()
        image_b64=base64.b64encode(image_bytes).decode("ascii")
        input_payload=[
            {"type":"image","data":image_b64,"mime_type":"image/jpeg"},
            {"type":"text","text":prompt+" The person in <IMAGE_REF_0> is the same fictional adult influencer. Preserve her facial identity, hairstyle and overall appearance while animating the described scene."},
        ]
        task="image_to_video"
    else:
        input_payload=prompt+" Create an original vertical short video featuring fictional adult characters."
        task="text_to_video"
    interaction=client.interactions.create(
        model=setting("GEMINI_VIDEO_MODEL","gemini-omni-1.1-flash"),
        input=input_payload,
        response_format={"type":"video","aspect_ratio":"9:16"},
        generation_config={"video_config":{"task":task}},
    )
    video=getattr(interaction,"output_video",None)
    data=getattr(video,"data",None) if video else None
    if not data:
        raise RuntimeError("Gemini returned no video. Confirm gemini-omni-1.1-flash is enabled for your API key and check quota/billing.")
    return base64.b64decode(data)

def token_cipher():
    key=setting("TOKEN_ENCRYPTION_KEY")
    if not key:
        app_secret=setting("INSTAGRAM_APP_SECRET")
        if not app_secret:
            raise RuntimeError("Add your Instagram App Secret in Setup, or configure TOKEN_ENCRYPTION_KEY in deployment secrets.")
        material=hashlib.sha256((app_secret+"|"+str(guest_id)+"|influencer-studio").encode()).digest()
        key=base64.urlsafe_b64encode(material).decode()
    return Fernet(key.encode())

def get_instagram_connection():
    with db() as c: row=c.execute("SELECT * FROM instagram_connections WHERE id=1").fetchone()
    if not row: return None
    item=dict(row)
    try:
        item["access_token"]=token_cipher().decrypt(item["encrypted_token"].encode()).decode()
    except Exception:
        # Visitor-supplied app secrets are session-only; an expired session can make
        # an old encrypted token unreadable. Do not crash the whole creator studio.
        with db() as c: c.execute("DELETE FROM instagram_connections WHERE id=1")
        return None
    return item

def save_instagram_connection(user_id,username,access_token,expires_in):
    expiry=datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+int(expires_in or 0),timezone.utc).isoformat()
    encrypted=token_cipher().encrypt(access_token.encode()).decode()
    with db() as c:
        c.execute("INSERT INTO instagram_connections(id,instagram_user_id,username,encrypted_token,expires_at,connected_at) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET instagram_user_id=excluded.instagram_user_id,username=excluded.username,encrypted_token=excluded.encrypted_token,expires_at=excluded.expires_at,connected_at=excluded.connected_at",(str(user_id),username,encrypted,expiry,now()))

def instagram_auth_url(state):
    app_id=setting("INSTAGRAM_APP_ID")
    redirect=setting("INSTAGRAM_REDIRECT_URI")
    if not app_id or not redirect:
        raise RuntimeError("Set INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET and INSTAGRAM_REDIRECT_URI in Streamlit Secrets.")
    scopes="instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"
    params={"client_id":app_id,"redirect_uri":redirect,"response_type":"code","scope":scopes,"state":state,"enable_fb_login":"0"}
    return "https://www.instagram.com/oauth/authorize?"+urllib.parse.urlencode(params)

def finish_instagram_auth(code):
    app_id=setting("INSTAGRAM_APP_ID")
    app_secret=setting("INSTAGRAM_APP_SECRET")
    redirect=setting("INSTAGRAM_REDIRECT_URI")
    if not app_id or not app_secret or not redirect:
        raise RuntimeError("Instagram OAuth settings are missing from Streamlit Secrets.")
    response=requests.post("https://api.instagram.com/oauth/access_token",data={"client_id":app_id,"client_secret":app_secret,"grant_type":"authorization_code","redirect_uri":redirect,"code":code},timeout=30)
    if not response.ok: raise RuntimeError(response.text[:1000])
    short=response.json()
    long=requests.get("https://graph.instagram.com/access_token",params={"grant_type":"ig_exchange_token","client_secret":app_secret,"access_token":short["access_token"]},timeout=30)
    if not long.ok: raise RuntimeError(long.text[:1000])
    token=long.json()
    me=requests.get("https://graph.instagram.com/me",params={"fields":"user_id,username","access_token":token["access_token"]},timeout=30)
    if not me.ok: raise RuntimeError(me.text[:1000])
    identity=me.json()
    instagram_user_id=identity.get("user_id") or identity.get("id") or short.get("user_id")
    if not instagram_user_id:
        raise RuntimeError("Instagram did not return a professional account ID.")
    return str(instagram_user_id), identity.get("username","Instagram creator"), token["access_token"], token.get("expires_in",short.get("expires_in",0))

def ig_request(method,path,params=None):
    connection=get_instagram_connection()
    if not connection: raise RuntimeError("Connect your Instagram account first.")
    p=dict(params or {}); p["access_token"]=connection["access_token"]
    response=requests.request(method,f"https://graph.instagram.com/{path.lstrip('/')}",params=p if method=="GET" else None,data=p if method!="GET" else None,timeout=60)
    if not response.ok: raise RuntimeError(response.text[:1200])
    return response.json()

def publish_reel(post):
    connection=get_instagram_connection()
    if not connection: raise RuntimeError("Connect your Instagram account first.")
    igid=connection["instagram_user_id"]
    video_url=post.get("video_uri","")
    if video_url.startswith("hf://"):
        bucket_name, object_key = video_url.removeprefix("hf://").split("/", 1)
        video_url = hf_client().generate_presigned_url("get_object", Params={"Bucket": bucket_name, "Key": object_key}, ExpiresIn=3600)
    if not video_url.startswith("https://"): raise RuntimeError("Instagram needs an HTTPS media URL.")
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

init_auth_db()
cookie_manager = stx.CookieManager(key="influencer_guest_cookie")
browser_cookies = cookie_manager.get_all()
if browser_cookies is None:
    st.info("Preparing your creator workspace…")
    st.stop()
session_token = str(browser_cookies.get(SESSION_COOKIE) or "")
guest_id = resolve_browser_session(session_token)
if not guest_id:
    guest_id = "guest_" + secrets.token_urlsafe(24)
    session_token = create_browser_session(guest_id)
    cookie_manager.set(SESSION_COOKIE,session_token,key="create_guest_workspace",expires_at=datetime.now(timezone.utc)+timedelta(days=30),max_age=30*24*60*60,path="/",secure=True,same_site="lax")
    st.rerun()
configure_workspace(guest_id)
init_db()
# Instagram is optional. Users can generate media before connecting it.
if st.query_params.get("error"):
    st.error("Instagram connection was not completed: " + str(st.query_params.get("error_description") or st.query_params.get("error")))
    st.query_params.clear()
elif st.query_params.get("code"):
    returned_state=str(st.query_params.get("state",""))
    browser_state=str(browser_cookies.get(OAUTH_STATE_COOKIE) or "")
    valid=bool(browser_state and secrets.compare_digest(returned_state,browser_state) and consume_oauth_state(returned_state))
    if not valid:
        st.error("Instagram connection expired or could not be verified. Please try again.")
    else:
        try:
            instagram_user_id,username,access_token,expires_in=finish_instagram_auth(str(st.query_params.get("code")))
            save_instagram_connection(instagram_user_id,username,access_token,expires_in)
            cookie_manager.delete(OAUTH_STATE_COOKIE,key="clear_instagram_state")
            st.success(f"Connected Instagram account @{username}.")
        except Exception as exc:
            st.error(f"Instagram connection failed: {exc}")
    st.query_params.clear()
connection=get_instagram_connection()
p=profile()
st.markdown("""<style>
.block-container{padding-top:1.5rem;max-width:1450px}
[data-testid="stSidebar"]{border-right:1px solid rgba(128,128,128,.18)}
.hero{padding:1.8rem 2rem;border:1px solid rgba(128,128,128,.22);border-radius:22px;background:linear-gradient(120deg,rgba(124,92,255,.16),rgba(36,180,170,.08))}
div[data-testid="stMetric"]{padding:.9rem;border:1px solid rgba(128,128,128,.18);border-radius:16px}
.stButton>button,.stLinkButton>a{border-radius:12px;font-weight:600}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px}
</style>""",unsafe_allow_html=True)
with st.sidebar:
    st.title("✨ Influencer Studio")
    page=st.radio("Studio",["Dashboard","How to use","Create content","My influencer","Publishing & analytics","Setup"])
    st.caption("Private workspace · this browser")
    if connection:
        st.success(f"Instagram: @{connection.get('username') or connection['instagram_user_id']}")
    else:
        st.caption("Instagram connection is optional.")

if page=="Dashboard":
    st.title("Your creator studio")
    st.markdown(f"<div class='hero'><h1>✨ Your AI Creator Studio</h1><p>Create a virtual influencer, generate model images and vertical videos, then publish when you are ready.</p><b>Creator: {p['name']}</b></div>",unsafe_allow_html=True)
    items=posts()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Content created",len(items)); c2.metric("Videos ready",sum(bool(x["video_uri"] or x["video_path"]) for x in items)); c3.metric("Model images",sum(bool(x["image_uri"] or x["image_path"]) for x in items)); c4.metric("Published",sum(x["status"]=="published" for x in items))
    st.subheader("Recent content")
    for item in items[:5]:
        with st.container(border=True):
            st.write(f"**{item['created_at'][:10]} · {item['status'].title()}**")
            st.write(item["caption"])
            if item["video_path"] and Path(item["video_path"]).exists(): st.video(item["video_path"])
            elif item["image_path"] and Path(item["image_path"]).exists(): st.image(item["image_path"],width=240)
    st.info("Start in **My influencer** to save a reusable portrait, then create your first short video.")

elif page=="How to use":
    st.title("How to use Influencer Studio")
    st.write("A guided tour of the main tools, with examples of what each step does. Explore the app without connecting Instagram.")
    st.subheader("The complete creator workflow")
    st.markdown("**1. Set up services → 2. Create your influencer → 3. Generate images and videos → 4. Review content → 5. Connect Instagram and publish → 6. Check available insights.**")
    st.divider()
    with st.container(border=True):
        st.subheader("1 · Setup: connect the services you want")
        st.markdown("- **Gemini API key:** powers AI portraits, model images, video generation and social captions.\n- **Hugging Face storage (optional):** stores media in your S3-compatible bucket. Without it, files stay in the current app workspace and may not persist on Streamlit Cloud.\n- **Instagram app credentials:** your Meta developer app's ID, secret and exact redirect URI are used for Instagram OAuth. Instagram is optional.")
        st.info("Demo: Setup shows whether each service is configured. This guide does not create fake API connections or sample analytics.")
    with st.container(border=True):
        st.subheader("2 · My influencer: build a consistent virtual creator")
        st.markdown("Choose a creator name, niche, bio and stable identity description. Generate a reference portrait with Gemini or upload an image. The saved portrait can guide future video generations.")
        st.code("Example identity: fictional adult creator, age 25+, warm confident personality, shoulder-length dark hair, natural expressions.",language="text")
    with st.container(border=True):
        st.subheader("3 · Create content: make images, videos and captions")
        st.markdown("- **AI model image:** enter an idea and prompt, then choose Portrait 4:5, Square 1:1 or Story 9:16. Suggested caption and hashtags are generated too.\n- **AI video:** describe the scene and select your saved portrait or a generated image as reference, or choose text-to-video.\n- **Download:** preview and download generated media.")
        st.code("Image idea: editorial streetwear photoshoot in Tokyo\nVideo idea: 3 easy summer outfit ideas\nScene: creator walks toward camera and shows the outfit.",language="text")
    with st.container(border=True):
        st.subheader("4 · Dashboard and content library")
        st.markdown("The Dashboard summarizes content in this browser workspace and shows recent creations. Create content includes saved videos; Publishing & analytics lists publishable media and lets you edit captions and hashtags.")
        st.caption("This is a browser workspace, not a full registered-user account system. Clearing cookies or losing local app storage can affect access.")
    with st.container(border=True):
        st.subheader("5 · Instagram publishing (optional)")
        st.markdown("Connect an eligible Instagram Creator or Business account through Instagram's official authorization screen. Never enter your Instagram password here. Review the caption and hashtags, then use **Publish Reel now** on a ready video.")
        st.warning("Publishing requires a properly configured Meta developer app, matching redirect URI, required permissions and any applicable Meta review/Advanced Access.")
    with st.container(border=True):
        st.subheader("6 · Publishing & analytics")
        st.markdown("After a Reel is published, use **Refresh insights** to request metrics exposed by Instagram's API for that media item, such as views, reach, likes, comments, shares and saves when supported.")
        st.info("This is not a full copy of Instagram's in-app Professional Dashboard. Audience demographics, follower trends and other metrics are not shown unless the connected API exposes them.")
    st.subheader("Quick start")
    st.markdown("1. Open **Setup** and add a Gemini key if needed.\n2. Open **My influencer** and save a profile plus reference portrait.\n3. Open **Create content** and generate an image or video.\n4. Open **Publishing & analytics** when you want to connect Instagram and publish.")

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
                    try:
                        uri=upload_gcs(str(path),f"users/{tenant}/references/influencer_reference.png")
                    except Exception:
                        uri=""
                    save_profile(name,niche,bio,persona,str(path),uri or "")
                st.success("Portrait saved as your reusable identity reference.")
                if not uri: st.info("Portrait saved in this browser workspace; cloud backup is not configured.")
                st.rerun()
            except Exception as e: st.error(str(e))
    with c2:
        uploaded=st.file_uploader("Or upload an existing portrait",type=["png","jpg","jpeg"])
        if uploaded and st.button("Save uploaded portrait"):
            try:
                img=Image.open(BytesIO(uploaded.getvalue())).convert("RGB")
                path=MEDIA_DIR/"influencer_reference.jpg"; img.save(path,quality=92)
                try:
                    uri=upload_gcs(str(path),f"users/{tenant}/references/influencer_reference.jpg")
                except Exception:
                    uri=""
                save_profile(name,niche,bio,persona,str(path),uri or "")
                st.success("Reference portrait saved.")
                if not uri: st.info("Portrait saved in this browser workspace; cloud backup is not configured.")
                st.rerun()
            except Exception as e: st.error(str(e))
    if p.get("reference_uri"): st.caption(f"Cloud reference: {p['reference_uri']}")

elif page=="Create content":
    st.title("Create with AI")
    st.caption("Make model images or vertical videos. Your files are saved in your workspace; Instagram is optional.")
    with st.container(border=True):
        st.subheader("Generate an AI model image")
        image_topic=st.text_input("Image idea",placeholder="e.g. luxury streetwear photoshoot in Tokyo",key="image_topic")
        image_prompt=st.text_area("Image prompt", "Create a high-quality editorial photograph of the same fictional adult AI influencer. Stylish outfit, natural realistic pose, detailed face and hands, premium lighting, clean composition. No text, watermark or logos.",key="image_prompt")
        image_format=st.selectbox("Image format",["Portrait 4:5","Square 1:1","Story 9:16"],key="image_format")
        if st.button("Generate model image",type="primary",key="generate_model_image",disabled=not bool(image_topic.strip())):
            try:
                full_prompt=f"{image_prompt} Concept: {image_topic}. Subject identity: {p['persona']}. Adult subject age 25 or older. Aspect ratio {image_format}. Keep identity consistent with the saved influencer reference description."
                with st.spinner("Creating your AI model image…"):
                    raw=generate_portrait(full_prompt, {"Portrait 4:5":"4:5","Square 1:1":"1:1","Story 9:16":"9:16"}[image_format])
                    copy=generate_social_copy(image_topic,"AI model image")
                    pid=save_post(full_prompt,copy["caption"],copy["hashtags"])
                    path=MEDIA_DIR/f"{pid}.png"
                    path.write_bytes(raw)
                    try:
                        uri=upload_gcs(str(path),f"users/{tenant}/images/{pid}.png")
                    except Exception:
                        uri=""
                    update_post(pid,status="ready",image_path=str(path),image_uri=uri)
                st.success("Your model image is ready.")
                if not uri: st.info("Image saved in this browser workspace. Configure Hugging Face for cloud backup.")
                st.image(raw,use_container_width=True)
                st.download_button("Download image",data=raw,file_name=f"ai-model-{pid}.png",mime="image/png")
                st.caption("Your image is saved in your content library below.")
            except Exception as exc:
                st.error(str(exc))
    st.divider()
    st.title("Create an Instagram video")
    st.caption("Generate a concept and caption, then create a vertical video using your saved influencer portrait.")
    saved_visuals=[x for x in posts() if x.get("image_path") and Path(x["image_path"]).exists()]
    reference_options={"No reference image (text-to-video)":""}
    if p.get("reference_path") and Path(p["reference_path"]).exists():
        reference_options["Saved influencer portrait"]=p["reference_path"]
    for visual in saved_visuals:
        reference_options[f"Generated image · {visual['created_at'][:10]} · {visual['id']}"]=visual["image_path"]
    selected_reference=st.selectbox("Visual reference for video",list(reference_options.keys()))
    selected_reference_path=reference_options[selected_reference]
    has_reference=bool(selected_reference_path)
    if not has_reference:
        st.info("Text-to-video mode selected. Choose your saved portrait or a generated model image to guide the video.")
    topic=st.text_input("Video idea",placeholder="e.g. 3 easy summer outfit ideas")
    scene=st.text_area("What should happen in the video?", "The influencer smiles at the camera, walks naturally toward the camera, and shows the outfit in a bright modern studio. Natural motion, realistic hands, no text overlays.")
    st.caption("Gemini Omni Flash currently chooses the generated clip length; use the prompt to guide pacing and scene complexity.")
    if st.button("Create video",type="primary"):
        try:
            with st.spinner("Preparing your video job..."):
                reference_instruction="Use the saved portrait as the same adult influencer and preserve her identity." if has_reference else "Create an original fictional adult character; no reference image is supplied."
                prompt=f"Create a vertical 9:16 short social video. {scene} Topic: {topic}. {reference_instruction} High-quality social video, smooth natural motion, no captions, no logos. Use a single continuous shot unless the scene specifically requires multiple shots."
                copy=generate_social_copy(topic or scene,"Reel")
                caption=copy["caption"]
                hashtags=copy["hashtags"]
                pid=save_post(prompt,caption,hashtags)
                ref_uri=p.get("reference_uri","") if has_reference else ""
                if has_reference and not ref_uri:
                    ref_uri=upload_gcs(p["reference_path"],f"users/{tenant}/references/influencer_reference.jpg")
                video_bytes=generate_video(prompt,ref_uri,p.get("reference_path","") if has_reference else "")
                local=MEDIA_DIR/f"{pid}.mp4"; local.write_bytes(video_bytes)
                try:
                    video_uri=upload_gcs(str(local),f"users/{tenant}/videos/{pid}.mp4")
                except Exception:
                    video_uri=""
                update_post(pid,status="ready",video_path=str(local),video_uri=video_uri)
            st.success("Your video is ready.")
            st.video(str(local))
            st.download_button("Download video",data=video_bytes,file_name=f"ai-reel-{pid}.mp4",mime="video/mp4")
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
    connection=get_instagram_connection()
    with st.container(border=True):
        st.subheader("Your Instagram account")
        if connection:
            st.success(f"Connected as @{connection.get('username') or connection['instagram_user_id']}")
            if st.button("Disconnect Instagram"):
                with db() as c: c.execute("DELETE FROM instagram_connections WHERE id=1")
                st.rerun()
        else:
            st.info("Create images and videos without Instagram. Connect an account only when you are ready to publish.")
            try:
                if "pending_instagram_state" not in st.session_state:
                    st.session_state["pending_instagram_state"]=create_oauth_state()
                state=st.session_state["pending_instagram_state"]
                cookie_manager.set(OAUTH_STATE_COOKIE,state,key="store_instagram_oauth_state",expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),max_age=600,path="/",secure=True,same_site="lax")
                st.link_button("Connect Instagram",instagram_auth_url(state),type="primary")
            except Exception as exc: st.error(str(exc))
    items=posts()
    ready=[x for x in items if (x.get("video_path") and Path(x["video_path"]).exists()) or (x.get("image_path") and Path(x["image_path"]).exists())]
    if not ready: st.info("Create an image or video first.")
    for item in ready:
        with st.container(border=True):
            st.write(f"**{item['created_at'][:10]} · {item['status'].title()}**")
            if item.get("video_path") and Path(item["video_path"]).exists():
                st.video(item["video_path"])
            elif item.get("image_path") and Path(item["image_path"]).exists():
                st.image(item["image_path"],use_container_width=True)
            caption=st.text_area("Caption",item["caption"],key=f"cap_{item['id']}")
            hashtags=st.text_input("Hashtags",item["hashtags"],key=f"hash_{item['id']}")
            if st.button("Save caption",key=f"save_{item['id']}"):
                update_post(item["id"],caption=caption,hashtags=hashtags); st.success("Saved.")
            if item["status"]=="published":
                st.success(f"Published · Instagram media ID {item.get('ig_media_id') or 'available'}")
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
            elif item.get("video_path") and Path(item["video_path"]).exists():
                if not connection:
                    st.info("Connect Instagram above when you are ready to publish this Reel.")
                if st.button("Publish Reel now",key=f"publish_{item['id']}",type="primary",disabled=not bool(connection)):
                    try:
                        update_post(item["id"],caption=caption,hashtags=hashtags)
                        mid=publish_reel({**item,"caption":caption,"hashtags":hashtags})
                        update_post(item["id"],status="published",ig_media_id=mid,error="")
                        st.success(f"Published to Instagram. Media ID: {mid}"); st.rerun()
                    except Exception as e:
                        update_post(item["id"],error=str(e)); st.error(str(e))
            elif item.get("image_path") and Path(item["image_path"]).exists():
                st.caption("Images can be downloaded and used in your social posts. Reel publishing is available for videos.")

elif page=="Setup":
    st.title("Your API keys & connections")
    st.caption("Add your own Gemini key, optional Hugging Face storage credentials, and Meta Instagram app credentials. Visitor-entered values stay in this active browser session.")
    app_gemini=bool(setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY"))
    app_hf=bool(setting("HF_ACCESS_KEY") and setting("HF_SECRET_KEY"))
    visitor_secrets=st.session_state.get("visitor_api_secrets",{})
    with st.container(border=True):
        st.subheader("Gemini API key")
        st.write("Use your own Google AI Studio key for image, video and caption generation.")
        with st.form("visitor_gemini_key_form"):
            gemini_input=st.text_input("Gemini API key",type="password",placeholder="Paste your API key")
            gemini_submit=st.form_submit_button("Save Gemini key",type="primary")
        if gemini_submit:
            if not gemini_input.strip():
                st.error("Paste a Gemini API key first.")
            else:
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                saved["GOOGLE_API_KEY"]=gemini_input.strip()
                st.session_state["visitor_api_secrets"]=saved
                st.success("Gemini key added for this session.")
                st.rerun()
        visitor_secrets=st.session_state.get("visitor_api_secrets",{})
        if visitor_secrets.get("GOOGLE_API_KEY"):
            st.success("Gemini key: your own key is active")
            if st.button("Remove my Gemini key",key="remove_visitor_gemini"):
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                saved.pop("GOOGLE_API_KEY",None)
                st.session_state["visitor_api_secrets"]=saved
                st.rerun()
        elif app_gemini:
            st.info("Gemini key: app owner's key is available")
        else:
            st.warning("Gemini key: not configured")

    with st.container(border=True):
        st.subheader("Hugging Face storage (optional)")
        st.write("Use your own S3-compatible bucket for storing generated media.")
        with st.form("visitor_hf_keys_form"):
            hf_access=st.text_input("Hugging Face access key",type="password",placeholder="HFAK…")
            hf_secret=st.text_input("Hugging Face secret key",type="password",placeholder="S3 secret")
            hf_endpoint=st.text_input("S3 endpoint",value=setting("HF_ENDPOINT","https://your-account.s3.hf.co"))
            hf_bucket=st.text_input("Bucket name",value=setting("HF_BUCKET",""))
            hf_submit=st.form_submit_button("Save storage credentials")
        if hf_submit:
            if not hf_access.strip() or not hf_secret.strip():
                st.error("Enter both storage keys.")
            else:
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                saved.update({"HF_ACCESS_KEY":hf_access.strip(),"HF_SECRET_KEY":hf_secret.strip()})
                if hf_endpoint.strip(): saved["HF_ENDPOINT"]=hf_endpoint.strip()
                if hf_bucket.strip(): saved["HF_BUCKET"]=hf_bucket.strip()
                st.session_state["visitor_api_secrets"]=saved
                st.success("Storage credentials added for this session.")
                st.rerun()
        visitor_secrets=st.session_state.get("visitor_api_secrets",{})
        if visitor_secrets.get("HF_ACCESS_KEY") and visitor_secrets.get("HF_SECRET_KEY"):
            st.success("Hugging Face: your credentials are active")
            if st.button("Remove my Hugging Face credentials",key="remove_visitor_hf"):
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                for key in ("HF_ACCESS_KEY","HF_SECRET_KEY","HF_ENDPOINT","HF_BUCKET","HF_REGION"):
                    saved.pop(key,None)
                st.session_state["visitor_api_secrets"]=saved
                st.rerun()
        elif app_hf:
            st.info("Hugging Face: app owner's storage credentials are available")
        else:
            st.caption("Optional. Without a bucket, files are stored only in the current app workspace.")

    with st.container(border=True):
        st.subheader("Instagram app credentials")
        st.write("Add credentials from your own Meta developer app. These values start and complete Instagram OAuth for your workspace.")
        with st.form("visitor_instagram_app_form"):
            ig_app_id=st.text_input("INSTAGRAM_APP_ID (Meta App ID)",placeholder="Your Meta App ID")
            ig_app_secret=st.text_input("INSTAGRAM_APP_SECRET (Meta App Secret)",type="password",placeholder="Paste your Meta App Secret")
            ig_redirect=st.text_input("INSTAGRAM_REDIRECT_URI",value=setting("INSTAGRAM_REDIRECT_URI"),placeholder="https://your-app.streamlit.app")
            ig_submit=st.form_submit_button("Save Instagram app settings",type="primary")
        if ig_submit:
            if not ig_app_id.strip() or not ig_app_secret.strip() or not ig_redirect.strip():
                st.error("Enter all three Instagram app settings.")
            elif not (ig_redirect.strip().startswith("https://") or ig_redirect.strip().startswith("http://localhost")):
                st.error("Use an HTTPS redirect URL (localhost is allowed for local development).")
            else:
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                saved.update({"INSTAGRAM_APP_ID":ig_app_id.strip(),"INSTAGRAM_APP_SECRET":ig_app_secret.strip(),"INSTAGRAM_REDIRECT_URI":ig_redirect.strip()})
                st.session_state["visitor_api_secrets"]=saved
                st.success("Instagram app settings saved in this browser session.")
                st.rerun()
        visitor_secrets=st.session_state.get("visitor_api_secrets",{})
        visitor_ig_ready=all(bool(visitor_secrets.get(k) or setting(k)) for k in ("INSTAGRAM_APP_ID","INSTAGRAM_APP_SECRET","INSTAGRAM_REDIRECT_URI"))
        if all(visitor_secrets.get(k) for k in ("INSTAGRAM_APP_ID","INSTAGRAM_APP_SECRET","INSTAGRAM_REDIRECT_URI")):
            st.success("Your Instagram app credentials are active for this session.")
            if st.button("Remove my Instagram app settings",key="remove_visitor_instagram"):
                saved=dict(st.session_state.get("visitor_api_secrets",{}))
                for key in ("INSTAGRAM_APP_ID","INSTAGRAM_APP_SECRET","INSTAGRAM_REDIRECT_URI"):
                    saved.pop(key,None)
                st.session_state["visitor_api_secrets"]=saved
                st.rerun()
        elif visitor_ig_ready:
            st.info("Instagram app settings are available from the website deployment.")
        else:
            st.warning("Instagram app settings are not complete yet.")
        with st.expander("Where do I get these values?"):
            st.markdown("1. Open [Meta for Developers](https://developers.facebook.com/) and create or select an app that supports Instagram API with Instagram Login.\n2. Add/configure Instagram Login and its OAuth redirect/callback settings.\n3. Copy the app's **App ID** and **App Secret** into the fields above.\n4. Set the redirect URI to your exact deployed app URL and register that exact same URL in Meta. Keep http/https and trailing slashes identical.\n5. Configure permissions for basic account access, content publishing and insights. Meta review/Advanced Access may be required before public users can connect.")
        st.caption("Never share your App Secret publicly or commit it to GitHub. Values entered here stay in Streamlit session memory only and may disappear when the session expires or the app restarts.")
        st.divider()
        st.subheader("Connect your Instagram account")
        st.write("App ID and Secret identify your Meta app. OAuth separately lets you authorize your Instagram Creator/Business account. Never enter your Instagram password here.")
        connection=get_instagram_connection()
        if connection:
            st.success(f"Connected Instagram: @{connection.get('username') or connection['instagram_user_id']}")
            if st.button("Disconnect Instagram from this workspace",key="disconnect_instagram_setup"):
                with db() as c: c.execute("DELETE FROM instagram_connections WHERE id=1")
                st.rerun()
        elif visitor_ig_ready:
            try:
                if "pending_instagram_state" not in st.session_state:
                    st.session_state["pending_instagram_state"]=create_oauth_state()
                state=st.session_state["pending_instagram_state"]
                cookie_manager.set(OAUTH_STATE_COOKIE,state,key="setup_instagram_oauth_state",expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),max_age=600,path="/",secure=True,same_site="lax")
                st.link_button("Connect Instagram securely",instagram_auth_url(state),type="primary")
            except Exception as exc:
                st.error(f"Could not start Instagram connection: {exc}")
        else:
            st.info("Complete the three app settings above to enable Instagram connection.")

    with st.container(border=True):
        st.subheader("Configuration status")
        visitor_secrets=st.session_state.get("visitor_api_secrets",{})
        gemini_ready=bool(visitor_secrets.get("GOOGLE_API_KEY") or setting("GOOGLE_API_KEY") or setting("GEMINI_API_KEY"))
        hf_ready=bool((visitor_secrets.get("HF_ACCESS_KEY") and visitor_secrets.get("HF_SECRET_KEY")) or (setting("HF_ACCESS_KEY") and setting("HF_SECRET_KEY")))
        instagram_ready=all(bool(setting(k)) for k in ("INSTAGRAM_APP_ID","INSTAGRAM_APP_SECRET","INSTAGRAM_REDIRECT_URI"))
        rows=[("Gemini generation",gemini_ready),("Hugging Face storage",hf_ready),("Instagram app settings",instagram_ready),("Instagram account",bool(get_instagram_connection()))]
        for label,ready in rows:
            st.write(("✅ " if ready else "○ ")+label)
    st.info("Your entered keys and Instagram app credentials are kept in Streamlit session memory only. They are not committed to GitHub or saved in a shared database, and may disappear when the session expires or the app restarts. Instagram OAuth tokens are encrypted in the workspace database; for production, use managed persistent storage and dedicated per-user secret management.")
