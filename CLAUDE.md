# CLAUDE.md — Aria: AI Sales Chief of Staff for Auralix
> Drop this file in the root of the `aria/` repo.
> Claude Code reads this automatically at the start of every session.
> Do not delete or edit manually.

---

## What Is Aria?

Aria is a private, internal AI sales automation system built for one purpose:
find and convert CPG companies into paying Auralix customers.

Aria is NOT a product. It is a personal tool run by the Auralix founder.
It runs overnight on GitHub Actions, costs ~$3/month (Claude API only),
and requires 15 minutes of human attention per day — via email on a phone.

**The single job**: Generate qualified demo meetings with CPG finance/deductions
leaders so Auralix can close its first 3-5 paying customers.

**The core contract with the human**:
- Aria does all research, writing, scheduling, and follow-up automatically
- The human ONLY makes two decisions: (1) which prospects to contact, (2) how
  to respond to positive replies
- Nothing goes out without human approval first
- Human approves by tapping a link in an email — no login required

---

## Product Context: What Is Auralix?

Auralix (auralix.ai) is a Trade Promotion Management (TPM) SaaS for CPG
companies. The core value proposition is deduction management — when retailers
like Walmart short-pay invoices, Auralix automatically processes the claims,
scores risk, generates evidence packs, and tracks dispute windows.

**Why this matters for Aria**: Every outreach message must lead with deduction
pain, not "AI trade promotion platform." The buyer is a Deductions Manager or
VP Finance sitting on hundreds of unresolved claims with 30-60 day dispute
windows. That is the pain. That is the hook.

---

## Ideal Customer Profile (ICP)

**Target company:**
- CPG manufacturer (food & beverage, personal care, household goods)
- Revenue: $50M–$500M
- Sells into 2+ major retailers (Walmart, Target, Kroger, Costco)
- Currently managing deductions in Excel or a legacy tool (not SAP TPM)

**Target person (in priority order):**
1. Deductions Manager / Director of Deductions
2. VP Finance / Director of Trade Finance
3. Controller
4. Trade Marketing Manager

**Disqualify if:**
- Already using SAP TPM, Salesforce TPM, or UpClear
- Revenue under $20M or over $1B
- Pure private label (no branded products)

---

## Repository Structure

```
aria/
├── CLAUDE.md                    ← this file (Claude Code reads on startup)
├── README.md                    ← setup instructions for humans
├── requirements.txt             ← all Python dependencies
├── .env.example                 ← all required env vars (no secrets)
├── .github/
│   └── workflows/
│       ├── nightly.yml          ← runs prospector + researcher + qualifier at 2am CT
│       ├── reply_monitor.yml    ← runs every 2 hours, checks Gmail for replies
│       └── weekly_summary.yml   ← runs every Monday 7am CT
├── aria/
│   ├── __init__.py
│   ├── graph.py                 ← LangGraph pipeline definition (main orchestrator)
│   ├── state.py                 ← TypedDict state schema for the entire graph
│   ├── config.py                ← loads env vars, validates on startup
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── prospector.py        ← Apollo.io API → raw prospect list
│   │   ├── researcher.py        ← Claude API → enriches each prospect
│   │   ├── qualifier.py         ← Claude API → scores 1-100, hot/warm/cold
│   │   ├── outreach_writer.py   ← Claude API → writes email + LinkedIn content
│   │   ├── reply_handler.py     ← Gmail API → reads inbox, Claude classifies
│   │   ├── follow_up.py         ← manages follow-up sequence scheduling
│   │   └── demo_prep.py         ← Claude API → generates pre-meeting brief
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── gmail.py             ← Gmail SMTP send + Gmail API read
│   │   ├── airtable.py          ← all CRM read/write operations
│   │   ├── apollo.py            ← Apollo.io people/company search
│   │   ├── cal_com.py           ← Cal.com webhook handler
│   │   └── web_search.py        ← DuckDuckGo search (free, no API key)
│   ├── approval/
│   │   ├── __init__.py
│   │   ├── server.py            ← FastAPI webhook server (runs on Railway)
│   │   ├── email_digest.py      ← builds + sends morning approval email
│   │   └── tokens.py            ← generates + validates approval tokens (HMAC)
│   ├── prompts/
│   │   ├── research.txt         ← prompt for researcher agent
│   │   ├── qualify.txt          ← prompt for qualifier agent
│   │   ├── email_cold.txt       ← cold outreach email template
│   │   ├── email_follow1.txt    ← follow-up #1 template (day 3)
│   │   ├── email_follow2.txt    ← follow-up #2 template (day 10)
│   │   ├── email_breakup.txt    ← breakup email template (day 17)
│   │   ├── reply_classify.txt   ← prompt for classifying prospect replies
│   │   ├── reply_draft.txt      ← prompt for drafting responses to replies
│   │   └── demo_prep.txt        ← prompt for pre-meeting brief
│   └── utils/
│       ├── __init__.py
│       ├── logger.py            ← structured logging
│       └── rate_limiter.py      ← respects API rate limits
├── tests/
│   ├── test_prospector.py
│   ├── test_researcher.py
│   ├── test_qualifier.py
│   ├── test_outreach_writer.py
│   ├── test_approval.py
│   └── fixtures/
│       └── mock_prospect.json   ← sample prospect for testing without API calls
└── scripts/
    ├── setup.sh                 ← one-time setup script
    ├── test_run.py              ← dry run: full pipeline, no emails sent
    └── seed_airtable.py         ← creates Airtable base with correct schema
```

