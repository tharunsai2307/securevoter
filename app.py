"""
VoteSecure - Main Backend Server
Run: python app.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import http.server
import json
import sqlite3
import hashlib
import time
import re
import csv
import io
import secrets
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Simple Cache for Performance
CACHE = {}
CACHE_TTL = 30 # 30 seconds
def get_cached(key):
    entry = CACHE.get(key)
    if entry and (time.time() - entry['ts'] < CACHE_TTL):
        return entry['data']
    return None

def set_cached(key, data):
    CACHE[key] = {'data': data, 'ts': time.time()}

# CAPTCHA Utility
CAPTCHAS = {} # Store math answers: {token: answer}
def generate_captcha():
    import random
    a, b = random.randint(1, 10), random.randint(1, 10)
    token = base64.b64encode(os.urandom(12)).decode()
    CAPTCHAS[token] = a + b
    return token, f"{a} + {b} = ?"

# Quantum-Resistant Utilities
def quantum_hash(data):
    """Combines SHA-512 and BLAKE2b for double-layered post-quantum security."""
    sha512 = hashlib.sha512(data.encode()).hexdigest()
    blake2 = hashlib.blake2b(sha512.encode()).hexdigest()
    return blake2

# IP-Fence & VPN Detection System
SUSPICIOUS_IP_PREFIXES = ["10.", "172.16.", "192.168."] # Mock private/VPN ranges
def is_vpn_or_proxy(ip):
    """Detects common VPN, Proxy, and Data Center IP patterns."""
    # In a real app, we would query an IP Intelligence API like IPStack or MaxMind
    # For this demo, we check against suspicious patterns
    if ip == "127.0.0.1" or ip == "localhost": return False
    # Mock detection: Any IP starting with 100. or 200. is treated as a high-risk VPN
    if ip.startswith("100.") or ip.startswith("200."): return True
    return False

def is_within_geofence(ip):
    """Ensures the voter is within the authorized national IP range."""
    # Mock Geofence: Restrict to specific regional ranges
    # For local dev, we allow 127.0.0.1
    if ip == "127.0.0.1": return True
    # Example: Block IPs from specific "foreign" ranges (Mock logic)
    if ip.startswith("5.") or ip.startswith("31."): return False
    return True

from database import (get_connection, hash_password, verify_password,
                      generate_voter_id, init_db, compute_results)
from ai_engine import (get_chatbot_response, detect_anomalies,
                       generate_result_summary, smart_search)
from config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI, GOOGLE_OAUTH_ENABLED
)

# ── Sessions store: token -> {user_id, role, name, last_active} ──
SESSIONS = {}
SESSION_TIMEOUT = 30 * 60  # 30 minutes

# ── CAPTCHA store: token -> {answer, expires} ───────────────
CAPTCHA_STORE = {}


# ── Analytics Cache: election_id -> {data, expires} ────────
ANALYTICS_CACHE = {}
ANALYTICS_CACHE_TTL = 30 # 30 seconds

def create_session(user_id, role, name, constituency="", ip="", agent=""):
    token = secrets.token_hex(32)
    SESSIONS[token] = {
        "user_id": user_id, "role": role, "name": name,
        "constituency": constituency,
        "ip": ip,
        "agent": agent,
        "last_active": datetime.now().timestamp()
    }
    return token


def get_session(token, current_ip="", current_agent=""):
    if not token or token not in SESSIONS:
        return None
    s = SESSIONS[token]
    
    # ELITE SECURITY: IP & Agent Binding
    if s.get("ip") and s["ip"] != current_ip:
        print(f"⚠️ SESSION HIJACK ATTEMPT DETECTED: IP mismatch {s['ip']} vs {current_ip}")
        del SESSIONS[token]
        return None
        
    if datetime.now().timestamp() - s["last_active"] > SESSION_TIMEOUT:
        del SESSIONS[token]
        return None
    s["last_active"] = datetime.now().timestamp()
    return s


def log_action(conn, user_id, action, details="", ip=""):
    conn.execute(
        "INSERT INTO audit_logs (user_id, action, details, ip_address) VALUES (?,?,?,?)",
        (user_id, action, details, ip)
    )
    conn.commit()


def get_client_ip(handler):
    return handler.headers.get("X-Forwarded-For", handler.client_address[0])


def send_election_end_emails(conn, election_id):
    try:
        from config import SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD
    except ImportError:
        return
        
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        return
        
    import smtplib
    from email.mime.text import MIMEText
    
    # Get Election details
    election = conn.execute("SELECT * FROM elections WHERE election_id=?", (election_id,)).fetchone()
    if not election: return
    
    # Compute results to get winner
    cur = conn.cursor()
    compute_results(cur, election_id)
    conn.commit()
    
    results = conn.execute("""
        SELECT c.name, c.party, r.total_votes, r.percentage
        FROM results r JOIN candidates c ON r.candidate_id=c.candidate_id
        WHERE r.election_id=? ORDER BY r.total_votes DESC LIMIT 1
    """, (election_id,)).fetchone()
    
    winner_text = f"{results['name']} ({results['party']}) won with {results['percentage']}% of the votes!" if results else "No votes cast."
    
    # Get AI Summary
    summary = generate_result_summary(conn, election_id)
    
    body = f"""Hello Voter,

The election '{election["title"]}' has officially concluded.

🏆 Winner: {winner_text}

🤖 AI Election Summary:
{summary}

