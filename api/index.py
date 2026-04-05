"""
Vercel serverless entry point.
"""
import sys
import os

# Ensure the repo root is on the path so `aria.*` imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aria.approval.server import app  # noqa: F401
