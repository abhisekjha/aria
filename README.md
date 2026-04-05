# Aria — AI Sales Chief of Staff for Auralix

Aria finds and converts CPG companies into paying Auralix customers.
Runs overnight on GitHub Actions. Costs ~$3/month. Requires 15 min/day from you.

## What Aria does while you sleep

- Finds 10 new CPG prospects nightly (Apollo.io)
- Researches each one (company, retailers, pain signals)
- Scores and ranks them (hot/warm/cold)
- Sends you a morning email: tap Approve/Reject from your phone
- Sends approved cold emails automatically
- Emails you LinkedIn copy-paste content (10 min of your time)
- Monitors your inbox every 2 hours for replies
- Classifies replies and alerts you instantly when someone is interested
- Drafts suggested responses — you tap Send or reply yourself
- Sends follow-ups on day 3, 10, 17 automatically
- Generates a pre-meeting brief 60 min before every demo
- Sends you a Monday morning summary

## Setup (one time, ~30 minutes)

### 1. Accounts you need (all free)

- [ ] [Apollo.io](https://apollo.io) — free account → get API key
- [ ] [Airtable](https://airtable.com) — free account → get API key + base ID
- [ ] [Cal.com](https://cal.com) — free account → create "Auralix Demo" event → get booking link
- [ ] [Railway](https://railway.app) — free account → deploy the webhook server
- [ ] Gmail account for sending (use a separate one, not your main)
- [ ] GitHub repo (this repo)

### 2. Gmail setup

1. Go to Google Account → Security → 2-Step Verification → App Passwords
2. Create app password for "Mail" → copy the 16-char password
3. Set `GMAIL_APP_PASSWORD` to that password
4. For inbox reading: create OAuth2 credentials in Google Cloud Console
   (Gmail API, Desktop app type) → download JSON → set as `GMAIL_OAUTH_CREDENTIALS`

### 3. Environment variables

Copy `.env.example` to `.env` and fill in all values:
```bash
cp .env.example .env
```

### 4. GitHub Secrets

Add all vars from `.env` to GitHub repo → Settings → Secrets → Actions.

### 5. Deploy webhook server to Railway

```bash
# In Railway dashboard:
# 1. New Project → Deploy from GitHub repo
# 2. Set root directory to: aria/approval/
# 3. Set start command: uvicorn server:app --host 0.0.0.0 --port $PORT
# 4. Add all env vars
# 5. Copy the Railway URL → set as RAILWAY_WEBHOOK_URL
```

### 6. Test the pipeline

```bash
pip install -r requirements.txt
python scripts/test_run.py
```

### 7. First real run

Set `DRY_RUN=false` in GitHub Secrets, then:
- Go to GitHub Actions → "Aria Nightly Pipeline" → Run workflow
- Check your email in ~10 minutes for the morning digest

## Cost

| Item | Cost |
|------|------|
| Claude API | ~$3/month |
| Everything else | $0 |
| **Total** | **~$3/month** |

## File structure

```
aria/
├── aria/
│   ├── graph.py          ← main pipeline orchestrator
│   ├── state.py          ← data models
│   ├── config.py         ← env var loading
│   ├── agents/           ← prospector, researcher, qualifier, outreach_writer, reply_handler, follow_up, demo_prep
│   ├── tools/            ← apollo, airtable, gmail, web_search, cal_com
│   ├── approval/         ← server, tokens, email_digest
│   ├── prompts/          ← Claude prompt templates
│   └── utils/            ← logger, rate_limiter
├── tests/                ← pytest tests
├── scripts/              ← test_run.py, weekly_summary.py
└── .github/workflows/    ← nightly, reply_monitor, weekly_summary
```