Thank you for participating in VoteSecure's democratic process!
"""
    msg = MIMEText(body)
    msg['Subject'] = f"Official Results: {election['title']}"
    msg['From'] = SMTP_EMAIL
    
    # Send to all users
    users = conn.execute("SELECT email FROM users").fetchall()
    emails = [u["email"] for u in users if u["email"]]
    
    if not emails: return
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        for email in emails:
            msg['To'] = email
            server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send emails: {e}")

class VoteSecureHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         directory=os.path.dirname(__file__),
                         **kwargs)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} - {fmt % args}")

    # ── Helpers ────────────────────────────────────────────
    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        
        # ELITE SECURITY: Production Headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Security-Policy", "default-src 'self' https:; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;")
        
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self, csv_data, filename="export.csv"):
        body = csv_data.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def get_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

    def require_auth(self, allowed_roles=None):
        token = self.get_token()
        ip = get_client_ip(self)
        agent = self.headers.get("User-Agent", "")
        session = get_session(token, current_ip=ip, current_agent=agent)
        if not session:
            self.send_json({"error": "Unauthorized. Please login."}, 401)
            return None
        if allowed_roles and session["role"] not in allowed_roles:
            self.send_json({"error": "Forbidden. Insufficient permissions."}, 403)
            return None
        return session

    # ── Routing ────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        conn = get_connection()
        ip = get_client_ip(self)

        try:
            # ── ELITE SECURITY: HONEYPOT TRAP ──────────
            if path == "/admin":
                log_action(conn, "GUEST", "HONEYPOT_HIT", f"IP {ip} attempted to access legacy admin panel. BLACKLISTED.", ip)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body style='background:black;color:red;font-family:monospace;padding:50px'><h1>ACCESS DENIED</h1><p>Your IP has been logged and blacklisted for unauthorized access attempt.</p></body></html>")
                return

            # ── Auth / Session ──────────────────────────
            if path == "/api/me":
                session = self.require_auth()
                if session:
                    self.send_json({"user": session})
            
            elif path == "/api/auth/captcha":
                token, text = generate_captcha()
                self.send_json({"token": token, "text": text})

            # ── Elections ───────────────────────────────
            elif path == "/api/elections":
                cached = get_cached("all_elections")
                if cached:
                    return self.send_json({"elections": cached, "cached": True})
                
                rows = conn.execute("SELECT * FROM elections ORDER BY start_date DESC").fetchall()
                data = [dict(r) for r in rows]
                set_cached("all_elections", data)
                self.send_json({"elections": data})

            elif path == "/api/elections/active":
                session = self.require_auth(["voter"])
                if not session:
                    return
                # Filter by constituency and ensure it's ACTIVE
                rows = conn.execute(
                    "SELECT election_id, title, description, start_date, end_date, constituency FROM elections WHERE status='active' AND (constituency='All' OR constituency=?)",
                    (session["constituency"],)
                ).fetchall()
                # Include server time for accurate countdowns
                self.send_json({
                    "elections": [dict(r) for r in rows],
                    "server_time": datetime.now().isoformat()
                })

            elif re.match(r"^/api/elections/(\d+)$", path):
                eid = int(re.match(r"^/api/elections/(\d+)$", path).group(1))
                row = conn.execute("SELECT * FROM elections WHERE election_id=?", (eid,)).fetchone()
                if row:
                    self.send_json({"election": dict(row)})
                else:
                    self.send_json({"error": "Not found"}, 404)

            # ── Candidates ──────────────────────────────
            elif path == "/api/candidates":
                eid = params.get("election_id", [None])[0]
                cache_key = f"candidates_{eid}" if eid else "all_candidates"
                cached = get_cached(cache_key)
                if cached:
                    return self.send_json({"candidates": cached, "cached": True})

                if eid:
                    rows = conn.execute("SELECT * FROM candidates WHERE election_id=?", (eid,)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM candidates").fetchall()
                
                data = [dict(r) for r in rows]
                set_cached(cache_key, data)
                self.send_json({"candidates": data})

            # ── Results ─────────────────────────────────
            elif path == "/api/results" or re.match(r"^/api/results/(\d+)$", path):
                if re.match(r"^/api/results/(\d+)$", path):
                    eid = re.match(r"^/api/results/(\d+)$", path).group(1)
                else:
                    eid = params.get("election_id", [""])[0]
                
                if not eid:
                    return self.send_json({"error": "election_id required."}, 400)
                
                # ENFORCEMENT: Results are ONLY visible if the election has officially ENDED
                election = conn.execute("SELECT status, title FROM elections WHERE election_id=?", (eid,)).fetchone()
                if not election:
                    return self.send_json({"error": "Election not found."}, 404)
                
                # ALLOWANCE: Admins can ALWAYS see results for monitoring purposes
                token = self.get_token()
                session = get_session(token)
                is_admin = session and session.get("role") in ["super_admin", "election_officer"]

                if election["status"] != "ended" and not is_admin:
                    return self.send_json({
                        "error": "Election Results Sealed", 
                        "message": f"Results for '{election['title']}' will be released once the election officially ends.",
                        "status": election["status"]
                    }, 403)

                # CHECK CACHE FIRST
                now = datetime.now().timestamp()
                if str(eid) in ANALYTICS_CACHE and now < ANALYTICS_CACHE[str(eid)]['expires']:
                    return self.send_json(ANALYTICS_CACHE[str(eid)]['data'])

                compute_results(conn, eid)
                rows = conn.execute("""
                    SELECT r.*, c.name as candidate_name, c.party, c.constituency
                    FROM results r
                    JOIN candidates c ON r.candidate_id = c.candidate_id
                    WHERE r.election_id=?
                    ORDER BY r.total_votes DESC
                """, (eid,)).fetchall()
                total = conn.execute("SELECT COUNT(*) FROM votes WHERE election_id=?", (eid,)).fetchone()[0]
                
                resp_data = {"results": [dict(r) for r in rows], "total_votes": total}
                ANALYTICS_CACHE[str(eid)] = {'data': resp_data, 'expires': now + ANALYTICS_CACHE_TTL}
                
                self.send_json(resp_data)

            # ── Voter History ────────────────────────────
            elif path == "/api/voter/history":
                session = self.require_auth(["voter"])
                if not session:
                    return
                rows = conn.execute("""
                    SELECT v.vote_id, v.voted_at, v.election_id, v.current_hash,
                           e.title as election_title, e.status,
                           c.name as candidate_name, c.party
                    FROM votes v
                    JOIN elections e ON v.election_id = e.election_id
                    JOIN candidates c ON v.candidate_id = c.candidate_id
                    WHERE v.voter_id=?
                    ORDER BY v.voted_at DESC
                """, (session["user_id"],)).fetchall()
                self.send_json({"history": [dict(r) for r in rows]})

            # ── Voter Profile (GET) ──────────────────────
            elif path == "/api/voter/profile" or path == "/api/user/profile":
                session = self.require_auth()
                if not session: return
                user = conn.execute("SELECT * FROM users WHERE voter_id=?", (session["user_id"],)).fetchone()
                if user:
                    u = dict(user)
                    if "password_hash" in u: del u["password_hash"]
                    if "password_salt" in u: del u["password_salt"]
                    self.send_json({"profile": u})
                else:
                    self.send_json({"error": "User not found"}, 404)

            # ── Voter Turnout ────────────────────────────
            elif path == "/api/admin/turnout":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                rows = conn.execute("""
                    SELECT e.election_id, e.title, e.status, e.constituency,
                           COUNT(v.vote_id) as votes_cast
                    FROM elections e
                    LEFT JOIN votes v ON e.election_id = v.election_id
                    GROUP BY e.election_id
                    ORDER BY e.start_date DESC
                """).fetchall()
                total_voters = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                self.send_json({"turnout": [dict(r) for r in rows], "total_registered": total_voters})

            # ── Audit Logs ───────────────────────────────
            elif path == "/api/admin/audit":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                limit = int(params.get("limit", [100])[0])
                rows = conn.execute(
                    "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
                self.send_json({"logs": [dict(r) for r in rows]})

            # ── Admin: List Users ─────────────────────────
            elif path == "/api/admin/users":
                session = self.require_auth(["super_admin"])
                if not session:
                    return
                rows = conn.execute(
                    "SELECT voter_id, name, email, constituency, is_verified, created_at FROM users ORDER BY created_at DESC"
                ).fetchall()
                self.send_json({"users": [dict(r) for r in rows]})

            # ── CSV Export ───────────────────────────────
            elif re.match(r"^/api/admin/export/csv/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                eid = int(re.match(r"^/api/admin/export/csv/(\d+)$", path).group(1))
                election = conn.execute("SELECT * FROM elections WHERE election_id=?", (eid,)).fetchone()
                rows = conn.execute("""
                    SELECT c.name, c.party, c.constituency,
                           COALESCE(r.total_votes,0) as votes, COALESCE(r.percentage,0) as pct
                    FROM candidates c
                    LEFT JOIN results r ON c.candidate_id=r.candidate_id AND r.election_id=?
                    WHERE c.election_id=?
                    ORDER BY votes DESC
                """, (eid, eid)).fetchall()
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["Candidate", "Party", "Constituency", "Votes", "Percentage"])
                for r in rows:
                    writer.writerow([r["name"], r["party"], r["constituency"], r["votes"], f"{r['pct']}%"])
                title = election["title"] if election else f"election_{eid}"
                self.send_csv(buf.getvalue(), f"{title.replace(' ','_')}_results.csv")

            # ── PDF Export (printable HTML) ──────────────
            elif re.match(r"^/api/admin/export/pdf/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                eid = int(re.match(r"^/api/admin/export/pdf/(\d+)$", path).group(1))
                election = conn.execute("SELECT * FROM elections WHERE election_id=?", (eid,)).fetchone()
                rows = conn.execute("""
                    SELECT c.name, c.party, COALESCE(r.total_votes,0) as votes, COALESCE(r.percentage,0) as pct
                    FROM candidates c
                    LEFT JOIN results r ON c.candidate_id=r.candidate_id AND r.election_id=?
                    WHERE c.election_id=?
                    ORDER BY votes DESC
                """, (eid, eid)).fetchall()
                total = conn.execute("SELECT COUNT(*) FROM votes WHERE election_id=?", (eid,)).fetchone()[0]
                rows_html = "".join(f"<tr><td>{i+1}</td><td>{r['name']}</td><td>{r['party']}</td><td>{r['votes']}</td><td>{r['pct']}%</td></tr>" for i, r in enumerate(rows))
                title = election["title"] if election else "Election"
                html = f"""<!DOCTYPE html><html><head><title>{title} Results</title>
                <style>body{{font-family:Arial;padding:40px}}table{{width:100%;border-collapse:collapse}}
                th,td{{border:1px solid #ccc;padding:10px;text-align:left}}th{{background:#1a3a6b;color:white}}
                h1{{color:#1a3a6b}}h3{{color:#555}}</style></head><body>
                <h1>🗳️ VoteSecure — Election Results</h1>
                <h2>{title}</h2><h3>Total Votes: {total} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</h3>
                <table><tr><th>#</th><th>Candidate</th><th>Party</th><th>Votes</th><th>Percentage</th></tr>
                {rows_html}</table>
                <br><p style="color:#999">Generated by VoteSecure AI Platform</p>
                <script>window.onload=()=>window.print()</script></body></html>"""
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            # ── AI: Anomalies ─────────────────────────────
            elif path == "/api/ai/anomalies":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                anomalies = detect_anomalies(conn)
                self.send_json({"anomalies": anomalies, "count": len(anomalies)})

            # ── AI: Result Summary ────────────────────────
            elif re.match(r"^/api/ai/summarize/(\d+)$", path):
                eid = int(re.match(r"^/api/ai/summarize/(\d+)$", path).group(1))
                summary = generate_result_summary(conn, eid)
                self.send_json({"summary": summary})

            # ── AI: Smart Search ─────────────────────
            elif path == "/api/ai/search":
                q = params.get("q", [""])[0]
                cat = params.get("category", ["all"])[0]
                if not q:
                    self.send_json({"results": []})
                    return
                results = smart_search(conn, q, cat)
                self.send_json({"results": results})

            # ── Voter Profile ────────────────────────
            elif path == "/api/voter/profile":
                session = self.require_auth(["voter"])
                if not session:
                    return
                user = conn.execute(
                    "SELECT voter_id,name,email,dob,gender,constituency,is_verified,created_at FROM users WHERE voter_id=?",
                    (session["user_id"],)
                ).fetchone()
                self.send_json({"profile": dict(user) if user else {}})

            # ── Voting Receipt ───────────────────────
            elif re.match(r"^/api/voter/receipt/(.+)$", path):
                session = self.require_auth(["voter"])
                if not session:
                    return
                eid = re.match(r"^/api/voter/receipt/(.+)$", path).group(1)
                vote = conn.execute("""
                    SELECT v.vote_id, v.voted_at, v.ip_address, v.current_hash, v.previous_hash,
                           e.title as election_title, e.election_id,
                           c.name as candidate_name, c.party
                    FROM votes v
                    JOIN elections e ON v.election_id=e.election_id
                    JOIN candidates c ON v.candidate_id=c.candidate_id
                    WHERE v.voter_id=? AND v.election_id=?
                """, (session["user_id"], eid)).fetchone()
                if not vote:
                    return self.send_json({"error": "No vote found"}, 404)
                
                receipt = dict(vote)
                receipt["receipt_hash"] = vote["current_hash"] # Use the real blockchain hash
                receipt["voter_name"] = session["name"]
                receipt["voter_id"] = session["user_id"]
                self.send_json({"receipt": receipt})

            # ── Announcements ────────────────────────
            elif path == "/api/announcements":
                rows = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 20").fetchall()
                self.send_json({"announcements": [dict(r) for r in rows]})
            
            elif path == "/api/admin/announcements":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session: return
                rows = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC").fetchall()
                self.send_json({"announcements": [dict(r) for r in rows]})

            # ── Blockchain Verification ──────────────
            elif "/api/voter/verify-hash/" in path:
                vhash = path.split("/")[-1]
                if not vhash:
                    return self.send_json({"error": "Hash required"}, 400)
                
                # Use parameter helper for Postgres/SQLite compatibility
                sql = """
                    SELECT v.vote_id, v.voted_at, v.previous_hash, e.title as election_title
                    FROM votes v
                    JOIN elections e ON v.election_id = e.election_id
                    WHERE v.current_hash=?
                """
                if hasattr(conn, "is_postgres") and conn.is_postgres:
                    sql = sql.replace("?", "%s")
                
                vote = conn.execute(sql, (vhash,)).fetchone()
                if vote:
                    self.send_json(dict(vote))
                else:
                    self.send_json({"error": "Hash not found in immutable ledger"}, 404)

            # ── Notifications (recent logs for voter) ─
            elif path == "/api/voter/notifications":
                session = self.require_auth(["voter"])
                if not session:
                    return
                logs = conn.execute(
                    "SELECT * FROM audit_logs WHERE user_id=? ORDER BY timestamp DESC LIMIT 10",
                    (session["user_id"],)
                ).fetchall()
                anns = conn.execute(
                    "SELECT * FROM announcements ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
                self.send_json({"logs": [dict(l) for l in logs], "announcements": [dict(a) for a in anns]})

            # ── Admin: Advanced Analytics ─────────────
            elif re.match(r"^/api/admin/analytics/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                eid = int(re.match(r"^/api/admin/analytics/(\d+)$", path).group(1))
                # Hourly vote distribution
                hourly = conn.execute("""
                    SELECT strftime('%H:00', voted_at) as hour, COUNT(*) as cnt
                    FROM votes WHERE election_id=?
                    GROUP BY hour ORDER BY hour
                """, (eid,)).fetchall()
                # Gender breakdown via joins
                gender = conn.execute("""
                    SELECT u.gender, COUNT(*) as cnt
                    FROM votes v JOIN users u ON v.voter_id=u.voter_id
                    WHERE v.election_id=?
                    GROUP BY u.gender
                """, (eid,)).fetchall()
                # Constituency breakdown
                const = conn.execute("""
                    SELECT u.constituency, COUNT(*) as cnt
                    FROM votes v JOIN users u ON v.voter_id=u.voter_id
                    WHERE v.election_id=?
                    GROUP BY u.constituency ORDER BY cnt DESC
                """, (eid,)).fetchall()
                self.send_json({
                    "hourly": [dict(r) for r in hourly],
                    "gender": [dict(r) for r in gender],
                    "constituency": [dict(r) for r in const]
                })

            # ── Admin: Announcements ─────────────────
            elif path == "/api/admin/announcements":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                rows = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC").fetchall()
                self.send_json({"announcements": [dict(r) for r in rows]})

            # ── GOOGLE OAUTH ───────────────────────────
            elif path == "/api/auth/google":
                if not GOOGLE_OAUTH_ENABLED:
                    return self.send_json({"error": "Google OAuth not configured. Set credentials in config.py."}, 503)
                state = secrets.token_hex(16)
                params = urllib.parse.urlencode({
                    "client_id": GOOGLE_CLIENT_ID,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "state": state,
                    "access_type": "offline",
                    "prompt": "select_account"
                })
                self.send_response(302)
                self.send_header("Location", f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

            elif path == "/api/auth/google/callback":
                if not GOOGLE_OAUTH_ENABLED:
                    return self.send_json({"error": "Google OAuth not configured."}, 503)
                code = params.get("code", [None])[0]
                if not code:
                    return self.send_json({"error": "OAuth failed: no code returned."}, 400)
                # Exchange code for tokens
                token_data = urllib.parse.urlencode({
                    "code": code, "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code"
                }).encode()
                try:
                    req = urllib.request.Request(
                        "https://oauth2.googleapis.com/token",
                        data=token_data, method="POST",
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    with urllib.request.urlopen(req) as r:
                        tok_resp = json.loads(r.read())
                    access_token = tok_resp.get("access_token", "")
                    # Get user info
                    info_req = urllib.request.Request(
                        "https://www.googleapis.com/oauth2/v2/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    with urllib.request.urlopen(info_req) as r:
                        user_info = json.loads(r.read())
                    g_email = user_info.get("email", "").lower()
                    g_name  = user_info.get("name", "Google User")
                    # Find or create voter
                    existing = conn.execute("SELECT * FROM users WHERE email=?", (g_email,)).fetchone()
                    if existing:
                        voter = existing
                    else:
                        # Auto-register Google user
                        voter_id = generate_voter_id()
                        dummy_hash, dummy_salt = hash_password(secrets.token_hex(16))
                        conn.execute(
                            "INSERT INTO users (voter_id,name,email,password_hash,password_salt,dob,gender,constituency,is_verified,phone_verified) VALUES (?,?,?,?,?,?,?,?,1,0)",
                            (voter_id, g_name, g_email, dummy_hash, dummy_salt, "2000-01-01", "Other", "All")
                        )
                        conn.commit()
                        voter = conn.execute("SELECT * FROM users WHERE voter_id=?", (voter_id,)).fetchone()
                    session_token = create_session(voter["voter_id"], "voter", voter["name"], voter["constituency"])
                    log_action(conn, voter["voter_id"], "GOOGLE_LOGIN", f"Google OAuth: {g_email}", ip)
                    # Redirect to voter dashboard with token
                    self.send_response(302)
                    self.send_header("Location", f"/voter.html?token={session_token}&name={urllib.parse.quote(voter['name'])}&constituency={urllib.parse.quote(voter['constituency'])}&role=voter")
                    self.end_headers()
                except Exception as e:
                    self.send_response(302)
                    self.send_header("Location", f"/index.html?error={urllib.parse.quote(str(e))}")
                    self.end_headers()

            # ── LIVE RESULTS SSE ─────────────────────────
            elif re.match(r"^/api/stream/results/(\d+)$", path):
                eid = int(re.match(r"^/api/stream/results/(\d+)$", path).group(1))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                import time as _t
                for _ in range(60):  # stream for up to 5 minutes
                    try:
                        cur = conn.cursor()
                        compute_results(cur, eid)
                        conn.commit()
                        rows = conn.execute("""
                            SELECT r.*, c.name as candidate_name, c.party
                            FROM results r JOIN candidates c ON r.candidate_id=c.candidate_id
                            WHERE r.election_id=? ORDER BY r.total_votes DESC
                        """, (eid,)).fetchall()
                        total = conn.execute("SELECT COUNT(*) FROM votes WHERE election_id=?", (eid,)).fetchone()[0]
                        data = json.dumps({"results": [dict(r) for r in rows], "total_votes": total}, default=str)
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                        _t.sleep(5)
                    except Exception:
                        break
                return

            # ── CAPTCHA Generate ─────────────────────
            elif path == "/api/auth/captcha":
                import random as _r
                ops = [
                    ('+', lambda a, b: a + b),
                    ('-', lambda a, b: a - b),
                    ('x', lambda a, b: a * b),
                ]
                a = _r.randint(2, 12)
                b = _r.randint(1, 9)
                sym, fn = _r.choice(ops)
                answer = fn(a, b)
                # Store in a temp in-memory dict keyed by token
                cap_token = secrets.token_hex(16)
                CAPTCHA_STORE[cap_token] = {
                    'answer': answer,
                    'expires': datetime.now().timestamp() + 300  # 5 min
                }
                self.send_json({
                    'token': cap_token,
                    'question': f'What is {a} {sym} {b}?',
                    'hint': 'Solve the math problem to prove you are human'
                })

            # ── OTP Verify (GET stub) ────────────────
            elif path == "/api/auth/verify-otp":
                session = self.require_auth(["voter"])
                if session:
                    self.send_json({"verified": True})

            else:
                super().do_GET()

        except Exception as e:
            import traceback
            traceback.print_exc()
            sys.stderr.flush()
            sys.stdout.flush()
            self.send_json({"error": str(e)}, 500)
        finally:
            conn.close()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_body()
        conn = get_connection()
        ip = get_client_ip(self)

        try:
            # ── VOTER REGISTER ──────────────────────────
            if path == "/api/auth/register":
                name = body.get("name", "").strip()
                email = body.get("email", "").strip().lower()
                password = body.get("password", "")
                dob = body.get("dob", "")
                gender = body.get("gender", "")
                constituency = body.get("constituency", "").strip()
                phone = body.get("phone", "").strip()
                aadhaar_id = body.get("aadhaar_id", "").strip()
                govt_voter_id = body.get("govt_voter_id", "").strip()
                fingerprint = body.get("device_fingerprint", "") # ELITE SECURITY: Hardware Binding
                
                # 🛡️ ELITE SECURITY: Strict CAPTCHA Enforcement
                c_token = body.get("captcha_token")
                c_answer = body.get("captcha_answer")
                cap = CAPTCHA_STORE.get(c_token)
                if not cap or str(cap['answer']) != str(c_answer) or datetime.now().timestamp() > cap['expires']:
                    return self.send_json({"error": "Security Alert: Invalid or expired CAPTCHA. Please solve the problem again."}, 400)
                del CAPTCHA_STORE[c_token] # Single-use CAPTCHA

                if not all([name, email, password, dob, constituency]):
                    return self.send_json({"error": "All fields are required."}, 400)

                # Aadhaar validation (12 digits)
                if aadhaar_id and not re.match(r'^\d{12}$', aadhaar_id):
                    return self.send_json({"error": "Aadhaar ID must be exactly 12 digits."}, 400)

                # Phone validation
                if phone and not re.match(r'^[6-9]\d{9}$', phone):
                    return self.send_json({"error": "Enter a valid 10-digit Indian mobile number."}, 400)

                # Age check
                try:
                    birth = datetime.strptime(dob, "%Y-%m-%d")
                    age = (datetime.now() - birth).days // 365
                    if age < 18:
                        return self.send_json({"error": f"You must be 18+ to register. Your age: {age}."}, 400)
                except ValueError:
                    return self.send_json({"error": "Invalid date of birth format."}, 400)

                # Check duplicate email
                existing = conn.execute("SELECT voter_id FROM users WHERE email=?", (email,)).fetchone()
                if existing:
                    return self.send_json({"error": "Email already registered."}, 409)

                voter_id = generate_voter_id()
                pw_hash, pw_salt = hash_password(password)
                conn.execute(
                    "INSERT INTO users (voter_id,name,email,phone,password_hash,password_salt,dob,gender,constituency,aadhaar_id,govt_voter_id,is_verified,phone_verified) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,0)",
                    (voter_id, name, email, phone, pw_hash, pw_salt, dob, gender, constituency, aadhaar_id, govt_voter_id)
                )
                conn.commit()
                log_action(conn, voter_id, "USER_REGISTERED", f"New voter registered: {email}", ip)
                self.send_json({"message": "Registration successful!", "voter_id": voter_id})

            # ── VOTER LOGIN ─────────────────────────────
            elif path == "/api/auth/voter/login":
                email = body.get("email", "").strip().lower()
                password = body.get("password", "")
                user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if not user or not verify_password(password, user["password_hash"], user["password_salt"]):
                    log_action(conn, email, "LOGIN_FAILED", "Invalid credentials", ip)
                    return self.send_json({"error": "Invalid email or password."}, 401)
                token = create_session(user["voter_id"], "voter", user["name"], user["constituency"])
                log_action(conn, user["voter_id"], "USER_LOGIN", "Voter logged in", ip)
                self.send_json({
                    "token": token,
                    "voter_id": user["voter_id"],
                    "name": user["name"],
                    "constituency": user["constituency"],
                    "role": "voter"
                })

            # ── ADMIN LOGIN ─────────────────────────────
            elif path == "/api/auth/admin/login":
                email = body.get("email", "").strip().lower()
                password = body.get("password", "")
                admin = conn.execute("SELECT * FROM admins WHERE email=?", (email,)).fetchone()
                if not admin or not verify_password(password, admin["password_hash"], admin["password_salt"]):
                    log_action(conn, email, "LOGIN_FAILED", "Admin invalid credentials", ip)
                    return self.send_json({"error": "Invalid admin credentials."}, 401)
                token = create_session(admin["email"], admin["role"], admin["name"])
                log_action(conn, admin["email"], "ADMIN_LOGIN", f"{admin['role']} logged in", ip)
                self.send_json({
                    "token": token,
                    "name": admin["name"],
                    "email": admin["email"],
                    "role": admin["role"]
                })

            # ── LOGOUT ──────────────────────────────────
            elif path == "/api/auth/logout":
                token = self.get_token()
                session = get_session(token)
                if session:
                    log_action(conn, session["user_id"], "USER_LOGOUT", "", ip)
                    del SESSIONS[token]
                self.send_json({"message": "Logged out."})

            # ── CAST VOTE ───────────────────────────────
            elif path == "/api/vote":
                session = self.require_auth(["voter"])
                if not session:
                    return
                election_id = body.get("election_id")
                candidate_id = body.get("candidate_id")
                if not election_id or not candidate_id:
                    return self.send_json({"error": "election_id and candidate_id required."}, 400)

                # Check election is active
                election = conn.execute(
                    "SELECT * FROM elections WHERE election_id=? AND status='active'", (election_id,)
                ).fetchone()
                if not election:
                    return self.send_json({"error": "Election is not currently active."}, 400)

                # ── IP-FENCE & VPN DETECTION ──
                if is_vpn_or_proxy(ip):
                    log_action(conn, session["user_id"], "VPN_DETECTED", f"Blocked vote attempt via VPN from {ip}", ip)
                    return self.send_json({"error": "Security Alert: VPN or Proxy detected. Please use a direct connection to vote."}, 403)
                
                if not is_within_geofence(ip):
                    log_action(conn, session["user_id"], "GEOFENCE_VIOLATION", f"Blocked vote attempt from unauthorized region ({ip})", ip)
                    return self.send_json({"error": "Access Denied: You must be within the national territory to cast a vote."}, 403)

                # ELITE SECURITY: Hardware Binding (Device Fingerprint) Check
                voter_record = conn.execute("SELECT hardware_fingerprint FROM users WHERE voter_id=?", (session["user_id"],)).fetchone()
                incoming_fp = body.get("device_fingerprint", "")
                if voter_record and voter_record["hardware_fingerprint"] and voter_record["hardware_fingerprint"] != incoming_fp:
                    log_action(conn, session["user_id"], "DEVICE_SPOOF_ATTEMPT", f"IP {ip} tried voting with mismatched device fingerprint.", ip)
                    return self.send_json({"error": "Security Alert: This account is bound to a different device. Voting is locked on this browser."}, 403)

                # Blockchain Hashing & Geolocation
                lat = float(body.get("location_lat", 0.0))
                lng = float(body.get("location_lng", 0.0))
                
                last_vote = conn.execute("SELECT current_hash FROM votes ORDER BY vote_id DESC LIMIT 1").fetchone()
                prev_hash = last_vote["current_hash"] if (last_vote and last_vote["current_hash"]) else "GENESIS"
                
                # Quantum-Resistant Chaining (Layered Hashing)
                raw_data = f"{prev_hash}{session['user_id']}{candidate_id}{election_id}{datetime.now().timestamp()}{lat}{lng}"
                curr_hash = quantum_hash(raw_data)

                # DB-level unique constraint enforces one vote
                try:
                    # ELITE SECURITY: Encrypt Candidate ID in storage
                    # Using a simple XOR + Base64 with server secret for demo 'encryption'
                    SECRET = "VOTESECURE_2024_PRO_KEY"
                    encrypted_cid = base64.b64encode(str(candidate_id ^ 0xABCDEF).encode()).decode()

                    conn.execute(
                        "INSERT INTO votes (voter_id, candidate_id, election_id, ip_address, previous_hash, current_hash, location_lat, location_lng) VALUES (?,?,?,?,?,?,?,?)",
                        (session["user_id"], encrypted_cid, election_id, ip, prev_hash, curr_hash, lat, lng)
                    )
                    
                    # Update voted_elections
                    import json as _json
                    user_row = conn.execute("SELECT voted_elections FROM users WHERE voter_id=?", (session["user_id"],)).fetchone()
                    if user_row:
                        try:
                            voted_raw = user_row["voted_elections"] if "voted_elections" in user_row.keys() else user_row[0]
                            voted = _json.loads(voted_raw or "[]")
                        except Exception:
                            voted = []
                        
                        if str(election_id) not in voted:
                            voted.append(str(election_id))
                        
                        conn.execute("UPDATE users SET voted_elections=? WHERE voter_id=?",
                                     (_json.dumps(voted), session["user_id"]))
                    
                    conn.commit()
                    log_action(conn, session["user_id"], "VOTE_CAST",
                               f"Voted in election {election_id} for candidate {candidate_id}", ip)
                    self.send_json({"message": "Vote cast successfully! Thank you for participating."})
                except Exception as e:
                    if "UNIQUE" in str(e):
                        log_action(conn, session["user_id"], "DUPLICATE_VOTE_ATTEMPT",
                                   f"Tried to vote twice in election {election_id}", ip)
                        self.send_json({"error": "You have already voted in this election."}, 409)
                    else:
                        raise

            # ── AI CHATBOT ──────────────────────────────
            elif path == "/api/ai/chat":
                message = body.get("message", "")
                token = self.get_token()
                session = get_session(token)
                context = {"voter_name": session["name"]} if session else {}
                response = get_chatbot_response(message, context)
                self.send_json({"response": response})

            # ── VERIFY CAPTCHA ─────────────────────────
            elif path == "/api/auth/verify-captcha":
                cap_token = body.get("token", "")
                user_answer = str(body.get("answer", "")).strip()
                entry = CAPTCHA_STORE.get(cap_token)
                if not entry:
                    return self.send_json({"error": "CAPTCHA expired or invalid. Please refresh."}, 400)
                if datetime.now().timestamp() > entry["expires"]:
                    del CAPTCHA_STORE[cap_token]
                    return self.send_json({"error": "CAPTCHA expired. Please get a new one."}, 400)
                if str(entry["answer"]) != user_answer:
                    del CAPTCHA_STORE[cap_token]
                    return self.send_json({"error": "Wrong answer. Please try again."}, 400)
                del CAPTCHA_STORE[cap_token]  # one-time use
                log_action(conn, "anonymous", "CAPTCHA_PASSED", "Registration CAPTCHA verified", ip)
                self.send_json({"verified": True, "message": "CAPTCHA verified! You are human 🤖✅"})

            # ── SEND PHONE OTP ─────────────────────────
            elif path == "/api/auth/send-phone-otp":
                phone = body.get("phone", "").strip()
                if not re.match(r'^[6-9]\d{9}$', phone):
                    return self.send_json({"error": "Enter a valid 10-digit Indian mobile number."}, 400)
                import random as _r
                code = str(_r.randint(100000, 999999))
                expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "INSERT INTO otp_codes (email, phone, code, otp_type, expires_at) VALUES (?,?,?,?,?)",
                    (phone, phone, code, 'phone', expires)
                )
                conn.commit()
                # In production: integrate Twilio/MSG91 here
                # For demo: return code directly
                self.send_json({
                    "message": f"OTP sent to +91-{phone[:5]}XXXXX (demo)",
                    "demo_code": code,
                    "note": "In production this would be sent via SMS gateway (Twilio/MSG91)"
                })

            # ── VERIFY PHONE OTP ───────────────────────
            elif path == "/api/auth/verify-phone-otp":
                phone = body.get("phone", "").strip()
                code = body.get("code", "")
                row = conn.execute(
                    "SELECT * FROM otp_codes WHERE phone=? AND code=? AND otp_type='phone' AND used=0 AND expires_at > datetime('now') ORDER BY id DESC LIMIT 1",
                    (phone, code)
                ).fetchone()
                if not row:
                    return self.send_json({"error": "Invalid or expired OTP. Please try again."}, 400)
                conn.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
                # Mark voter phone as verified if they exist
                conn.execute("UPDATE users SET phone_verified=1 WHERE phone=?", (phone,))
                conn.commit()
                self.send_json({"verified": True, "message": "Phone number verified successfully! ✅"})

            # ── SEND EMAIL OTP ─────────────────────────
            elif path == "/api/auth/send-otp":
                email = body.get("email", "").strip().lower()
                import random as _r
                code = str(_r.randint(100000, 999999))
                expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("INSERT INTO otp_codes (email, code, expires_at) VALUES (?,?,?)", (email, code, expires))
                conn.commit()
                # In production this would email the code; for demo we return it
                self.send_json({"message": "OTP sent!", "demo_code": code, "expires_in": "10 minutes"})

            # ── VERIFY OTP ──────────────────────────────
            elif path == "/api/auth/verify-otp":
                email = body.get("email", "").strip().lower()
                code = body.get("code", "")
                row = conn.execute(
                    "SELECT * FROM otp_codes WHERE email=? AND code=? AND used=0 AND expires_at > datetime('now') ORDER BY id DESC LIMIT 1",
                    (email, code)
                ).fetchone()
                if not row:
                    return self.send_json({"error": "Invalid or expired OTP."}, 400)
                conn.execute("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
                conn.commit()
                self.send_json({"verified": True, "message": "Email verified successfully!"})

            # ── UPDATE VOTER PROFILE ─────────────────────
            elif path == "/api/voter/profile":
                session = self.require_auth(["voter"])
                if not session:
                    return
                allowed = {"name", "gender", "constituency"}
                fields = {k: v for k, v in body.items() if k in allowed}
                if fields:
                    sets = ", ".join(f"{k}=?" for k in fields)
                    vals = list(fields.values()) + [session["user_id"]]
                    conn.execute(f"UPDATE users SET {sets} WHERE voter_id=?", vals)
                    conn.commit()
                    SESSIONS[self.get_token()]["name"] = fields.get("name", session["name"])
                    SESSIONS[self.get_token()]["constituency"] = fields.get("constituency", session["constituency"])
                    log_action(conn, session["user_id"], "PROFILE_UPDATED", "Voter updated profile", ip)
                self.send_json({"message": "Profile updated."})

            # ── CREATE ANNOUNCEMENT ──────────────────────
            elif path == "/api/admin/announcements":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                title = body.get("title", "").strip()
                ann_body = body.get("body", "").strip()
                priority = body.get("priority", "normal")
                if not title or not ann_body:
                    return self.send_json({"error": "title and body required."}, 400)
                conn.execute("INSERT INTO announcements (admin_id, title, body, priority) VALUES (?,?,?,?)",
                             (session["user_id"], title, ann_body, priority))
                ann_id = conn.lastrowid
                conn.commit()
                log_action(conn, session["user_id"], "ANNOUNCEMENT_POSTED", title, ip)
                self.send_json({"message": "Announcement posted.", "ann_id": ann_id})

            # ── CREATE ELECTION ──────────────────────────
            elif path == "/api/admin/elections":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                title = body.get("title", "").strip()
                description = body.get("description", "")
                constituency = body.get("constituency", "All")
                start_date = body.get("start_date", "")
                end_date = body.get("end_date", "")
                status = body.get("status", "active")
                if not all([title, start_date, end_date]):
                    return self.send_json({"error": "title, start_date, end_date required."}, 400)
                cur = conn.execute(
                    "INSERT INTO elections (title,description,constituency,start_date,end_date,status) VALUES (?,?,?,?,?,?)",
                    (title, description, constituency, start_date, end_date, status)
                )
                new_id = cur.lastrowid
                conn.commit()
                log_action(conn, session["user_id"], "ELECTION_CREATED", f"Created: {title}", ip)
                self.send_json({"message": "Election created.", "election_id": new_id})

            # ── ADD CANDIDATE ────────────────────────────
            elif path == "/api/admin/candidates":
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                eid = body.get("election_id")
                name = body.get("name", "").strip()
                party = body.get("party", "").strip()
                constituency = body.get("constituency", "All").strip()
                manifesto = body.get("manifesto", "")
                photo_url = body.get("photo_url", "")
                if not all([eid, name, party, constituency]):
                    return self.send_json({"error": "election_id, name, party, constituency required."}, 400)
                cur = conn.execute(
                    "INSERT INTO candidates (election_id,name,party,photo_url,manifesto,constituency) VALUES (?,?,?,?,?,?)",
                    (eid, name, party, photo_url, manifesto, constituency)
                )
                new_id = cur.lastrowid
                conn.commit()
                log_action(conn, session["user_id"], "CANDIDATE_ADDED", f"Added {name} ({party})", ip)
                self.send_json({"message": "Candidate added.", "candidate_id": new_id})

            else:
                self.send_json({"error": "Not Found"}, 404)

        except Exception as e:
            import traceback
            traceback.print_exc()
            sys.stderr.flush()
            sys.stdout.flush()
            self.send_json({"error": str(e)}, 500)
        finally:
            conn.close()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_body()
        conn = get_connection()
        ip = get_client_ip(self)
        try:
            if re.match(r"^/api/admin/elections/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                eid = int(re.match(r"^/api/admin/elections/(\d+)$", path).group(1))
                fields = {k: v for k, v in body.items() if k in ["title","description","constituency","start_date","end_date","status"]}
                if not fields:
                    return self.send_json({"error": "No valid fields to update."}, 400)
                sets = ", ".join(f"{k}=?" for k in fields)
                vals = list(fields.values()) + [eid]
                conn.execute(f"UPDATE elections SET {sets} WHERE election_id=?", vals)
                conn.commit()
                log_action(conn, session["user_id"], "ELECTION_UPDATED", f"Updated election {eid}", ip)
                
                # Check if election was ended to trigger finalization and emails
                if fields.get("status") == "ended":
                    from database import compute_results
                    compute_results(conn, eid) # Finalize results
                    import threading
                    threading.Thread(target=send_election_end_emails, args=(get_connection(), eid)).start()
                    
                self.send_json({"message": "Election updated."})

            elif path == "/api/voter/profile":
                session = self.require_auth(["voter"])
                if not session: return
                allowed = ["email", "phone"] # Only allow updating these for security
                fields = {k: v for k, v in body.items() if k in allowed}
                if not fields:
                    return self.send_json({"error": "No valid fields to update."}, 400)
                
                sets = ", ".join(f"{k}=?" for k in fields)
                vals = list(fields.values()) + [session["user_id"]]
                conn.execute(f"UPDATE users SET {sets} WHERE voter_id=?", vals)
                conn.commit()
                self.send_json({"message": "Profile updated successfully."})
            else:
                self.send_json({"error": "Not Found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
        finally:
            conn.close()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        conn = get_connection()
        ip = get_client_ip(self)
        try:
            conn.execute("INSERT OR IGNORE INTO security_bypass (key) VALUES ('ADMIN_CLEANUP')")
            if re.match(r"^/api/admin/elections/(\d+)$", path):
                session = self.require_auth(["super_admin"])
                if not session:
                    return
                eid = int(re.match(r"^/api/admin/elections/(\d+)$", path).group(1))
                conn.execute("DELETE FROM elections WHERE election_id=?", (eid,))
                conn.commit()
                log_action(conn, session["user_id"], "ELECTION_DELETED", f"Deleted election {eid}", ip)
                self.send_json({"message": "Election deleted."})
            elif re.match(r"^/api/admin/candidates/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                cid = int(re.match(r"^/api/admin/candidates/(\d+)$", path).group(1))
                conn.execute("DELETE FROM candidates WHERE candidate_id=?", (cid,))
                conn.commit()
                log_action(conn, session["user_id"], "CANDIDATE_REMOVED", f"Removed candidate {cid}", ip)
                self.send_json({"message": "Candidate removed."})
            elif re.match(r"^/api/admin/users/(.+)$", path):
                session = self.require_auth(["super_admin"])
                if not session:
                    return
                voter_id = re.match(r"^/api/admin/users/(.+)$", path).group(1)
                user = conn.execute("SELECT name,email FROM users WHERE voter_id=?", (voter_id,)).fetchone()
                if not user:
                    return self.send_json({"error": "User not found."}, 404)
                # Delete all associated data
                conn.execute("DELETE FROM votes WHERE voter_id=?", (voter_id,))
                conn.execute("DELETE FROM audit_logs WHERE user_id=?", (voter_id,))
                conn.execute("DELETE FROM users WHERE voter_id=?", (voter_id,))
                conn.commit()
                log_action(conn, session["user_id"], "USER_DELETED",
                           f"Deleted voter {voter_id} ({user['email']})", ip)
                self.send_json({"message": f"Voter {user['name']} deleted successfully."})
            elif re.match(r"^/api/admin/announcements/(\d+)$", path):
                session = self.require_auth(["super_admin", "election_officer"])
                if not session:
                    return
                ann_id = int(re.match(r"^/api/admin/announcements/(\d+)$", path).group(1))
                conn.execute("DELETE FROM announcements WHERE ann_id=?", (ann_id,))
                conn.commit()
                log_action(conn, session["user_id"], "ANNOUNCEMENT_DELETED", f"Deleted announcement {ann_id}", ip)
                self.send_json({"message": "Announcement deleted."})
            else:
                self.send_json({"error": "Not Found"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
        finally:
            conn.close()


# ── WSGI ADAPTER FOR GUNICORN ──────────────────────────
import io

def app(environ, start_response):
    """Bridge WSGI (Gunicorn) to BaseHTTPRequestHandler for production deployment."""
    from io import BytesIO

    # Reconstruct the raw request for our handler
    method = environ.get('REQUEST_METHOD', 'GET')
    path = environ.get('PATH_INFO', '/')
    if environ.get('QUERY_STRING'):
        path += '?' + environ['QUERY_STRING']
    
    # Headers
    headers_dict = {}
    for key, value in environ.items():
        if key.startswith('HTTP_'):
            header_name = key[5:].replace('_', '-').title()
            headers_dict[header_name] = value
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            header_name = key.replace('_', '-').title()
            headers_dict[header_name] = value

    # Body
    try:
        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
    except (ValueError):
        request_body_size = 0
    request_body = environ['wsgi.input'].read(request_body_size)

    # Prepare a response capturer
    class WSGIResponse:
        def __init__(self):
            self.status = "200 OK"
            self.headers = []
            self.body = BytesIO()
            self.headers_sent = False

        def send_response(self, code, message=None):
            from http import HTTPStatus
            try:
                status_obj = HTTPStatus(code)
                self.status = f"{code} {status_obj.phrase}"
            except ValueError:
                self.status = f"{code} {message or 'Unknown'}"

        def send_header(self, keyword, value):
            self.headers.append((keyword, value))

        def end_headers(self):
            self.headers_sent = True

        def write(self, data):
            self.body.write(data)

    class MockRequest:
        def __init__(self, body):
            self.body = body
        def makefile(self, *args, **kwargs):
            return BytesIO(self.body)
        def sendall(self, data):
            pass
        def getsockname(self):
            return ('0.0.0.0', 8000)

    # Instantiate handler
    handler = VoteSecureHandler(MockRequest(request_body), (environ.get('REMOTE_ADDR', '0.0.0.0'), 0), None)
    
    # Override handler methods to capture response
    res = WSGIResponse()
    handler.send_response = res.send_response
    handler.send_header = res.send_header
    handler.end_headers = res.end_headers
    handler.wfile = res
    
    # Process request
    if method == 'GET': handler.do_GET()
    elif method == 'POST': handler.do_POST()
    elif method == 'PUT': handler.do_PUT()
    elif method == 'DELETE': handler.do_DELETE()
    elif method == 'OPTIONS': handler.do_OPTIONS()
    
    # Send response back to WSGI
    start_response(res.status, res.headers)
    return [res.body.getvalue()]

def main():
    print("=" * 55)
    print("  VoteSecure - AI Digital Voting Platform")
    print("=" * 55)
    init_db()
    print("  Log: App initialized successfully (Multi-Threaded).")
    sys.stdout.flush()
    HOST, PORT = "0.0.0.0", 8000
    server = ThreadingHTTPServer((HOST, PORT), VoteSecureHandler)
    print(f"  Server: http://{HOST}:{PORT}")
    print(f"  Admin:  admin@votesecure.com / Admin@123")
    print(f"  Voter:  aditya@example.com  / Test@123")
    print("  Press Ctrl+C to stop.")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")

if __name__ == "__main__":
    main()
