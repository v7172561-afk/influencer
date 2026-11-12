# One AI Influencer Studio

A free-first starter app for **one fictional adult AI influencer**. It creates a daily content draft (caption, hashtags, image prompt), stores it for review, lets the owner upload the final image, and publishes an approved image post to one Instagram professional Creator account through Meta's official API.

## Current MVP scope

- One influencer profile, with realistic and animated style options.
- AI-generated captions and visual prompts using Groq (or a local template fallback when no Groq key is configured).
- Human approval before publishing.
- Image-post publishing through Instagram Login / Instagram Platform.
- Supabase Postgres for persistence and a public Supabase Storage bucket for media.
- GitHub Actions hourly tick to generate one draft per day and publish approved posts when due.
- A password gate for the owner dashboard.

**Not included yet:** automatic image/video generation, Reels publishing, OAuth connect flow inside the app, automated DMs/comments, follower automation, or guaranteed exact-time scheduling. The first release asks you to upload the final image. This keeps image generation free by using a local tool or your own existing image workflow.

## 1. Run locally

Use Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

The app works in local/demo mode without credentials: it uses a template content draft and saves to local SQLite. Add credentials for AI generation and actual Instagram publishing.

For local environment variables, export them in your shell or load them with your preferred dotenv runner. Streamlit deployments should use Streamlit Secrets.

## 2. Configure persistent database and media storage

Create a free Supabase project:

1. Create a Postgres project.
2. Copy a connection URI into `DATABASE_URL` (use the Supabase pooler URI where appropriate).
3. Create a Storage bucket named `influencer-media`.
4. Set the bucket to **public**. Meta needs to fetch the public image URL when publishing.
5. Put `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_BUCKET=influencer-media` in secrets.

The service-role key is highly privileged. Keep it only in server-side secrets (Streamlit Secrets and GitHub Actions Secrets); never expose it in browser code or commit it to GitHub. Use this one-owner app privately.

If `DATABASE_URL` is empty, the app uses `data/influencer.db` (SQLite). That is suitable for local development only. Filesystems on hosted app/runner environments are not shared or durable; hosted deployment needs Supabase Postgres so the dashboard and Actions worker see the same records.

## 3. Configure Groq (optional, but needed for AI-generated drafts)

Create a Groq API key and set:

```toml
GROQ_API_KEY = "your-key"
GROQ_MODEL = "openai/gpt-oss-20b"
```

The model and free allowance can change. Check your Groq console for current model availability and rate limits. Without a key, the app generates a simple template draft; the scheduled automation skips AI draft generation.

## 4. Configure Instagram publishing

This starter expects an Instagram Login access token and Instagram professional account ID to be provisioned in Meta's developer tools. It does not implement the OAuth login/callback flow.

1. Convert/operate the Instagram account as a **Creator** or Business professional account.
2. Create a Meta developer app and configure the Instagram API with Instagram Login.
3. Grant the `instagram_business_basic` and `instagram_business_content_publish` permissions required by your setup. Complete Meta app review/verification when Meta requires it for the access level you need.
4. Obtain the Instagram user access token and Instagram professional account ID.
5. Set these secrets:

```toml
INSTAGRAM_ACCESS_TOKEN = "..."
INSTAGRAM_USER_ID = "..."
INSTAGRAM_API_BASE_URL = "https://graph.instagram.com"
META_GRAPH_VERSION = "v27.0"
```

Meta versions its API. `v27.0` is the version configured when this starter was prepared (November 2026); verify the current supported version in Meta's changelog before deployment and update `META_GRAPH_VERSION` as needed.

Publishing images is a two-step operation: create a media container, wait for processing, then publish it. The media image must be publicly reachable over HTTPS. This starter uploads images to a public Supabase Storage bucket and passes that URL to Meta.

The API can only manage eligible professional accounts and permitted interactions. It does not provide unrestricted control of Instagram. App roles, permissions and review requirements depend on whether the app is in development or live mode and who is using it.

## 5. Deploy the dashboard to Streamlit Community Cloud

1. Push this project to a private GitHub repository.
2. Open https://share.streamlit.io and create an app from that repository.
3. Set the main file to `app.py`.
4. In App settings → Secrets, add the values from `.streamlit/secrets.toml.example`.
5. Make sure `DASHBOARD_PASSWORD` is a strong password.
6. Keep the app access restricted to you if the app contains private tokens or account controls.

Streamlit Community Cloud is the dashboard host only. Its app can hibernate after 12 hours without traffic; do not use it as the scheduler.

## 6. Configure GitHub Actions scheduler

In your GitHub repository, open Settings → Secrets and variables → Actions → New repository secret. Add:

- `GROQ_API_KEY`
- `GROQ_MODEL` (optional)
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`

The workflow `.github/workflows/automation.yml` runs hourly and can also be started manually from Actions → AI influencer automation → Run workflow. It:

- creates one daily draft if no draft exists for the current date;
- publishes posts only if they are approved, scheduled, and have a public media URL.

GitHub scheduled workflows may be delayed and are not a guaranteed real-time scheduler. You must approve each draft in the Streamlit dashboard before it can publish. Use **Publish now** in the dashboard for a manual publish after approval.

## 7. Daily operating procedure

1. Open the dashboard.
2. Check today's generated draft (the worker creates it on its next scheduled run, or use Create daily draft manually).
3. Generate the visual from the image prompt using your own image workflow or local ComfyUI.
4. Upload the JPG/PNG in Approval queue. With Supabase configured, the file is uploaded to the public bucket.
5. Review the image and caption, then click Approve post.
6. The worker publishes it when its scheduled time is due. Or click Publish now.
7. Review the published status in the dashboard.

For the selected frequency of one post per day, the automation makes at most one draft per local calendar day. It does not publish unless you approve it.

## 8. Important free-tier and safety notes

- Free-tier quotas and conditions change. Check the providers' current pricing/limits before relying on a quota.
- Streamlit Community Cloud has shared CPU/RAM limits and hibernates inactive apps.
- Supabase free projects may pause after inactivity and have capped database/storage/egress quotas.
- GitHub Actions scheduled runs can be delayed. A free-only setup is not suitable for guaranteed exact-time or mission-critical posting.
- AI image generation is not provided by Groq text generation. Local image generation requires your own computer/GPU; cloud image/video generation may cost money.
- The starter generates prompts but does not automatically scrape Instagram or automate follows/likes/engagement.
- Use a fictional adult persona; do not impersonate a real person. Label virtual/AI content transparently where appropriate, follow Instagram's policies, and review commercial claims before publishing.

## 9. Troubleshooting

- **No Groq generation:** check `GROQ_API_KEY`, `GROQ_MODEL`, model access and rate limits.
- **Image won't publish:** verify the Supabase bucket is public, the URL opens without login, the image is JPG/PNG, and your token has the correct publish permission.
- **Meta permission error:** check account type, Instagram Login setup, token scope, app mode/review, and account ID.
- **App data missing on Streamlit:** configure `DATABASE_URL`; SQLite on an ephemeral host is not persistent.
- **Actions cannot see records:** ensure GitHub Actions has the same `DATABASE_URL` and Supabase credentials as Streamlit.

## References

- Streamlit Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud
- Streamlit app limits/hibernation: https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
- Meta Instagram API: https://developers.facebook.com/docs/instagram-platform/
- Meta Instagram publishing collection: https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
- Groq rate limits: https://console.groq.com/docs/rate-limits
- Supabase pricing: https://supabase.com/pricing
- GitHub Actions limits: https://docs.github.com/en/actions/reference/limits
