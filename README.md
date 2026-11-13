# AI Influencer Studio

A Streamlit workspace for building a fictional adult AI influencer, saving a reusable portrait reference, generating vertical videos with Gemini Omni Flash on Google Cloud Agent Platform, and publishing approved Reels to Instagram with performance insights.

## Features

- Creator profile with a persistent identity description and reference portrait.
- Generate a portrait with Gemini image generation or upload your own.
- Reuse the saved portrait as an image reference for future vertical video generations.
- Generate short 9:16 videos with `gemini-omni-1.2-flash`.
- Review videos and captions before publishing.
- Publish Reels through the official Instagram API.
- Refresh per-post views, reach, likes, comments, shares and saves where the account/API exposes them.
- Local SQLite metadata store for development.

## Run locally

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

For local secrets, create `.streamlit/secrets.toml` from the examples in the Setup page. Do not commit credentials.

## Google setup

The image generation step uses the Gemini API through `GEMINI_API_KEY`. Video generation uses Google Cloud Agent Platform's Interactions API and requires a Google Cloud project with Vertex AI enabled, Application Default Credentials (or a service account), and a Cloud Storage bucket.

1. Create/select a Google Cloud project.
2. Enable Vertex AI and Cloud Storage APIs.
3. Create a Cloud Storage bucket.
4. Configure the Streamlit runtime identity with Vertex AI User and permissions to read/write the bucket.
5. Set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_STORAGE_BUCKET`, and `GEMINI_API_KEY`.
6. The app uploads the portrait reference and generated video to the configured bucket.

The video model identifier is `gemini-omni-1.2-flash`. Google documents this model for text- and image-referenced video generation via the Agent Platform Interactions API. Check current regional availability, quotas, and billing before production use.

## Instagram setup

Use an Instagram Creator or Business professional account. Create/configure a Meta developer app for Instagram API, obtain an eligible user access token and professional account ID, and grant the required publishing and insights permissions. Add:

```toml
INSTAGRAM_API_BASE_URL = "https://graph.instagram.com"
INSTAGRAM_ACCESS_TOKEN = "..."
INSTAGRAM_USER_ID = "..."
```

Instagram publishing requires a publicly reachable HTTPS video URL. This starter returns a `gs://` URI from Cloud Storage; configure public object delivery or a CDN and update `publish_reel` to use that HTTPS URL before publishing. Do not make a bucket public unless you understand the exposure implications.

## Important deployment notes

- Local SQLite and the local `data/` folder are for development; ephemeral hosting may erase them. Use managed PostgreSQL and durable object storage for a production multi-session deployment.
- Streamlit Community Cloud does not automatically have Google Cloud service-account credentials. Configure workload identity/service-account credentials securely in the host environment.
- Meta permissions, app review, token expiry and insights availability depend on the account and app mode.
- AI video generation and cloud storage may incur charges. Review provider pricing and quotas.
- Use a fictional adult persona; do not impersonate a real person. Follow Instagram's rules and disclose synthetic media where appropriate.

## References

- [Gemini Omni video generation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-references)
- [Gemini image generation models](https://ai.google.dev/gemini-api/docs/models)
- [Instagram Platform](https://developers.facebook.com/docs/instagram-platform/)
