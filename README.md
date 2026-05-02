# VoteSecure

> **AI-Based Digital Voting and Election Result Management System**  
> DBMS Capstone Project

---

## 🚀 Features

- 🗳️ **Secure Voter Registration** with age verification (18+)
- 🔐 **Hashed Passwords** (SHA-256 + salt)
- 🏛️ **Admin Panel** with role-based access (Super Admin / Election Officer)
- 📊 **Real-time Results** with bar & pie charts (Chart.js)
- 🤖 **AI Chatbot** to guide voters
- 🛡️ **Anomaly Detection** — flags suspicious voting patterns
- 📝 **AI Result Summarizer** — plain-English election summary
- 🔍 **Smart Candidate Search** by name, party, constituency
- 📋 **Full Audit Logs** for every action
- ⬇️ **CSV & PDF Export** of election results
- 🌙 **Dark / Light Mode** toggle

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Database | SQLite (7 tables, FK constraints, indexes) |
| Backend | Python (built-in `http.server`, `sqlite3`) |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Charts | Chart.js (CDN) |
| Password Hashing | `hashlib` SHA-256 + salt |

---

## ▶️ How to Run

**Requirements:** Python 3.x (no pip installs needed!)

```bash
python app.py
```

Open your browser at: **http://localhost:8000**

---

## 🔑 Default Credentials

| Role | Email | Password |
|---|---|---|
| Super Admin | admin@votesecure.com | Admin@123 |
| Election Officer | officer@votesecure.com | Officer@123 |
| Demo Voter | aditya@example.com | Test@123 |

---

## 📁 Project Structure

```
├── app.py           # Python backend server + all API routes
├── database.py      # SQLite schema (7 tables) + seed data
├── ai_engine.py     # AI chatbot, anomaly detection, result summarizer
├── votesecure.db    # SQLite database (auto-created on first run)
└── public/
    ├── index.html   # Landing + Auth page
    ├── voter.html   # Voter dashboard (SPA)
    ├── admin.html   # Admin panel (SPA)
    ├── style.css    # Design system
    ├── voter.js     # Voter logic
    └── admin.js     # Admin logic
```

---

## 🗄️ Database Schema

7 tables: `users`, `admins`, `elections`, `candidates`, `votes`, `results`, `audit_logs`

- `UNIQUE(voter_id, election_id)` on votes — enforces one vote per election at DB level
- Foreign key constraints with `ON DELETE CASCADE`
- Indexed for performance

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Register voter |
| POST | `/api/auth/voter/login` | Voter login |
| POST | `/api/auth/admin/login` | Admin login |
| GET | `/api/elections/active` | Active elections for voter |
| POST | `/api/vote` | Cast vote |
| GET | `/api/results/:id` | Live results |
| POST | `/api/admin/elections` | Create election |
| PUT | `/api/admin/elections/:id` | Update election |
| DELETE | `/api/admin/elections/:id` | Delete election |
| POST | `/api/admin/candidates` | Add candidate |
| DELETE | `/api/admin/candidates/:id` | Remove candidate |
| GET | `/api/admin/turnout` | Voter turnout stats |
| GET | `/api/admin/audit` | Audit logs |
| GET | `/api/admin/export/csv/:id` | Export CSV |
| GET | `/api/admin/export/pdf/:id` | Export PDF |
| POST | `/api/ai/chat` | AI chatbot |
| GET | `/api/ai/anomalies` | Anomaly detection |
| GET | `/api/ai/summarize/:id` | AI result summary |
| GET | `/api/ai/search` | Smart candidate search |
