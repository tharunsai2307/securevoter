"""
VoteSecure - Database Initialization
SQLite schema creation and seed data
"""

import sqlite3
import hashlib
import os
import secrets
import json
import re
from datetime import datetime, timedelta

try:
    from config import DATABASE_URL, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD
except ImportError:
    DATABASE_URL = ""
    DEFAULT_ADMIN_EMAIL = "admin@votesecure.com"
    DEFAULT_ADMIN_PASSWORD = "Admin@123"

DB_PATH = os.path.join(os.path.dirname(__file__), "votesecure.db")

try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

class PostgresWrapper:
    def __init__(self, conn):
        self.conn = conn
        self._last_cur = None
        self._last_id = None

    def execute(self, sql, params=()):
        pg_sql = sql.replace('?', '%s')
        pg_sql = pg_sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        pg_sql = pg_sql.replace('INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY')
        pg_sql = pg_sql.replace('DATETIME', 'TIMESTAMP')
        pg_sql = pg_sql.replace('REAL', 'NUMERIC')
        
        # SQLite: datetime('now') -> PG: CURRENT_TIMESTAMP
        # SQLite: datetime('now', '-1 hour') -> PG: CURRENT_TIMESTAMP - INTERVAL '1 hour'
        if "datetime('now')" in pg_sql:
            pg_sql = pg_sql.replace("datetime('now')", 'CURRENT_TIMESTAMP')
        
        # Handle offsets like datetime('now', '-1 hour')
        import re
        offsets = re.findall(r"datetime\('now',\s*'([^']+)'\)", pg_sql)
        for offset in offsets:
            pg_sql = pg_sql.replace(f"datetime('now', '{offset}')", f"CURRENT_TIMESTAMP + INTERVAL '{offset}'")

        # SQLite: strftime('%H:00', voted_at) -> PG: to_char(voted_at, 'HH24:00')
        # SQLite: strftime('%Y-%m-%d %H:%M', voted_at) -> PG: to_char(voted_at, 'YYYY-MM-DD HH24:MI')
        strftime_matches = re.findall(r"strftime\('([^']+)',\s*([^)]+)\)", pg_sql)
        for fmt, col in strftime_matches:
            pg_fmt = fmt.replace('%Y', 'YYYY').replace('%m', 'MM').replace('%d', 'DD').replace('%H', 'HH24').replace('%M', 'MI').replace('%S', 'SS')
            pg_sql = pg_sql.replace(f"strftime('{fmt}', {col})", f"to_char({col}, '{pg_fmt}')")

        pg_sql = pg_sql.replace("TEXT DEFAULT (CURRENT_TIMESTAMP)", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        
        is_insert = pg_sql.strip().upper().startswith("INSERT")
        
        if "INSERT OR IGNORE INTO" in pg_sql:
            pg_sql = pg_sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            pg_sql += " ON CONFLICT DO NOTHING"
            
        if is_insert and "RETURNING" not in pg_sql.upper():
            table_match = re.search(r'INTO\s+([a-zA-Z0-9_]+)', pg_sql, re.IGNORECASE)
            if table_match:
                table = table_match.group(1).lower()
                if table == "elections": pg_sql += " RETURNING election_id"
                elif table == "candidates": pg_sql += " RETURNING candidate_id"
                elif table == "announcements": pg_sql += " RETURNING ann_id"
                elif table == "audit_logs": pg_sql += " RETURNING id"

        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        self._last_cur = cur
        cur.execute(pg_sql, params)
        
        # Cache ID if we have RETURNING
        if is_insert and "RETURNING" in pg_sql.upper():
            try:
                row = cur.fetchone()
                if row: self._last_id = row[0]
            except: pass
            
        return self

    def executescript(self, sql):
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for stmt in statements:
            self.execute(stmt)

    def fetchone(self):
        return self._last_cur.fetchone()

    def fetchall(self):
        return self._last_cur.fetchall()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def cursor(self):
        return self

        return None

    @property
    def lastrowid(self):
        if self._last_id is not None:
            return self._last_id
        return None

    @property
    def is_postgres(self):
        return True

_POOL = None

def get_connection():
    global _POOL
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        if not HAS_POSTGRES:
            print("⚠️ psycopg2-binary not installed. Falling back to SQLite...")
        else:
            try:
                if _POOL is None:
                    from psycopg2.pool import ThreadedConnectionPool
                    # Min 5, Max 20 connections for high performance
                    _POOL = ThreadedConnectionPool(5, 20, DATABASE_URL)
                
                conn = _POOL.getconn()
                return PooledPostgresWrapper(conn, _POOL)
            except Exception as e:
                print(f"⚠️ Cloud Database Connection Failed: {e}")
                print("⚠️ Falling back to local SQLite database...")

    # Fallback to SQLite
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

class PooledPostgresWrapper(PostgresWrapper):
    def __init__(self, conn, pool):
        super().__init__(conn)
        self.pool = pool
    def close(self):
        try: self.pool.putconn(self.conn)
        except: self.conn.close()


def hash_password(password: str):
    salt = secrets.token_hex(32)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


def generate_voter_id():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return f"VTR-{datetime.now().year}-{str(count + 1).zfill(4)}"


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ─── TABLES ───────────────────────────────────────────
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            voter_id       TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            email          TEXT UNIQUE NOT NULL,
            phone          TEXT,
            password_hash  TEXT NOT NULL,
            password_salt  TEXT NOT NULL,
            dob            TEXT NOT NULL,
            gender         TEXT,
            constituency   TEXT NOT NULL,
            aadhaar_id     TEXT,
            govt_voter_id  TEXT,
            is_verified    INTEGER DEFAULT 1,
            phone_verified INTEGER DEFAULT 0,
            voted_elections TEXT DEFAULT '[]',
            hardware_fingerprint TEXT,
            created_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS admins (
            admin_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT NOT NULL,
            password_salt  TEXT NOT NULL,
            role           TEXT DEFAULT 'election_officer'
        );

        CREATE TABLE IF NOT EXISTS elections (
            election_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            constituency TEXT DEFAULT 'All',
            start_date   TEXT NOT NULL,
            end_date     TEXT NOT NULL,
            status       TEXT DEFAULT 'upcoming'
        );

        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id   INTEGER NOT NULL,
            name          TEXT NOT NULL,
            party         TEXT NOT NULL,
            photo_url     TEXT DEFAULT '',
            manifesto     TEXT DEFAULT '',
            constituency  TEXT NOT NULL,
            FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS votes (
            vote_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_id     TEXT NOT NULL,
            candidate_id INTEGER NOT NULL,
            election_id  INTEGER NOT NULL,
            voted_at     TEXT DEFAULT (datetime('now')),
            ip_address   TEXT,
            previous_hash TEXT DEFAULT 'GENESIS',
            current_hash  TEXT DEFAULT '',
            location_lat  REAL DEFAULT 0.0,
            location_lng  REAL DEFAULT 0.0,
            UNIQUE(voter_id, election_id),
            FOREIGN KEY (voter_id) REFERENCES users(voter_id),
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id),
            FOREIGN KEY (election_id) REFERENCES elections(election_id)
        );

        CREATE TABLE IF NOT EXISTS results (
            result_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id  INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            total_votes  INTEGER DEFAULT 0,
            percentage   REAL DEFAULT 0.0,
            FOREIGN KEY (election_id) REFERENCES elections(election_id),
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT,
            action     TEXT NOT NULL,
            details    TEXT,
            timestamp  TEXT DEFAULT (datetime('now')),
            ip_address TEXT
        );

        CREATE TABLE IF NOT EXISTS announcements (
            ann_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   TEXT NOT NULL,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            priority   TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS security_bypass (
            key TEXT PRIMARY KEY
        );

        /* 🔒 ELITE SECURITY: WORM TRIGGERS (Anti-Tampering with Admin Bypass) */
        CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete BEFORE DELETE ON audit_logs
        WHEN (SELECT COUNT(*) FROM security_bypass WHERE key='ADMIN_CLEANUP') = 0
        BEGIN SELECT RAISE(FAIL, 'Audit logs are immutable and cannot be deleted.'); END;

        CREATE TRIGGER IF NOT EXISTS audit_logs_no_update BEFORE UPDATE ON audit_logs
        BEGIN SELECT RAISE(FAIL, 'Audit logs are immutable and cannot be updated.'); END;

        CREATE TRIGGER IF NOT EXISTS votes_no_delete BEFORE DELETE ON votes
        WHEN (SELECT COUNT(*) FROM security_bypass WHERE key='ADMIN_CLEANUP') = 0
        BEGIN SELECT RAISE(FAIL, 'Votes are immutable and cannot be deleted.'); END;

        CREATE TRIGGER IF NOT EXISTS elections_no_delete BEFORE DELETE ON elections
        WHEN (SELECT COUNT(*) FROM security_bypass WHERE key='ADMIN_CLEANUP') = 0
        BEGIN SELECT RAISE(FAIL, 'Elections are protected. Use Archive or Admin Cleanup.'); END;

        /* ⚡ HYPER-SPEED INDEXES (Optimized for 100k Users) */
        CREATE INDEX IF NOT EXISTS idx_votes_election ON votes(election_id);
        CREATE INDEX IF NOT EXISTS idx_votes_voter ON votes(voter_id);
        CREATE INDEX IF NOT EXISTS idx_candidates_election ON candidates(election_id);
        CREATE INDEX IF NOT EXISTS idx_announcements_created ON announcements(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC);

        CREATE TABLE IF NOT EXISTS otp_codes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            phone      TEXT,
            code       TEXT NOT NULL,
            otp_type   TEXT DEFAULT 'email',
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_votes_election ON votes(election_id);
        CREATE INDEX IF NOT EXISTS idx_votes_voter ON votes(voter_id);
        CREATE INDEX IF NOT EXISTS idx_candidates_election ON candidates(election_id);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
    """)
    conn.commit()

    # ─── MIGRATIONS (For existing databases) ──────────────
    migrations = [
        "ALTER TABLE votes ADD COLUMN previous_hash TEXT DEFAULT 'GENESIS'",
        "ALTER TABLE votes ADD COLUMN current_hash TEXT DEFAULT ''",
        "ALTER TABLE votes ADD COLUMN location_lat REAL DEFAULT 0.0",
        "ALTER TABLE votes ADD COLUMN location_lng REAL DEFAULT 0.0"
    ]
    for mig in migrations:
        try:
            conn.execute(mig)
            conn.commit()
        except Exception:
            if hasattr(conn, 'conn'):
                conn.conn.rollback() # Postgres rollback
            pass

    # ─── SEED DATA ────────────────────────────────────────
    # Check if already seeded
    admin_count = cur.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if admin_count > 0:
        conn.close()
        return

    print("  Seeding database with initial data...")

    # Admins
    sa_hash, sa_salt = hash_password("Admin@123")
    eo_hash, eo_salt = hash_password("Officer@123")

    cur.execute("INSERT INTO admins (name, email, password_hash, password_salt, role) VALUES (?,?,?,?,?)",
                ("Super Admin", "admin@votesecure.com", sa_hash, sa_salt, "super_admin"))
    cur.execute("INSERT INTO admins (name, email, password_hash, password_salt, role) VALUES (?,?,?,?,?)",
                ("Raj Kumar", "officer@votesecure.com", eo_hash, eo_salt, "election_officer"))

    # Elections
    now = datetime.now()
    elections = [
        ("General Assembly Election 2024", "Election for the General Assembly seats across all constituencies.",
         "All", (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
         (now + timedelta(days=2)).strftime("%Y-%m-%d %H:%M"), "active"),

        ("North District Municipal Poll", "Municipal Corporation election for North District.",
         "North District", (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M"),
         (now + timedelta(days=6)).strftime("%Y-%m-%d %H:%M"), "upcoming"),

        ("South Constituency By-Election", "By-election for vacant South Constituency seat.",
         "South Constituency", (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M"),
         (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M"), "ended"),
    ]
    for e in elections:
        cur.execute("INSERT INTO elections (title, description, constituency, start_date, end_date, status) VALUES (?,?,?,?,?,?)", e)

    # Candidates
    candidates = [
        # Election 1 - General Assembly (active)
        (1, "Priya Sharma", "National Progressive Party", "", "Focus on education reform and digital infrastructure.", "All"),
        (1, "Vikram Singh", "United Democratic Front", "", "Rural development and farmer welfare programs.", "All"),
        (1, "Anjali Mehta", "Green Future Alliance", "", "Environmental sustainability and clean energy.", "All"),
        (1, "Suresh Patel", "People's Voice Party", "", "Anti-corruption and transparency in governance.", "All"),

        # Election 2 - North District (upcoming)
        (2, "Arjun Reddy", "National Progressive Party", "", "Infrastructure and road development.", "North District"),
        (2, "Meena Joshi", "United Democratic Front", "", "Women empowerment and child welfare.", "North District"),
        (2, "Rahul Verma", "Independent", "", "Local development and community welfare.", "North District"),

        # Election 3 - South Constituency (ended)
        (3, "Deepa Nair", "National Progressive Party", "", "Healthcare and education priority.", "South Constituency"),
        (3, "Mohan Lal", "United Democratic Front", "", "Business and trade development.", "South Constituency"),
        (3, "Kavitha Rao", "Green Future Alliance", "", "Women's rights and environment.", "South Constituency"),
    ]
    for c in candidates:
        cur.execute("INSERT INTO candidates (election_id, name, party, photo_url, manifesto, constituency) VALUES (?,?,?,?,?,?)", c)

    # Voters
    voters = [
        ("VTR-2024-0001", "Aditya Kumar", "aditya@example.com", "Test@123", "1995-03-15", "Male", "All"),
        ("VTR-2024-0002", "Sneha Gupta", "sneha@example.com", "Test@123", "1990-07-22", "Female", "North District"),
        ("VTR-2024-0003", "Rohan Das", "rohan@example.com", "Test@123", "1988-11-05", "Male", "South Constituency"),
    ]
    for v in voters:
        vh, vs = hash_password(v[3])
        cur.execute(
            "INSERT INTO users (voter_id, name, email, password_hash, password_salt, dob, gender, constituency, is_verified) VALUES (?,?,?,?,?,?,?,?,1)",
            (v[0], v[1], v[2], vh, vs, v[4], v[5], v[6])
        )

    # Seed some votes for the ended election (election 3)
    votes_seed = [
        ("VTR-2024-0003", 8, 3, "192.168.1.1"),  # Deepa Nair
        ("VTR-2024-0001", 9, 3, "192.168.1.2"),  # Mohan Lal
    ]
    for vt in votes_seed:
        cur.execute("INSERT OR IGNORE INTO votes (voter_id, candidate_id, election_id, ip_address) VALUES (?,?,?,?)", vt)
        # Update voted_elections for user
        user = cur.execute("SELECT voted_elections FROM users WHERE voter_id=?", (vt[0],)).fetchone()
        if user:
            voted = json.loads(user[0] or "[]")
            if str(vt[2]) not in voted:
                voted.append(str(vt[2]))
            cur.execute("UPDATE users SET voted_elections=? WHERE voter_id=?", (json.dumps(voted), vt[0]))

    # Seed some votes for the active election (election 1)
    active_votes = [
        ("VTR-2024-0002", 1, 1, "10.0.0.1"),   # Priya Sharma
    ]
    for vt in active_votes:
        cur.execute("INSERT OR IGNORE INTO votes (voter_id, candidate_id, election_id, ip_address) VALUES (?,?,?,?)", vt)
        user = cur.execute("SELECT voted_elections FROM users WHERE voter_id=?", (vt[0],)).fetchone()
        if user:
            voted = json.loads(user[0] or "[]")
            if str(vt[2]) not in voted:
                voted.append(str(vt[2]))
            cur.execute("UPDATE users SET voted_elections=? WHERE voter_id=?", (json.dumps(voted), vt[0]))

    # Compute results for ended election
    compute_results(cur, 3)

    # Seed announcements
    cur.execute(
        "INSERT INTO announcements (admin_id, title, body, priority) VALUES (?,?,?,?)",
        ("admin@votesecure.com",
         "🗳️ General Assembly Election Now Open!",
         "Voting is now open for the General Assembly Election 2024. All registered voters can cast their vote until the deadline. Make your voice count!",
         "high")
    )
    cur.execute(
        "INSERT INTO announcements (admin_id, title, body, priority) VALUES (?,?,?,?)",
        ("officer@votesecure.com",
         "📋 North District Municipal Poll — Registration Reminder",
         "The North District Municipal Poll starts in 5 days. Ensure your constituency is updated in your profile before voting begins.",
         "normal")
    )

    # Seed audit logs
    logs = [
        ("VTR-2024-0001", "USER_LOGIN", "Voter logged in", "192.168.1.2"),
        ("VTR-2024-0003", "VOTE_CAST", "Vote cast in Election 3", "192.168.1.1"),
        ("admin@votesecure.com", "ELECTION_CREATED", "Created General Assembly Election 2024", "10.0.0.0"),
        ("admin@votesecure.com", "CANDIDATE_ADDED", "Added candidate Priya Sharma", "10.0.0.0"),
    ]
    for lg in logs:
        cur.execute("INSERT INTO audit_logs (user_id, action, details, ip_address) VALUES (?,?,?,?)", lg)

    conn.commit()
    conn.close()
    print("  Database seeded successfully.")


def compute_results(cur, election_id):
    """Compute and store results for an election."""
    cur.execute("DELETE FROM results WHERE election_id=?", (election_id,))
    total = cur.execute("SELECT COUNT(*) FROM votes WHERE election_id=?", (election_id,)).fetchone()[0]
    if total == 0:
        return
    rows = cur.execute(
        "SELECT candidate_id, COUNT(*) as cnt FROM votes WHERE election_id=? GROUP BY candidate_id",
        (election_id,)
    ).fetchall()
    for row in rows:
        pct = round((row["cnt"] / total) * 100, 2)
        cur.execute(
            "INSERT INTO results (election_id, candidate_id, total_votes, percentage) VALUES (?,?,?,?)",
            (election_id, row["candidate_id"], row["cnt"], pct)
        )


if __name__ == "__main__":
    init_db()
    print("Database ready at:", DB_PATH)
