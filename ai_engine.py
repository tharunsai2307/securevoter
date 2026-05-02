"""
VoteSecure - AI Engine
Chatbot, Anomaly Detection, Result Summarizer, Smart Search
"""

import json
import re
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────
# 1. AI CHATBOT (Rule-based NLP)
# ─────────────────────────────────────────────────────────

CHATBOT_KB = [
    {
        "patterns": ["hello", "hi", "hey", "greet", "good morning", "good evening"],
        "response": "👋 Hello! I'm VoteBot, your AI voting assistant. I can help you with registration, voting, results, and more. What would you like to know?"
    },
    {
        "patterns": ["how to vote", "how do i vote", "cast vote", "voting process", "vote kaise"],
        "response": "🗳️ To cast your vote:\n1. Login with your voter credentials\n2. Go to **Vote** section\n3. Select your active election\n4. Click on your preferred candidate\n5. Confirm your choice\n\nRemember: You can only vote **once per election**."
    },
    {
        "patterns": ["register", "sign up", "new voter", "create account", "registration"],
        "response": "📝 To register as a voter:\n1. Click **Register** on the home page\n2. Fill in your personal details\n3. You must be **18 years or older**\n4. Enter your constituency\n5. Submit to receive your Voter ID\n\nYour Voter ID will be in the format VTR-YYYY-XXXX."
    },
    {
        "patterns": ["forgot password", "reset password", "cant login", "login problem"],
        "response": "🔑 If you've forgotten your password, please contact your election officer at officer@votesecure.com with your registered email and Voter ID for assistance."
    },
    {
        "patterns": ["result", "who won", "winner", "election result", "outcome"],
        "response": "📊 To view election results:\n1. Go to the **Results** tab in your dashboard\n2. Select the election you want to view\n3. You'll see live bar & pie charts, vote percentages, and the winner announcement\n\nResults are updated in real-time!"
    },
    {
        "patterns": ["age", "eligible", "eligibility", "18", "minimum age"],
        "response": "✅ To be eligible to vote, you must:\n- Be **18 years of age or older**\n- Be a registered citizen\n- Have a valid email address\n- Be registered in a constituency\n\nOur system automatically verifies your age during registration."
    },
    {
        "patterns": ["constituency", "area", "region", "location"],
        "response": "🗺️ Your constituency determines which elections you can participate in. Elections may be:\n- **All** – Open to all voters nationwide\n- **Constituency-specific** – Only for voters in that area\n\nYou can see your constituency in your voter profile."
    },
    {
        "patterns": ["secure", "safe", "security", "privacy", "anonymous"],
        "response": "🔒 VoteSecure uses multiple layers of security:\n- Passwords are hashed with SHA-256 + salt\n- One vote per election enforced at database level\n- All actions are logged in the audit trail\n- Your vote choice remains confidential\n- Session expires automatically after inactivity"
    },
    {
        "patterns": ["voter id", "my id", "what is my voter id", "voter number"],
        "response": "🪪 Your Voter ID is a unique identifier assigned when you register. It follows the format **VTR-YYYY-XXXX** (e.g., VTR-2024-0001). You can find it on your voter dashboard after logging in."
    },
    {
        "patterns": ["double vote", "vote twice", "vote again", "second vote"],
        "response": "🚫 You cannot vote twice in the same election. VoteSecure enforces a **strict one-vote policy** at both the application and database level. Any attempt to vote twice will be blocked and logged."
    },
    {
        "patterns": ["candidate", "candidates", "party", "parties", "who is running"],
        "response": "👤 To view candidates:\n1. Go to the **Vote** section\n2. Select an active election\n3. You'll see all candidates with their **party, manifesto, and constituency**\n\nYou can also use Smart Search to find candidates by party or name."
    },
    {
        "patterns": ["history", "my votes", "past votes", "voting history", "voted before"],
        "response": "📋 Your complete voting history is available in the **My History** tab on your dashboard. It shows all elections you've participated in, when you voted, and the election outcome."
    },
    {
        "patterns": ["contact", "help", "support", "admin", "officer"],
        "response": "📧 For support, contact:\n- **Election Officer**: officer@votesecure.com\n- **Technical Support**: admin@votesecure.com\n\nOur team typically responds within 24 hours."
    },
    {
        "patterns": ["thank", "thanks", "thank you", "thx"],
        "response": "😊 You're welcome! Is there anything else I can help you with? Happy voting!"
    },
    {
        "patterns": ["bye", "goodbye", "exit", "quit", "close"],
        "response": "👋 Goodbye! Remember, every vote counts. See you at the polls!"
    },
    {
        "patterns": ["anomaly", "suspicious", "fraud", "fake vote", "rigging"],
        "response": "🛡️ VoteSecure has an AI-powered anomaly detection system that monitors for suspicious patterns like:\n- Multiple votes from the same IP address\n- Unusual login attempts\n- Out-of-hours voting activity\n\nAll suspicious activity is flagged and reviewed by admins."
    },
    {
        "patterns": ["what is votesecure", "about", "what can you do", "platform"],
        "response": "🏛️ **VoteSecure** is an AI-powered Digital Voting and Election Management Platform. It offers:\n- 🗳️ Secure digital voting\n- 📊 Real-time results with charts\n- 🤖 AI-powered recommendations & anomaly detection\n- 🔒 Bank-grade security\n- 👤 Admin & voter dashboards\n\nBuilt for transparent, fair elections!"
    },
]


