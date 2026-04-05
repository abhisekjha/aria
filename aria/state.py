from typing import TypedDict, List, Optional, Literal
from datetime import datetime


class Prospect(TypedDict):
    id: str                           # UUID generated on creation
    first_name: str
    last_name: str
    title: str
    company: str
    company_domain: str
    company_revenue_estimate: str     # e.g. "$50M-$100M" or "unknown"
    company_headcount: str            # e.g. "100-500"
    retailers: List[str]              # ["Walmart", "Target"]
    email: str
    linkedin_url: str
    score: int                        # 0-100
    tier: Optional[Literal["hot", "warm", "cold"]]
    research_summary: str             # 2-3 sentence enrichment
    pain_angle: str                   # strongest deduction pain hook
    personalization_hook: Optional[str]  # specific recent fact for outreach
    tpm_software_detected: bool       # disqualifier if True
    job_signal: bool                  # deductions job posting = buying signal
    recent_news: Optional[str]        # one-line recent news or None
    disqualified: bool
    disqualify_reason: Optional[str]
    approved: Optional[bool]          # None=pending, True=approved, False=rejected
    email_subject: Optional[str]
    email_body: Optional[str]
    linkedin_connection_msg: Optional[str]
    linkedin_dm: Optional[str]
    outreach_sent: bool
    outreach_sent_at: Optional[str]   # ISO datetime string
    follow_up_1_sent: bool
    follow_up_2_sent: bool
    breakup_sent: bool
    reply_received: bool
    reply_classification: Optional[str]
    meeting_booked: bool
    meeting_datetime: Optional[str]   # ISO datetime string
    re_engage_date: Optional[str]     # ISO date string
    do_not_contact: bool
    deal_stage: Literal[
        "new", "contacted", "replied", "demo_booked",
        "demo_done", "proposal", "closed_won", "closed_lost",
        "not_now", "cold"
    ]
    notes: str                        # append-only running log
    airtable_id: Optional[str]        # Airtable record ID for updates


class AriaState(TypedDict):
    run_id: str                       # UUID for this pipeline run
    run_date: str                     # ISO date string
    prospects: List[Prospect]
    digest_sent: bool
    digest_token: str                 # HMAC token for approval validation
    approvals_received: List[str]     # prospect IDs approved by human
    rejections_received: List[str]    # prospect IDs rejected by human
    outreach_sent_count: int
    errors: List[str]                 # non-fatal errors — never crash pipeline


def make_empty_prospect() -> Prospect:
    """Returns a Prospect with all required fields set to safe defaults."""
    return Prospect(
        id="",
        first_name="",
        last_name="",
        title="",
        company="",
        company_domain="",
        company_revenue_estimate="unknown",
        company_headcount="unknown",
        retailers=[],
        email="",
        linkedin_url="",
        score=0,
        tier=None,
        research_summary="",
        pain_angle="",
        personalization_hook=None,
        tpm_software_detected=False,
        job_signal=False,
        recent_news=None,
        disqualified=False,
        disqualify_reason=None,
        approved=None,
        email_subject=None,
        email_body=None,
        linkedin_connection_msg=None,
        linkedin_dm=None,
        outreach_sent=False,
        outreach_sent_at=None,
        follow_up_1_sent=False,
        follow_up_2_sent=False,
        breakup_sent=False,
        reply_received=False,
        reply_classification=None,
        meeting_booked=False,
        meeting_datetime=None,
        re_engage_date=None,
        do_not_contact=False,
        deal_stage="new",
        notes="",
        airtable_id=None,
    )
