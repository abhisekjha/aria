"""
FastAPI webhook server — runs 24/7 on Railway free tier.
Handles: approval taps, Cal.com webhooks, reply send confirmations.
"""
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from aria.approval.tokens import validate_token
from aria.ui.routes import router as ui_router
from aria.tools.airtable import update_prospect, log_activity, get_prospect_by_email
from aria.tools.gmail import send_email
from aria.tools.cal_com import verify_webhook_signature, handle_booking_created, handle_booking_cancelled
from aria.agents.demo_prep import run as run_demo_prep
from aria.config import Config
from aria.utils.logger import get_logger, log_approval

logger = get_logger(__name__)

app = FastAPI(title="Aria Webhook Server")
app.include_router(ui_router)


@app.get("/")
async def root():
    return RedirectResponse("/ui")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aria-webhook"}


@app.get("/approve", response_class=HTMLResponse)
async def approve(token: str, prospect: str, run: str = ""):
    if not validate_token(token, prospect):
        raise HTTPException(400, "Invalid or expired token")

    update_prospect(prospect, {"approved": True, "Deal Stage": "contacted"})
    log_activity(prospect, "note_added", "Approved by human via email tap")
    log_approval(logger, prospect, "APPROVED")

    return _success_page("✅ Approved", "Outreach will go out shortly.")


@app.get("/reject", response_class=HTMLResponse)
async def reject(token: str, prospect: str, run: str = ""):
    if not validate_token(token, prospect):
        raise HTTPException(400, "Invalid or expired token")

    update_prospect(prospect, {"approved": False})
    log_activity(prospect, "note_added", "Rejected by human via email tap")
    log_approval(logger, prospect, "REJECTED")

    return _success_page("❌ Rejected", "This prospect has been skipped.")


@app.get("/approve-all", response_class=HTMLResponse)
async def approve_all(run: str, ids: str):
    prospect_ids = ids.split(",")
    for pid in prospect_ids:
        update_prospect(pid, {"approved": True, "Deal Stage": "contacted"})
        log_activity(pid, "note_added", "Bulk approved via email tap")
        log_approval(logger, pid, "APPROVED")

    return _success_page(
        f"✅ Approved All ({len(prospect_ids)})",
        "All outreach emails will go out shortly."
    )


@app.post("/send-reply")
async def send_reply(airtable_id: str, approved: bool, request: Request):
    """Human approves AI-drafted reply to a hot prospect."""
    body = await request.json()
    draft = body.get("draft", "")
    prospect_email = body.get("email", "")
    subject = body.get("subject", "Re: Auralix")

    if approved and draft and prospect_email:
        sent = send_email(prospect_email, subject, draft)
        if sent:
            update_prospect(airtable_id, {"Deal Stage": "replied"})
            log_activity(airtable_id, "email_sent", "AI-drafted reply sent (human approved)")

    return {"status": "ok"}


@app.post("/cal-webhook")
async def cal_webhook(request: Request):
    """Handle Cal.com booking webhooks."""
    body_bytes = await request.body()
    signature = request.headers.get("X-Cal-Signature-256", "")

    if Config.CAL_COM_WEBHOOK_SECRET:
        if not verify_webhook_signature(body_bytes, signature):
            raise HTTPException(401, "Invalid webhook signature")

    payload = json.loads(body_bytes)
    trigger = payload.get("triggerEvent", "")

    logger.info(f"[CAL_WEBHOOK] Received: {trigger}")

    if trigger == "BOOKING_CREATED":
        prospect_data = handle_booking_created(payload)
        if prospect_data:
            meeting_dt = prospect_data.get("meeting_datetime", "")
            attendee_email = payload.get("attendees", [{}])[0].get("email", "")
            if attendee_email and meeting_dt:
                # Run demo prep immediately (in production, would schedule for -60min)
                run_demo_prep(attendee_email, meeting_dt)

    elif trigger == "BOOKING_CANCELLED":
        handle_booking_cancelled(payload)

    return {"status": "ok"}


def _success_page(title: str, message: str) -> str:
    return f"""
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; margin: 0; background: #f8fafc;
    }}
    .card {{
      text-align: center; padding: 40px; background: white;
      border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);
      max-width: 320px;
    }}
    h2 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ color: #64748b; margin: 0; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>{title}</h2>
    <p>{message}</p>
  </div>
</body>
</html>
"""