---

## Full Pipeline Architecture

Aria is a LangGraph stateful graph. The graph pauses at two interrupt points
and waits for human approval via webhook before proceeding.

### Graph Flow

```
[START]
    ↓
[prospector_node]          # Apollo.io → finds 10 new prospects nightly
    ↓
[researcher_node]          # Claude → enriches each prospect (parallel)
    ↓
[qualifier_node]           # Claude → scores 1-100, filters to Hot only
    ↓
[build_digest_node]        # Builds approval email with all Hot prospects
    ↓
⛔ [INTERRUPT #1]          # Graph pauses. Sends morning digest email.
    ↓                      # Waits for human to tap Approve/Reject links.
[process_approvals_node]   # Applies human decisions to state
    ↓
[outreach_writer_node]     # Claude → writes email + LinkedIn content
    ↓
[send_outreach_node]       # Gmail SMTP → sends approved emails
    ↓
[log_to_crm_node]          # Airtable → logs all activity
    ↓
[linkedin_digest_node]     # Emails human copy-paste LinkedIn content
    ↓
[END — nightly run complete]


SEPARATE GRAPH: reply_monitor (runs every 2 hours)
    ↓
[check_inbox_node]         # Gmail API → fetches new replies
    ↓
[classify_replies_node]    # Claude → classifies each reply type
    ↓
[route_replies_node]       # branches based on classification:
    ├── POSITIVE → [draft_response_node]
    │       ↓
    │   ⛔ [INTERRUPT #2]  # Immediate alert email to human
    │       ↓              # Human taps: SEND THIS / EDIT FIRST / IGNORE
    │   [send_response_node]
    │       ↓
    │   [include_cal_link_node]  # Appends Cal.com booking link
    │
    ├── QUESTION → [draft_answer_node] → INTERRUPT #2 → [send_response_node]
    ├── NOT_NOW  → [schedule_reengage_node]  # Sets future follow-up date
    ├── WRONG_PERSON → [find_contact_node]   # Adds correct person to queue
    ├── OUT_OF_OFFICE → [reschedule_node]    # Uses OOO return date
    └── NO_REPLY → [check_followup_schedule_node]
            ↓
        day 3  → [send_followup_1_node]
        day 10 → [send_followup_2_node]
        day 17 → [send_breakup_node] → [mark_cold_node]


SEPARATE GRAPH: demo_prep (triggers from Cal.com webhook, 1hr before meeting)
    ↓
[fetch_prospect_data_node]  # Airtable → full history of this prospect
    ↓
[generate_brief_node]       # Claude → generates demo prep document
    ↓
[email_brief_node]          # Sends prep email to human


SEPARATE GRAPH: weekly_summary (runs every Monday 7am CT)
    ↓
[fetch_weekly_stats_node]   # Airtable → contacts, replies, demos, pipeline
    ↓
[generate_summary_node]     # Claude → writes weekly summary narrative
    ↓
[email_summary_node]        # Sends Monday morning email to human
```

---

## State Schema

Define in `aria/state.py` using TypedDict:

```python
from typing import TypedDict, List, Optional, Literal
from datetime import datetime

class Prospect(TypedDict):
    id: str                          # UUID, generated on creation
    first_name: str
    last_name: str
    title: str
    company: str
    company_domain: str
    company_revenue_estimate: str    # e.g. "$50M-$100M"
    company_headcount: str
    retailers: List[str]             # ["Walmart", "Target"]
    email: str
    linkedin_url: str
    score: int                       # 0-100
    tier: Literal["hot", "warm", "cold"]
    research_summary: str            # 2-3 sentence enrichment from researcher
    pain_angle: str                  # strongest pain hook for this prospect
    approved: Optional[bool]         # None = pending, True = approved, False = rejected
    outreach_sent: bool
    outreach_sent_at: Optional[str]
    follow_up_1_sent: bool
    follow_up_2_sent: bool
    breakup_sent: bool
    reply_received: bool
    reply_classification: Optional[str]
    meeting_booked: bool
    meeting_datetime: Optional[str]
    deal_stage: Literal["new", "contacted", "replied", "demo_booked",
                         "demo_done", "proposal", "closed_won", "closed_lost",
                         "not_now", "cold"]
    notes: str                       # running notes, appended over time
    airtable_id: Optional[str]       # Airtable record ID for updates

class AriaState(TypedDict):
    run_id: str                      # UUID for this pipeline run
    run_date: str                    # ISO date string
    prospects: List[Prospect]
    digest_sent: bool
    digest_token: str                # HMAC token for approval validation
    approvals_received: List[str]    # list of approved prospect IDs
    rejections_received: List[str]   # list of rejected prospect IDs
    outreach_sent_count: int
    errors: List[str]                # non-fatal errors to log
```

