"""
VoteSecure Configuration
========================
To enable Google Sign-In:
1. Go to https://console.cloud.google.com
2. Create a project → APIs & Services → OAuth 2.0 Client IDs
3. Application type: Web application
4. Authorized redirect URIs: http://localhost:8000/api/auth/google/callback
5. Copy your Client ID and Client Secret below
"""

# ── Google OAuth 2.0 ─────────────────────────────────────────
GOOGLE_CLIENT_ID     = "769161688094-3q37gb7kfit3jfnkq2693oosqk91fl0l.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
GOOGLE_REDIRECT_URI  = "http://localhost:8000/api/auth/google/callback"

# Set to True once you've added real credentials above
GOOGLE_OAUTH_ENABLED = True

import os

# ── Database Config (Cloud / Local) ──────────────────────────
# Prefers Environment Variable 'DATABASE_URL' for Cloud deployment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_yOJxMqV4m1sG@ep-broad-truth-anqla1es.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require") 

# ── Automated Mailer (SMTP Config) ───────────────────────────
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

# ── App Config ───────────────────────────────────────────────
APP_HOST = "localhost"
APP_PORT = 8000
SESSION_TIMEOUT_MINUTES = 60

# ── Default Admin ────────────────────────────────────────────
DEFAULT_ADMIN_EMAIL    = "admin@votesecure.com"
DEFAULT_ADMIN_PASSWORD = "Admin@123"
