# AI Influencer Studio

Streamlit AI creator workspace with **Instagram Login as the only sign-in method**. Users authorize their own Instagram professional account; the Instagram account ID identifies a separate workspace, database, media folder, and encrypted access token. No Google sign-in is required.

## Streamlit Secrets

Add these in Streamlit Cloud → App settings → Secrets. Never commit credentials.

```toml
INSTAGRAM_APP_ID = "YOUR_META_APP_ID"
INSTAGRAM_APP_SECRET = "YOUR_META_APP_SECRET"
INSTAGRAM_REDIRECT_URI = "https://YOUR-APP.streamlit.app"
TOKEN_ENCRYPTION_KEY = "YOUR_FERNET_KEY"

GOOGLE_API_KEY = "your-gemini-api-key"
HF_ACCESS_KEY = "HFAK..."
HF_SECRET_KEY = "your-hugging-face-s3-secret"
HF_ENDPOINT = "https://varun20014k.s3.hf.co"
HF_BUCKET = "animedubhindi-storage"
HF_REGION = "us-east-1"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_VIDEO_MODEL = "gemini-omni-1.1-flash"
```

Generate the token-encryption key locally:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Instagram Login setup
1. In Meta for Developers, add the Instagram API product and configure **Instagram Login**.
2. Register the exact redirect URI from `INSTAGRAM_REDIRECT_URI` in the Instagram Login settings.
3. Configure the Instagram Login permissions needed by the features you use, including basic profile access, content publishing, and insights where supported.
4. Complete Meta App Review and Advanced Access requirements before allowing accounts outside your app roles to use the service.
5. Copy the Meta App ID and App Secret into Streamlit Secrets.

The app redirects users to Instagram to authorize. It validates a one-time OAuth state, exchanges the authorization code, encrypts the long-lived access token, and creates a random browser session cookie. The Instagram account ID maps the user to a separate workspace. The browser cookie contains only a random session identifier, not the Instagram access token.

## Other services
Gemini and Hugging Face credentials above remain required for AI generation and media storage. These are app-level service credentials, not user login credentials.

## Local development
Run `pip install -r requirements.txt` and `streamlit run app.py`. For local Meta testing, set `INSTAGRAM_REDIRECT_URI = "http://localhost:8501"` and register that exact URI in the Meta app.

## Production notes
This version uses SQLite files and local media directories per Instagram account, plus a shared local SQLite authentication/session database. Streamlit-hosted local disk may reset and is not a robust multi-instance production session store. Before public launch, move session/OAuth state to managed PostgreSQL or Redis and tenant data to managed PostgreSQL/object storage. Add token refresh/revocation, key rotation, monitoring, rate limiting, and verify current Meta OAuth scopes and API requirements. Reels publishing also requires a publicly fetchable HTTPS video URL. Gemini generation remains subject to model access, quotas, and billing.