---

## Approval System (Critical — Read Carefully)

The approval mechanism is the heart of Aria. It must be simple, secure,
and work from a phone with one tap.

### How It Works

1. Nightly pipeline builds a morning digest email
2. Each prospect in the email has two links:
   - `https://aria-webhook.railway.app/approve?token=<HMAC_TOKEN>&prospect=<ID>`
   - `https://aria-webhook.railway.app/reject?token=<HMAC_TOKEN>&prospect=<ID>`
3. Human taps links from phone (no login, no password)
4. FastAPI server on Railway receives the tap, validates HMAC token,
   records decision in Airtable, resumes the LangGraph checkpoint
5. After all decisions received (or 4hr timeout), graph resumes and sends
   approved outreach

### Security
- HMAC tokens are signed with `APPROVAL_SECRET` env var
- Tokens expire after 8 hours
- Each token is single-use (marked used in Airtable after first tap)
- If token invalid or expired: returns friendly error page

### Morning Digest Email Format

```
Subject: Aria — 4 prospects ready for review (Apr 4)

Good morning. Here are today's prospects for Auralix outreach.
Tap Approve or Reject for each. Approvals go out automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 #1 — Sarah Chen, Director of Deductions @ Acme Foods
Score: 87/100
Why: Sells to Walmart + Target. $120M revenue. Posted "Deductions Manager"
job last week (signal: backlog pain). No TPM software on website.
Email preview: "Hi Sarah — most deduction teams I talk to at mid-size
CPG companies are sitting on 500–2,000 open claims..."

[✅ APPROVE]    [❌ REJECT]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 #2 — Mike Torres, VP Finance @ Green Valley Brands
Score: 81/100
...

[✅ APPROVE ALL 4]    [❌ REJECT ALL]

Reply to this email with any notes or edits before approving.
```

### Hot Reply Alert Email Format

```
Subject: 🔥 Reply from Sarah Chen @ Acme Foods — action needed

Sarah replied 12 minutes ago:

"This is actually really timely — we've been struggling with our
Walmart deduction backlog. Can you tell me more about how the
evidence pack generation works?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
My suggested response:

"Hi Sarah — great timing. The evidence pack builder automatically
pulls your PO, invoice, and delivery confirmation, then assembles
them into the exact format each retailer requires for dispute...
[SEND THIS RESPONSE]    [I'LL REPLY MYSELF]
```

---

## Agent Specifications

### 1. Prospector (`aria/agents/prospector.py`)

**Purpose**: Find new CPG prospects daily using Apollo.io free tier.

**Apollo.io free tier limits**: 50 credits/month. Use carefully.
Each people search = 1 credit. Budget: 10 new prospects/day, 5 days/week.

**Search parameters to use**:
```python
apollo_params = {
    "person_titles": [
        "Deductions Manager",
        "Director of Deductions",
        "VP Finance",
        "Director of Trade Finance",
        "Controller",
        "Trade Finance Manager",
        "VP Trade Marketing"
    ],
    "organization_industry_tag_ids": [
        "5567cd4773696439b10b0000",  # Food & Beverages
        "5567cd4773696439b10b0001",  # Consumer Goods
        "5567cd4773696439b10b0002",  # Health & Beauty
    ],
    "organization_num_employees_ranges": ["100,2000"],
    "per_page": 10,
    "page": 1
}
```

**Deduplication**: Before returning prospects, check Airtable for existing
records with same email or same (first_name + company_domain) combination.
Skip duplicates silently.

**Output**: List of raw Prospect objects (score=0, tier=None, not yet enriched)

**Error handling**: If Apollo API fails, log error and return empty list.
Do not crash the pipeline. Send error notification email to human.

---

### 2. Researcher (`aria/agents/researcher.py`)

**Purpose**: Enrich each prospect with company intelligence before scoring.

