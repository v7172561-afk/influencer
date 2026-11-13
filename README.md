# AI Influencer Studio

Streamlit creator workspace with Google OIDC sign-in and Instagram Login OAuth. Each signed-in user has a separate SQLite database and media directory and connects their own Instagram Creator or Business account. Instagram tokens are encrypted at rest. There is no shared Instagram access token or account ID.

## Streamlit Secrets

Add these in Streamlit Cloud → App settings → Secrets. Never commit credentials.

```toml
[auth]
redirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"
cookie_secret = "GENERATE-A-LONG-RANDOM-SECRET"
client_id = "YOUR-GOOGLE-OIDC-CLIENT-ID"
client_secret = "YOUR-GOOGLE-OIDC-CLIENT-SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

GOOGLE_API_KEY = "your-gemini-api-key"
HF_ACCESS_KEY = "HFAK..."
HF_SECRET_KEY = "your-hugging-face-s3-secret"
HF_ENDPOINT = "https://varun20014k.s3.hf.co"
HF_BUCKET = "animedubhindi-storage"
HF_REGION = "us-east-1"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_VIDEO_MODEL = "gemini-omni-1.1-flash"

INSTAGRAM_APP_ID = "YOUR_META_APP_ID"
INSTAGRAM_APP_SECRET = "YOUR_META_APP_SECRET"
INSTAGRAM_REDIRECT_URI = "https://YOUR-APP.streamlit.app"
TOKEN_ENCRYPTION_KEY = "YOUR_FERNET_KEY"
```

Generate a Fernet key locally:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Meta configuration
Add Instagram API with Instagram Login to the Meta app, register the exact Instagram redirect URI, configure required Instagram Login permissions for basic profile access and content publishing, and complete Meta app review/Advanced Access before public launch. Add the Meta app ID and secret to Streamlit Secrets. The OIDC callback and Instagram redirect URI are different.

## Local development
Install requirements and run `streamlit run app.py`. Register `http://localhost:8501/oauth2callback` as the Google OIDC redirect and `http://localhost:8501` as the Instagram redirect for local testing.

## Production notes
Per-user separation currently uses a SQLite file and local media directory per user. Streamlit hosted local disk may reset; use managed PostgreSQL and object storage before public launch. Add token refresh/revocation, key rotation, and validate current Meta scopes/endpoints before opening to public users. Gemini generation remains subject to account model access, quota, and billing.
