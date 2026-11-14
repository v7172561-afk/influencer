# AI Influencer Studio

An open Streamlit AI creator studio. Visitors can open the app and generate fictional adult AI influencer portraits, model images, and short videos without signing in to Google or Instagram. Image generation uses the public FLUX.1 Schnell Hugging Face ZeroGPU Space; video generation uses the public Wan 2.2 Fast image-to-video Space. A private browser workspace stores their drafts. Instagram connection is optional and is requested only when the user wants to publish Reels or view account insights.

## Features
- Create or edit a reusable fictional adult influencer profile.
- Generate AI portraits and model images with FLUX.1 Schnell via Hugging Face ZeroGPU.
- Generate short image-to-video clips with Wan 2.2 Fast via Hugging Face ZeroGPU; text-only requests first create an opening image with FLUX.
- Generate enhanced social captions and hashtags with optional Gemini; without Gemini, the app uses a simple built-in caption template.
- Preview and download generated images; preview generated videos.
- Keep a content library and review drafts.
- Optionally configure your own Meta Instagram app credentials in Setup, connect an Instagram Creator or Business account, publish Reels and retrieve available insights.
- A built-in **How to use** guide explains the complete workflow with examples and setup instructions.
- Per-browser guest workspaces and per-workspace media prefixes in Hugging Face storage.

## Streamlit Secrets

Add these in Streamlit Cloud → App settings → Secrets. Never commit credentials.

```toml
HF_TOKEN = "hf_your_hugging_face_read_token"
# Optional: Gemini is used only for enhanced captions and hashtags
GOOGLE_API_KEY = "your-gemini-api-key"
HF_ACCESS_KEY = "HFAK..."
HF_SECRET_KEY = "your-hugging-face-s3-secret"
HF_ENDPOINT = "https://varun20014k.s3.hf.co"
HF_BUCKET = "animedubhindi-storage"
HF_REGION = "us-east-1"
GEMINI_TEXT_MODEL = "gemini-3.1-flash"

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
- Hugging Face ZeroGPU is shared, quota-limited demo infrastructure, not unlimited production GPU hosting. The current free Hugging Face account allowance is 5 GPU minutes per account per day; unauthenticated traffic has a smaller 2-minute daily allowance. All app visitors share the app owner's HF_TOKEN quota because generation runs server-side using the one deployment token. Queue delays, quota exhaustion, Space maintenance or endpoint changes can temporarily prevent generation. See the [official ZeroGPU quota documentation](https://huggingface.co/docs/hub/en/spaces-zerogpu).
- Every Space has a Gradio API. This app calls the public [FLUX.1 Schnell Space](https://huggingface.co/spaces/black-forest-labs/FLUX.1-schnell) and [Wan 2.2 Fast Space](https://huggingface.co/spaces/zerogpu-aoti/wan2-2-fp8da-aoti-faster) through the supported [Spaces API](https://huggingface.co/docs/hub/en/spaces-api-endpoints). The public Space owners may change their availability, API or limits; no uptime guarantee is provided.
- FLUX.1 Schnell's model card identifies Apache-2.0 licensing and commercial use. Wan2.2-I2V-A14B is listed as Apache-2.0. Review upstream model and Space terms before commercial deployment.
- The app code has been updated, but end-to-end image/video generation and Instagram publishing still require testing with your actual service credentials and deployed Streamlit app.

## Visitor API key settings

The Setup page shows whether the hidden Hugging Face ZeroGPU token is configured. Set `HF_TOKEN` in Streamlit Cloud → App settings → Secrets; it is used only by the server and is not displayed to visitors. The optional Gemini key is used only for enhanced captions. Visitors may still enter optional Hugging Face S3 access/secret keys and their own Instagram Meta App ID, App Secret and Redirect URI.

Visitor-entered optional keys are not stored in GitHub or a shared database; they are session-only and can be lost when the Streamlit session expires, reconnects, or the app restarts. The deployment-level HF_TOKEN is stored in Streamlit Secrets, not in client-side session state. Before a public production launch, use durable managed infrastructure and usage-aware per-tenant quota controls.

Instagram passwords and raw personal access tokens are not accepted in the form. Visitors may supply their own Meta App ID, App Secret and Redirect URI in Setup; those credentials are kept in that visitor's Streamlit session memory and are not saved in GitHub or a shared database. The exact redirect URI must also be registered in the Meta developer app. Visitors then connect their own Instagram Creator/Business account using OAuth. For a public production service, the operator should use managed persistent storage and a dedicated secure secret-management design rather than session-only visitor credentials.


## Website guide

The sidebar's **How to use** page explains the creator workflow: service setup, influencer profile and reference portrait, AI model image generation, vertical video generation, captions and hashtags, content library, optional Instagram publishing, and the currently available Instagram media insights. It includes example prompts and clearly distinguishes supported insights from features that are not currently implemented.