**For each prospect, Claude must find**:
1. Which major retailers does this company sell to? (Walmart, Target, Kroger,
   Costco, Whole Foods, CVS, Walgreens, etc.)
2. Approximate annual revenue (confirm or refine Apollo estimate)
3. Any recent news about trade spend, deductions, or financial pressure
4. Does the company website mention TPM software? (disqualifier)
5. Is there a job posting for Deductions Manager? (strong buying signal)
6. What product categories do they sell? (context for personalization)
7. One specific, recent fact to use in personalized outreach
   (e.g., "saw you just launched your oat milk line at Target")

**Tools to use** (in this order):
1. `web_search(f"{company} CPG retailers sells to")` → DuckDuckGo
2. `web_search(f"{company} annual revenue trade spend")` → DuckDuckGo
3. `web_fetch(company_domain)` → scrape homepage + about page
4. `web_search(f"site:linkedin.com/jobs {company} deductions manager")` → job signals
5. `web_search(f"{company} {current_year} news")` → recent signals

**Claude prompt** (load from `aria/prompts/research.txt`):
Research this CPG company and return a JSON object with these exact fields:
- retailers: list of retailers they sell to (only confirmed, not assumed)
- revenue_confirmed: string like "$50M-$100M" or "unknown"
- tpm_software_detected: boolean (true if SAP TPM, Salesforce TPM, UpClear mentioned)
- job_signal: boolean (true if deductions/trade finance job posted in last 90 days)
- recent_news: one sentence summary of most relevant recent news, or null
- personalization_hook: one specific recent fact for use in outreach (or null)
- pain_angle: one sentence — the strongest deduction pain angle for this prospect
- disqualify: boolean (true if should be removed from pipeline)
- disqualify_reason: string or null

Return ONLY valid JSON. No preamble, no markdown.

**Output**: Enriched Prospect objects. Remove disqualified prospects from list.

---

### 3. Qualifier (`aria/agents/qualifier.py`)

**Purpose**: Score each prospect 0-100 and segment into hot/warm/cold.

**Scoring rules** (implement as deterministic code, not Claude):
```python
def score_prospect(prospect: Prospect) -> int:
    score = 0

    # Retailer signals (max 25)
    high_volume = ["walmart", "target", "costco", "kroger"]
    retailer_matches = sum(1 for r in prospect["retailers"]
                          if any(h in r.lower() for h in high_volume))
    score += min(retailer_matches * 12, 25)

    # Revenue fit (max 20)
    revenue = prospect["company_revenue_estimate"]
    if "$50M" in revenue or "$100M" in revenue or "$200M" in revenue:
        score += 20
    elif "$20M" in revenue or "$500M" in revenue:
        score += 10
    elif "unknown" in revenue:
        score += 5

    # Title match (max 15)
    title = prospect["title"].lower()
    if "deduction" in title:
        score += 15
    elif "trade finance" in title or "vp finance" in title:
        score += 12
    elif "controller" in title or "trade marketing" in title:
        score += 8

    # Buying signals (max 15)
    if prospect.get("job_signal"):       # job posting = active pain
        score += 10
    if prospect.get("recent_news"):      # news = context for outreach
        score += 5

    # Disqualifiers
    if prospect.get("tpm_software_detected"):
        score -= 30

    return max(0, min(100, score))


def tier(score: int) -> str:
    if score >= 70: return "hot"
    if score >= 40: return "warm"
    return "cold"
```

**Output**: Scored and tiered prospects. Only Hot prospects go to the digest.
Warm prospects are stored in Airtable for future outreach batches.
Cold prospects are stored but not actioned.

---

### 4. Outreach Writer (`aria/agents/outreach_writer.py`)

**Purpose**: Write personalized cold email + LinkedIn content for each
approved prospect.

**Email rules** (enforce strictly):
- Under 120 words total
- Lead with their specific pain, not our product
- One question only, at the end
- No bullet points
- No "I hope this email finds you well"
- No "synergy", "leverage", "game-changing"
- Sign as: Abhisek | Auralix | auralix.ai

**Email template** (load from `aria/prompts/email_cold.txt`):
```
Subject: Retailer deductions — {company}

Hi {first_name} —

Most {title}s I talk to at {revenue} CPG companies are sitting on
500–2,000 unresolved retailer deductions, with 30–60 day dispute
windows closing fast.

{personalization_hook if available, else pain_angle}

We built Auralix specifically for this — auto risk scoring, evidence
pack generation, and deadline tracking in one place.

Worth a 20-minute call to see if it's relevant?

Abhisek | Auralix | auralix.ai
```

**Claude's job**: Fill the template with prospect-specific details.
Make it sound human, not AI-generated. Vary sentence structure per prospect.
If personalization_hook exists, use it in sentence 2. If not, use pain_angle.

