import logging
import sys
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """
    Returns a structured logger for the given module name.
    Logs to stdout only — GitHub Actions captures this.
    NEVER logs email body content or personal data.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def log_agent_start(logger: logging.Logger, agent_name: str, prospect_count: int = 0) -> None:
    logger.info(f"[{agent_name}] START — {prospect_count} prospects")


def log_agent_end(logger: logging.Logger, agent_name: str, prospect_count: int = 0) -> None:
    logger.info(f"[{agent_name}] END — {prospect_count} prospects processed")


def log_email_sent(logger: logging.Logger, to_email: str, subject: str) -> None:
    """Log email sent. Never log the body."""
    logger.info(f"[EMAIL] Sent to={to_email} subject='{subject}'")


def log_airtable_write(logger: logging.Logger, table: str, record_id: str, action: str) -> None:
    logger.info(f"[AIRTABLE] {action} table={table} record={record_id}")


def log_approval(logger: logging.Logger, prospect_id: str, decision: str) -> None:
    logger.info(f"[APPROVAL] prospect={prospect_id} decision={decision}")


def log_error(logger: logging.Logger, agent: str, error: str) -> None:
    logger.error(f"[ERROR] agent={agent} error={error}")