def get_chatbot_response(message: str, context: dict = None) -> str:
    """Return AI chatbot response based on keyword matching."""
    msg = message.lower().strip()
    context = context or {}

    # Score each KB entry
    best_score = 0
    best_response = None

    for entry in CHATBOT_KB:
        score = 0
        for pattern in entry["patterns"]:
            if pattern in msg:
                score += len(pattern)  # longer match = better
        if score > best_score:
            best_score = score
            best_response = entry["response"]

    # Context-aware personalization
    if best_response and context.get("voter_name"):
        if "hello" in msg or "hi" in msg or "hey" in msg:
            return f"👋 Hello, **{context['voter_name']}**! Great to see you. {best_response}"

    if best_response:
        return best_response

    # Fallback
    return ("🤔 I'm not sure I understood that. Try asking about:\n"
            "- **How to vote**\n- **Registration**\n- **Results**\n"
            "- **Security**\n- **Candidates**\n\nOr type **help** for more options.")


# ─────────────────────────────────────────────────────────
# 2. ANOMALY DETECTION
# ─────────────────────────────────────────────────────────

def detect_anomalies(conn) -> list:
    """
    Detect suspicious voting patterns from the database.
    Returns a list of anomaly dicts with severity and description.
    """
    anomalies = []
    cur = conn.cursor()

    # ── Anomaly 1: Multiple votes from same IP in same election ──
    rows = cur.execute("""
        SELECT ip_address, election_id, COUNT(*) as cnt
        FROM votes
        WHERE ip_address IS NOT NULL AND ip_address != ''
        GROUP BY ip_address, election_id
        HAVING cnt > 1
    """).fetchall()
    for row in rows:
        election = cur.execute("SELECT title FROM elections WHERE election_id=?", (row["election_id"],)).fetchone()
        anomalies.append({
            "type": "DUPLICATE_IP_VOTE",
            "severity": "HIGH",
            "description": f"IP {row['ip_address']} cast {row['cnt']} votes in election '{election['title'] if election else row['election_id']}'.",
            "election_id": row["election_id"],
            "ip_address": row["ip_address"],
            "count": row["cnt"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # ── Anomaly 2: Failed login spikes (5+ failed attempts logged) ──
    rows = cur.execute("""
        SELECT user_id, COUNT(*) as cnt
        FROM audit_logs
        WHERE action = 'LOGIN_FAILED'
          AND timestamp >= datetime('now', '-1 hour')
        GROUP BY user_id
        HAVING cnt >= 3
    """).fetchall()
    for row in rows:
        anomalies.append({
            "type": "BRUTE_FORCE_ATTEMPT",
            "severity": "MEDIUM",
            "description": f"User '{row['user_id']}' had {row['cnt']} failed login attempts in the last hour.",
            "user_id": row["user_id"],
            "count": row["cnt"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # ── Anomaly 3: Votes cast outside election window ──
    rows = cur.execute("""
        SELECT v.vote_id, v.voter_id, v.election_id, v.voted_at,
               e.start_date, e.end_date, e.title
        FROM votes v
        JOIN elections e ON v.election_id = e.election_id
        WHERE v.voted_at < e.start_date OR v.voted_at > e.end_date
    """).fetchall()
    for row in rows:
        anomalies.append({
            "type": "OUT_OF_WINDOW_VOTE",
            "severity": "CRITICAL",
            "description": f"Vote by '{row['voter_id']}' in '{row['title']}' cast outside the election window.",
            "voter_id": row["voter_id"],
            "voted_at": row["voted_at"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # ── Anomaly 4: High volume voting in short burst (>10 votes/minute) ──
    rows = cur.execute("""
        SELECT strftime('%Y-%m-%d %H:%M', voted_at) as minute_window,
               election_id, COUNT(*) as cnt
        FROM votes
        GROUP BY minute_window, election_id
        HAVING cnt > 5
    """).fetchall()
    for row in rows:
        election = cur.execute("SELECT title FROM elections WHERE election_id=?", (row["election_id"],)).fetchone()
        anomalies.append({
            "type": "VOTE_BURST",
            "severity": "MEDIUM",
            "description": f"{row['cnt']} votes cast in 1 minute for '{election['title'] if election else 'Unknown'}'. Possible bot activity.",
            "window": row["minute_window"],
            "count": row["cnt"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # ── Anomaly 5: Geographic Fencing / Coordinate Spoofing ──
    rows = cur.execute("""
        SELECT v.vote_id, v.voter_id, v.location_lat, v.location_lng, e.title
        FROM votes v
        JOIN elections e ON v.election_id = e.election_id
        WHERE v.location_lat = 0.0 AND v.location_lng = 0.0
    """).fetchall()
    for row in rows:
        anomalies.append({
            "type": "GEOLOCATION_HIDDEN",
            "severity": "MEDIUM",
            "description": f"Voter '{row['voter_id']}' cast a vote with hidden or blocked GPS coordinates.",
            "voter_id": row["voter_id"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return anomalies


# ─────────────────────────────────────────────────────────
# 3. AI RESULT SUMMARIZER
# ─────────────────────────────────────────────────────────

def generate_result_summary(conn, election_id: int) -> str:
    """Generate a plain-English AI summary of election results."""
    cur = conn.cursor()

    election = cur.execute(
        "SELECT * FROM elections WHERE election_id=?", (election_id,)
    ).fetchone()
    if not election:
        return "Election not found."

    results = cur.execute("""
        SELECT r.*, c.name, c.party, c.constituency
        FROM results r
        JOIN candidates c ON r.candidate_id = c.candidate_id
        WHERE r.election_id = ?
        ORDER BY r.total_votes DESC
    """, (election_id,)).fetchall()

    total_votes = cur.execute(
        "SELECT COUNT(*) FROM votes WHERE election_id=?", (election_id,)
    ).fetchone()[0]

    total_voters = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    if not results or total_votes == 0:
        return f"The election **'{election['title']}'** has concluded, but no votes were recorded."

    winner = results[0]
    runner_up = results[1] if len(results) > 1 else None
    turnout_pct = round((total_votes / max(total_voters, 1)) * 100, 1)

    # Determine win margin
    margin = winner["total_votes"] - (runner_up["total_votes"] if runner_up else 0)
    margin_pct = round(winner["percentage"] - (runner_up["percentage"] if runner_up else 0), 1)

    # Win type
    if winner["percentage"] >= 60:
        win_type = "a landslide victory"
    elif winner["percentage"] >= 50:
        win_type = "a decisive win"
    elif margin <= 5:
        win_type = "an extremely close contest"
    else:
        win_type = "a clear victory"

    # Turnout description
    if turnout_pct >= 70:
        turnout_desc = "an exceptionally high voter turnout"
    elif turnout_pct >= 50:
        turnout_desc = "a strong voter turnout"
    elif turnout_pct >= 30:
        turnout_desc = "a moderate voter turnout"
    else:
        turnout_desc = "a low voter turnout"

    summary = (
        f"📋 **AI Election Summary — {election['title']}**\n\n"
        f"The election has concluded with {turnout_desc} of **{turnout_pct}%** "
        f"({total_votes} votes cast).\n\n"
        f"🏆 **{winner['name']}** of the **{winner['party']}** secured {win_type} "
        f"with **{winner['total_votes']} votes ({winner['percentage']}%)**."
    )

    if runner_up:
        summary += (
            f" The runner-up, **{runner_up['name']}** ({runner_up['party']}), "
            f"received {runner_up['total_votes']} votes ({runner_up['percentage']}%), "
            f"trailing by a margin of {margin_pct} percentage points."
        )

    if len(results) > 2:
        others = results[2:]
        other_names = ", ".join([f"{r['name']} ({r['party']}, {r['total_votes']} votes)" for r in others])
        summary += f"\n\nOther candidates: {other_names}."

    summary += (
        f"\n\n📌 This result was determined by {total_votes} verified voters "
        f"in the **{election['constituency']}** constituency."
    )

    return summary


# ─────────────────────────────────────────────────────────
# 4. SMART CANDIDATE SEARCH
# ─────────────────────────────────────────────────────────

def smart_search(conn, query: str, category: str = "all") -> list:
    """Fuzzy search candidates by name, party, or constituency."""
    cur = conn.cursor()
    q = query.lower().strip()

    all_candidates = cur.execute("""
        SELECT c.*, e.title as election_title, e.status as election_status
        FROM candidates c
        JOIN elections e ON c.election_id = e.election_id
    """).fetchall()

    results = []
    for c in all_candidates:
        score = 0
        c_dict = dict(c)

        # Exact match gets higher score
        if q in c_dict["name"].lower():
            score += 10 if q == c_dict["name"].lower() else 5
        if q in c_dict["party"].lower():
            score += 4
        if q in c_dict["constituency"].lower():
            score += 3
        if q in c_dict.get("manifesto", "").lower():
            score += 1

        # Category filter
        if category == "party" and q not in c_dict["party"].lower():
            continue
        if category == "constituency" and q not in c_dict["constituency"].lower():
            continue
        if category == "name" and q not in c_dict["name"].lower():
            continue

        if score > 0:
            c_dict["relevance_score"] = score
            results.append(c_dict)

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results