**LinkedIn connection request** (under 300 chars):
```
Hi {first_name} — I work with CPG finance teams dealing with retailer
deduction backlogs. Think it could be relevant. Happy to connect.
```

**LinkedIn first DM** (after they accept — provide as copy-paste):
```
Thanks for connecting {first_name}.

Quick question — how many unresolved retailer deductions is your team
sitting on right now? Most teams I talk to are managing 500–2,000 open
claims with dispute windows closing fast.

We built something that auto-generates evidence packs and flags which
ones are about to expire. Significantly cut resolution time for a few
CPG teams.

Worth a 20-min call?
```

**Output**: Updated Prospect with email_body, subject, linkedin_connection,
linkedin_dm fields populated.

---

### 5. Reply Handler (`aria/agents/reply_handler.py`)

**Purpose**: Monitor Gmail for prospect replies and classify them.

**Gmail polling**: Use Gmail API (not IMAP). Search for:
```python
query = "in:inbox is:unread -from:me"
# Then filter: is sender email in our Airtable prospect list?
```

**Classification prompt** (load from `aria/prompts/reply_classify.txt`):
Classify this email reply into exactly one category:
- POSITIVE: prospect is interested, wants to learn more, asks questions
- QUESTION: prospect asks a specific question but hasn't committed
- NOT_NOW: prospect says reach out later (extract the timeframe if given)
- WRONG_PERSON: prospect redirects to someone else (extract name/email if given)
- OUT_OF_OFFICE: auto-reply (extract return date if given)
- UNSUBSCRIBE: prospect asks to be removed
- NEGATIVE: prospect clearly not interested
- OTHER: anything else

Return JSON: {"classification": "...", "notes": "...", "extracted_info": "..."}

**Actions per classification**:
```
POSITIVE    → draft_response + INTERRUPT → human decides → include Cal.com link
QUESTION    → draft_response + INTERRUPT → human decides → include Cal.com link
NOT_NOW     → update Airtable re-engage date, log note, no email sent
WRONG_PERSON → find new contact in Airtable or Apollo, add to queue
OUT_OF_OFFICE → reschedule follow-up to after return date
UNSUBSCRIBE → mark do_not_contact=True in Airtable, never contact again
NEGATIVE    → mark closed_lost in Airtable, log note
OTHER       → flag for human review, send alert email
```

---

### 6. Demo Prep (`aria/agents/demo_prep.py`)

**Purpose**: Generate a pre-meeting brief 60 minutes before each booked demo.

**Triggered by**: Cal.com webhook → `POST /cal-webhook` on Railway server
Cal.com sends booking details. Schedule a delayed task for (meeting_time - 60min).

**Claude prompt** (load from `aria/prompts/demo_prep.txt`):
Generate a demo prep brief for a sales call with this prospect.
Use everything we know about them from our CRM data.
Format as a clean email with these sections:

1. WHO YOU'RE MEETING (name, title, company, background)
2. WHAT THEY CARE ABOUT (their top 3 likely pain points based on research)
3. DEMO FLOW (which Auralix screens to show, in what order, ~15 min)
   - Always start with Claims Workbench (their immediate pain)
   - Show risk scoring + expiring claims
   - Show evidence pack generator
   - Do NOT show Scenario Lab, ICC, or Outreach on first call
4. DISCOVERY QUESTIONS (3 specific questions to open the call)
5. LIKELY OBJECTIONS + HOW TO HANDLE (2 most common)
6. GOAL FOR THIS CALL (book a second call with finance decision maker)

---

## Tools Specifications

### Gmail Tool (`aria/tools/gmail.py`)

**Send email**:
```python
def send_email(to: str, subject: str, body: str,
               reply_to: str = None) -> bool:
    # Use Gmail SMTP with app password (not OAuth for sending)
    # SMTP server: smtp.gmail.com, port: 587, TLS
    # Credentials: GMAIL_ADDRESS, GMAIL_APP_PASSWORD env vars
    # Returns True on success, False on failure (never raises)
```

**Read inbox**:
```python
def get_new_replies(since_hours: int = 2) -> List[dict]:
    # Use Gmail API (OAuth 2.0)
    # Returns list of {sender, subject, body, message_id, thread_id}
    # Only returns emails from known prospects (check Airtable)
    # Marks messages as read after fetching
```

