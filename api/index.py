"""
Vercel serverless entry point.
Imports the FastAPI app so Vercel can serve it.
"""
from aria.approval.server import app  # noqa: F401
