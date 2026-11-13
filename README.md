# AI Influencer Studio

Streamlit workspace for a fictional adult AI influencer. Gemini generates a reusable portrait and short reference-led videos; a private Hugging Face Storage Bucket stores the media; Instagram publishing and insights are available after Meta setup.

## Features
- Creator profile and reusable reference portrait.
- Gemini image generation or portrait upload.
- Gemini Omni Flash image-referenced video generation.
- Private media storage in Hugging Face Storage Buckets using the S3-compatible API.
- Instagram Reels publishing and supported post insights.

## Streamlit Secrets
Add these in Streamlit App settings -> Secrets. Never commit real credentials to GitHub.

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

## Architecture
Hugging Face is the durable private media store; Gemini is the generation service. This removes Google Cloud Storage and Google Cloud service-account credentials from the app. Hugging Face bucket access uses the namespace S3 endpoint, path-style addressing, region us-east-1 and checksum settings required by its gateway. Instagram receives a one-hour presigned HTTPS URL for each private video; test Meta's ability to fetch that URL before production use.

SQLite and the app's local cache are lightweight development storage. Hosted local disk may be reset, so use managed PostgreSQL for production metadata. Video generation depends on model availability, account eligibility, quota and billing. Instagram publishing requires a professional account, Meta app permissions and a valid access token.

## Run locally
Python 3.11+:

    pip install -r requirements.txt
    streamlit run app.py

Create .streamlit/secrets.toml locally using the settings above. Never commit it.

## References
- https://huggingface.co/docs/hub/storage-buckets-s3
- https://ai.google.dev/gemini-api/docs/omni
- https://ai.google.dev/gemini-api/docs/image-generation
- https://developers.facebook.com/docs/instagram-platform/