**Required env vars**: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`,
`GMAIL_OAUTH_CREDENTIALS` (JSON string for Gmail API)

---

### Airtable Tool (`aria/tools/airtable.py`)

**Base structure** — create these tables in Airtable:

**Table: Prospects**
| Field | Type | Notes |
|-------|------|-------|
| Name | Text | "{first} {last}" |
| Email | Email | Primary identifier |
| Title | Text | |
| Company | Text | |
| Domain | URL | |
| Score | Number | 0-100 |
| Tier | Single Select | hot/warm/cold |
| Deal Stage | Single Select | new/contacted/replied/demo_booked/demo_done/proposal/closed_won/closed_lost/not_now/cold |
| Research Summary | Long Text | |
| Pain Angle | Text | |
| Email Body | Long Text | Outreach email used |
| Outreach Sent | Checkbox | |
| Outreach Sent At | Date | |
| Follow Up 1 Sent | Checkbox | |
| Follow Up 2 Sent | Checkbox | |
| Breakup Sent | Checkbox | |
| Reply Received | Checkbox | |
| Reply Classification | Single Select | |
| Meeting Booked | Checkbox | |
| Meeting Date | Date | |
| Re-engage Date | Date | When to follow up again |
| Do Not Contact | Checkbox | NEVER contact if true |
| LinkedIn URL | URL | |
| Notes | Long Text | Append-only running log |
| Created At | Date | |
| Last Updated | Date | Auto |

**Table: Activity Log**
| Field | Type | Notes |
|-------|------|-------|
| Prospect | Link to Prospects | |
| Action | Single Select | email_sent/reply_received/meeting_booked/note_added/stage_changed |
| Details | Long Text | |
| Timestamp | Date+Time | |

**Required env vars**: `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`

---

### Apollo Tool (`aria/tools/apollo.py`)

```python
def search_prospects(titles: List[str], industries: List[str],
                     headcount_range: str, page: int = 1) -> List[dict]:
    # POST https://api.apollo.io/v1/mixed_people/search
    # Headers: {"X-Api-Key": APOLLO_API_KEY}
    # Returns raw Apollo person objects
    # Maps to Prospect TypedDict format before returning

def get_email(person_id: str) -> Optional[str]:
    # POST https://api.apollo.io/v1/people/match
    # Reveals email address (costs 1 credit)
    # Only call if email not already in search results
```

**Required env vars**: `APOLLO_API_KEY`
**Rate limiting**: Max 10 requests/minute. Use `aria/utils/rate_limiter.py`.

---

### Web Search Tool (`aria/tools/web_search.py`)

Use DuckDuckGo Instant Answer API (free, no API key):
```python
import httpx

def web_search(query: str, max_results: int = 5) -> List[dict]:
    # GET https://api.duckduckgo.com/?q={query}&format=json&no_html=1
    # Returns list of {title, url, snippet}
    # Also try: https://html.duckduckgo.com/html/?q={query}
    # Parse results with BeautifulSoup if needed

def web_fetch(url: str, max_chars: int = 3000) -> str:
    # GET the URL, extract main text content
    # Use readability-lxml or trafilatura for clean extraction
    # Truncate to max_chars to control Claude API costs
    # Return empty string on error (never raise)
```

---

### Cal.com Tool (`aria/tools/cal_com.py`)

```python
def handle_booking_webhook(payload: dict) -> dict:
    # Receives Cal.com BOOKING_CREATED webhook
    # Extracts: attendee name, email, company, meeting datetime
    # Finds prospect in Airtable by email
    # Updates: meeting_booked=True, meeting_date, deal_stage=demo_booked
    # Schedules demo prep email for (meeting_datetime - 60min)
    # Returns prospect data for demo prep agent

def handle_cancellation_webhook(payload: dict):
    # Receives Cal.com BOOKING_CANCELLED
    # Updates Airtable: meeting_booked=False
    # Sends human a heads-up email

def handle_noshow_webhook(payload: dict):
    # Receives Cal.com NO_SHOW event
    # Queues follow-up email for next day
    # Updates Airtable: notes += "No-show on {date}"
```

**Required env vars**: `CAL_COM_WEBHOOK_SECRET` (for signature verification)

---

## Approval Server (`aria/approval/server.py`)

This is a tiny FastAPI server that runs 24/7 on Railway (free tier).
It receives webhook taps from the human's phone and resumes LangGraph.

```python
from fastapi import FastAPI, HTTPException
from aria.approval.tokens import validate_token
from aria.tools.airtable import update_prospect
import httpx

app = FastAPI()

@app.get("/approve")
async def approve(token: str, prospect: str):
    if not validate_token(token, prospect):
        raise HTTPException(400, "Invalid or expired token")
    update_prospect(prospect, {"approved": True})
    # Resume LangGraph checkpoint for this run
    # (store thread_id in Airtable when digest is sent)
    return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:50px">
        <h2>✅ Approved</h2>
        <p>Outreach will go out shortly.</p>
        </body></html>
    """)

@app.get("/reject")
async def reject(token: str, prospect: str):
    if not validate_token(token, prospect):
        raise HTTPException(400, "Invalid or expired token")
    update_prospect(prospect, {"approved": False})
    return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding:50px">
        <h2>❌ Rejected</h2>
        <p>This prospect has been skipped.</p>
        </body></html>
    """)

