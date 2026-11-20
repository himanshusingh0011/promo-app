"""Vercel Python function: /api/score (logic lives in promo/web.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from promo.web import make_handler  # noqa: E402

handler = make_handler("score")
