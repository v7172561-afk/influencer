# AI Influencer Studio

An open Streamlit AI creator studio. Visitors can open the app and start generating fictional adult AI influencer portraits, model images, and vertical videos without signing in to Google or Instagram. A private browser workspace stores their drafts. Instagram connection is optional and is requested only when the user wants to publish Reels or view account insights.

## Features
- Create or edit a reusable fictional adult influencer profile.
- Generate an AI portrait or upload a reference portrait.
- Generate AI model images from custom prompts.
- Generate vertical short videos using the saved influencer reference.
- Generate social captions and hashtags with Gemini.
- Preview and download generated images; preview generated videos.
- Keep a content library and review drafts.
- Optionally configure your own Meta Instagram app credentials in Setup, connect an Instagram Creator or Business account, publish Reels and retrieve available insights.
- A built-in **How to use** guide explains the complete workflow with examples and setup instructions.
- Per-browser guest workspaces and per-workspace media prefixes in Hugging Face storage.

## Streamlit Secrets

Add these in Streamlit Cloud → App settings → Secrets. Never commit credentials.

```toml
GOOGLE_API_KEY = "your-gemini-api-key"
HF_ACCESS_KEY = "HFAK..."
HF_SECRET_KEY = "your-hugging-face-s3-secret"
HF_ENDPOINT = "https://varun20014k.s3.hf.co"
HF_BUCKET = "animedubhindi-storage"
HF_REGION = "us-east-1"
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_VIDEO_MODEL = "gemini-omni-1.1-flash"
GEMINI_TEXT_MODEL = "gemini-2.5-flash"

# Optional: only needed for Instagram publishing and insights
INSTAGRAM_APP_ID = "YOUR_META_APP_ID"
INSTAGRAM_APP_SECRET = "YOUR_META_APP_SECRET"
INSTAGRAM_REDIRECT_URI = "https://YOUR-APP.streamlit.app"
TOKEN_ENCRYPTION_KEY = "YOUR_FERNET_KEY"
```

Generate a Fernet key locally:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
For local Instagram OAuth testing, set the redirect URI to `http://localhost:8501` and register that exact URI in the Meta app. Instagram is not needed to use image or video generation.

## Instagram publishing
1. Add Instagram API with Instagram Login to your Meta developer app.
2. Register the exact redirect URI.
3. Configure required Instagram Login permissions for basic account access, content publishing, and insights where supported.
4. Complete Meta App Review and Advanced Access before allowing general public users to connect.
5. Add the four optional Instagram settings above.

## Important limitations before public launch
- Guest workspace identity is stored in a browser cookie. Clearing cookies or using another browser/device starts a new workspace. This is not a full registered-user account system.
- Streamlit local disk and SQLite files may reset or are not shared between multiple app instances. Move session state, projects, and generated media metadata to managed persistent storage (e.g. PostgreSQL plus object storage) before production.
- Instagram OAuth token refresh/revocation and public app review must be fully tested. Publishing requires a publicly reachable video URL; private bucket delivery must be tested end-to-end with Meta.
- Gemini models, video generation methods, quotas, and billing depend on the Google AI account and model availability. Check the configured model IDs against the models enabled for your API key.
- The app code has been updated, but end-to-end image/video generation and Instagram publishing still require testing with your actual service credentials and deployed Streamlit app.

## Visitor API key settings

The Setup page lets each visitor enter their own Gemini API key, optional Hugging Face S3 access/secret keys, and Instagram Meta App ID, App Secret and Redirect URI. Keys are masked in the form and stored in that visitor's Streamlit session memory, overriding app-owner defaults for that session. Visitors can inspect whether the app owner has configured service credentials and remove their own keys.

These visitor-entered keys are not stored in GitHub or a shared database, but this is session-only storage: keys can be lost when the Streamlit session expires, reconnects, or the app restarts. Do not describe this as permanent encrypted storage. Before a public production launch, use authenticated user accounts and encrypted per-user secrets in a managed secret store.

Instagram passwords and raw personal access tokens are not accepted in the form. Visitors may supply their own Meta App ID, App Secret and Redirect URI in Setup; those credentials are kept in that visitor's Streamlit session memory and are not saved in GitHub or a shared database. The exact redirect URI must also be registered in the Meta developer app. Visitors then connect their own Instagram Creator/Business account using OAuth. For a public production service, the operator should use managed persistent storage and a dedicated secure secret-management design rather than session-only visitor credentials.


## Website guide

The sidebar's **How to use** page explains the creator workflow: service setup, influencer profile and reference portrait, AI model image generation, vertical video generation, captions and hashtags, content library, optional Instagram publishing, and the currently available Instagram media insights. It includes example prompts and clearly distinguishes supported insights from features that are not currently implemented.