@app.post("/cal-webhook")
async def cal_webhook(request: Request):
    # Verify Cal.com signature
    # Route to cal_com.py handler
    ...

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Required env vars**: `APPROVAL_SECRET`, `AIRTABLE_API_KEY`,
`AIRTABLE_BASE_ID`, `RAILWAY_PORT` (set by Railway automatically)

---

## GitHub Actions Workflows

### Nightly Pipeline (`.github/workflows/nightly.yml`)
```yaml
name: Aria Nightly
on:
  schedule:
    - cron: '0 7 * * 1-5'  # 2am CT = 7am UTC, weekdays only
  workflow_dispatch:         # allow manual trigger for testing

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python -m aria.graph
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          APOLLO_API_KEY: ${{ secrets.APOLLO_API_KEY }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GMAIL_OAUTH_CREDENTIALS: ${{ secrets.GMAIL_OAUTH_CREDENTIALS }}
          AIRTABLE_API_KEY: ${{ secrets.AIRTABLE_API_KEY }}
          AIRTABLE_BASE_ID: ${{ secrets.AIRTABLE_BASE_ID }}
          APPROVAL_SECRET: ${{ secrets.APPROVAL_SECRET }}
          RAILWAY_WEBHOOK_URL: ${{ secrets.RAILWAY_WEBHOOK_URL }}
          HUMAN_EMAIL: ${{ secrets.HUMAN_EMAIL }}
          CAL_COM_LINK: ${{ secrets.CAL_COM_LINK }}
```

### Reply Monitor (`.github/workflows/reply_monitor.yml`)
```yaml
name: Aria Reply Monitor
on:
  schedule:
    - cron: '0 */2 * * *'   # every 2 hours
  workflow_dispatch:

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python -m aria.agents.reply_handler
        env: [same secrets as above]
```

### Weekly Summary (`.github/workflows/weekly_summary.yml`)
```yaml
name: Aria Weekly Summary
on:
  schedule:
    - cron: '0 13 * * 1'    # Monday 7am CT = 1pm UTC
  workflow_dispatch:
```

---

## Environment Variables

Create `.env.example` with ALL of these (no values, just keys):

```bash
# Claude API
ANTHROPIC_API_KEY=

# Apollo.io (prospecting)
APOLLO_API_KEY=

# Gmail (sending + reading)
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=          # 16-char app password from Google account
GMAIL_OAUTH_CREDENTIALS=     # JSON string for Gmail API read access

# Airtable (CRM)
AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=

# Approval system
APPROVAL_SECRET=             # random 32-char string for HMAC signing
RAILWAY_WEBHOOK_URL=         # e.g. https://aria-webhook.railway.app

# Scheduling
HUMAN_EMAIL=                 # where to send digest + alerts
CAL_COM_LINK=                # your Cal.com booking page URL

# Cal.com
CAL_COM_WEBHOOK_SECRET=      # from Cal.com webhook settings

# Optional: controls
DRY_RUN=false                # set true to run pipeline without sending emails
MAX_PROSPECTS_PER_DAY=10     # safety limit
```

---

## Cost Budget

| Item | Monthly Cost |
|------|-------------|
| Claude API (research + writing ~200 prospects/month) | ~$3 |
| Apollo.io free tier | $0 |
| Gmail | $0 |
| Airtable free tier | $0 |
| Cal.com free tier | $0 |
| GitHub Actions free tier | $0 |
| Railway free tier (webhook server) | $0 |
| **Total** | **~$3/month** |

**Claude API cost control**:
- Researcher: use claude-haiku-4-5 (cheapest, good enough for research)
- Qualifier: deterministic code, no Claude needed
- Outreach writer: use claude-sonnet-4-6 (quality matters here)
- Reply classifier: use claude-haiku-4-5
- Reply drafter: use claude-sonnet-4-6
- Demo prep: use claude-sonnet-4-6
- Weekly summary: use claude-haiku-4-5

---

## Build Order (2-Week Sprint)

### Week 1 — Core Pipeline

**Day 1-2: Foundation**
- [ ] Set up repo structure exactly as specified above
- [ ] `aria/state.py` — full TypedDict schema
- [ ] `aria/config.py` — loads + validates all env vars on startup
- [ ] `aria/utils/logger.py` — structured logging to stdout
- [ ] `aria/utils/rate_limiter.py` — token bucket, configurable per API
- [ ] `tests/fixtures/mock_prospect.json` — sample data for testing
- [ ] `requirements.txt` — all dependencies pinned

