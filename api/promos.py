"""Vercel Python function: /api/promos (logic lives in promo/web.py)."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from promo.web import make_handler  # noqa: E402


class handler(make_handler("promos"), BaseHTTPRequestHandler):
    pass
