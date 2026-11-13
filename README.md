# AI Influencer Studio

Streamlit workspace for a fictional adult AI influencer. Gemini generates reusable portraits and short reference-led videos; a private Hugging Face Storage Bucket stores media; Instagram publishing and insights are available after Meta setup.

## Streamlit Secrets
Add to Streamlit App settings -> Secrets. Never commit real credentials to GitHub.

    GOOGLE_API_KEY = "your-gemini-api-key"
    HF_ACCESS_KEY = "HFAK..."
    HF_SECRET_KEY = "your-hugging-face-s3-secret"
    HF_ENDPOINT = "https://varun20014k.s3.hf.co"
    HF_BUCKET = "animedubhindi-storage"
    HF_REGION = "us-east-1"
    GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
    GEMINI_VIDEO_MODEL = "gemini-omni-1.1-flash"

Optional Instagram settings:

    INSTAGRAM_API_BASE_URL = "https://graph.instagram.com"
    INSTAGRAM_ACCESS_TOKEN = "your-instagram-user-access-token"
    INSTAGRAM_USER_ID = "your-instagram-professional-account-id"

Hugging Face stores private media; Gemini generates images and videos. No Google Cloud Storage bucket or service-account credential is required by this app. The Hugging Face S3 gateway requires the namespace endpoint, us-east-1, path-style addressing, and checksum settings. Instagram publishing uses a temporary signed URL for private videos; verify Meta can fetch it before relying on publishing.

SQLite is lightweight metadata storage. Streamlit hosted local disk can reset, so use managed PostgreSQL for production. Video generation depends on model availability, account eligibility, quotas and billing. Instagram publishing requires a professional account, Meta app configuration, permissions and a valid token.

## Run locally
Python 3.11+: install requirements with `pip install -r requirements.txt`, then run `streamlit run app.py`. Create `.streamlit/secrets.toml` locally from the settings above. Never commit it.

## References
- https://huggingface.co/docs/hub/storage-buckets-s3
- https://ai.google.dev/gemini-api/docs/omni
- https://ai.google.dev/gemini-api/docs/image-generation
- https://developers.facebook.com/docs/instagram-platform/