**Day 3: Prospector + Airtable**
- [ ] `aria/tools/airtable.py` — full CRUD for Prospects + Activity Log
- [ ] `scripts/seed_airtable.py` — creates tables with correct schema
- [ ] `aria/agents/prospector.py` — Apollo.io search + deduplication
- [ ] `tests/test_prospector.py` — test with mock Apollo response

**Day 4: Researcher**
- [ ] `aria/tools/web_search.py` — DuckDuckGo + web_fetch
- [ ] `aria/prompts/research.txt` — research prompt
- [ ] `aria/agents/researcher.py` — full enrichment pipeline
- [ ] `tests/test_researcher.py` — test with mock_prospect.json

**Day 5: Qualifier + Morning Digest**
- [ ] `aria/agents/qualifier.py` — deterministic scoring
- [ ] `aria/approval/tokens.py` — HMAC generation + validation
- [ ] `aria/approval/email_digest.py` — builds HTML digest email
- [ ] Wire together in `aria/graph.py` — nodes 1-4
- [ ] `tests/test_qualifier.py`

### Week 2 — Full Loop

**Day 6-7: Approval Server + Outreach**
- [ ] `aria/approval/server.py` — FastAPI with /approve /reject /cal-webhook
- [ ] Deploy to Railway (free tier), get RAILWAY_WEBHOOK_URL
- [ ] `aria/prompts/email_cold.txt` + all follow-up templates
- [ ] `aria/agents/outreach_writer.py` — email + LinkedIn content
- [ ] `aria/tools/gmail.py` — SMTP send + API read
- [ ] Wire INTERRUPT #1 into LangGraph graph
- [ ] `tests/test_approval.py`

**Day 8-9: Reply Handler**
- [ ] `aria/prompts/reply_classify.txt` + `reply_draft.txt`
- [ ] `aria/agents/reply_handler.py` — full classification + routing
- [ ] `aria/agents/follow_up.py` — sequence scheduling
- [ ] Wire INTERRUPT #2 into reply graph
- [ ] `tests/test_reply_handler.py` (if time permits)

**Day 10: Demo Prep + Weekly Summary**
- [ ] `aria/prompts/demo_prep.txt`
- [ ] `aria/agents/demo_prep.py`
- [ ] Weekly summary graph
- [ ] All GitHub Actions workflows

**Day 11-12: Integration Testing**
- [ ] `scripts/test_run.py` — full pipeline dry run (DRY_RUN=true)
- [ ] Test approval email on real phone
- [ ] Test approval tap → webhook → Airtable update
- [ ] Test reply monitor with a real reply to yourself
- [ ] Fix any issues

**Day 13-14: First Real Run**
- [ ] Set DRY_RUN=false
- [ ] Run nightly pipeline with 5 real prospects
- [ ] Review morning digest, approve 2-3
- [ ] Confirm emails sent, logged in Airtable
- [ ] Aria is live

---

## Coding Standards

**Language**: Python 3.11+

**Dependencies to use**:
```
langgraph>=0.2.0
langchain-anthropic>=0.3.0
anthropic>=0.40.0
fastapi>=0.115.0
uvicorn>=0.32.0
httpx>=0.27.0
pyairtable>=2.3.0
google-auth>=2.35.0
google-api-python-client>=2.150.0
trafilatura>=1.12.0   # web content extraction
pydantic>=2.9.0
python-dotenv>=1.0.0
pytest>=8.3.0
pytest-asyncio>=0.24.0
```

**Error handling rules**:
- NEVER let an agent crash the entire pipeline
- Every external API call wrapped in try/except
- On failure: log error, append to state["errors"], continue
- If 3+ errors in one run: send alert email to human
- Always return something (empty list, None) rather than raising

**Logging rules**:
- Log every agent start/end with prospect count
- Log every email sent (to, subject, timestamp)
- Log every Airtable write
- Log every approval received
- NEVER log email body content or personal data to stdout
  (GitHub Actions logs are visible)

**Testing rules**:
- All tests use mock_prospect.json fixture, never real APIs
- Use pytest with fixtures
- Each agent has its own test file
- `DRY_RUN=true` must prevent ALL external calls (emails, Airtable writes)

---

## What Claude Code Should Do On First Session

1. Read this entire CLAUDE.md
2. Create the full directory structure
3. Start with Day 1-2 tasks: state.py, config.py, logger.py, rate_limiter.py
4. Ask before making any design decisions not covered in this doc
5. Never skip the build order — foundation before features

---

## What Success Looks Like

**Week 2**: First real outreach emails sent to CPG prospects.
**Month 1**: 50 prospects contacted, 5-10 replies, 2-3 demos booked.
**Month 2**: First Auralix design partner signed.
**Month 3**: Case study in hand. Expand outreach volume.
