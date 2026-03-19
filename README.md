# 🎓 University Agent — Text-to-SQL AI

> Ask questions about a university database in plain English.
> Powered by GPT-4o-mini with conversation memory.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![OpenAI](https://img.shields.io/badge/GPT--4o--mini-412991?logo=openai&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 💬 Natural Language Queries | Ask anything about students, professors, subjects, divisions |
| 🧠 Conversation Memory | Follow-up questions work — "what is their email?" understands context |
| 🔍 Fuzzy Matching | "maths" finds Mathematics, "CS" finds Computer Science |
| 🛡️ Security | Blocks DROP TABLE, DELETE, UPDATE and out-of-scope questions |
| 🗄️ Database Explorer | Browse all 5 tables with search, filter, and CSV export |
| ➕ Manage Data | Add/update students, professors, subjects, divisions |
| 🎓 Smart Enrollment | 3-step student enrollment with subject selection and review |
| 📊 Division View | Click any division to see subjects, professors, and students |

---

## 🏗️ Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────┐     OpenAI
│   Streamlit UI  │ ◄──────────► │   FastAPI Server  │ ◄──────────► GPT-4o-mini
│   (Port 8501)   │              │   (Port 8000)     │
└─────────────────┘              └────────┬─────────┘
                                          │
                                   ┌──────┴──────┐
                                   │   SQLite    │
                                   │ university  │
                                   │    .db      │
                                   └─────────────┘
```

---

## 📁 Project Structure

```
text-to-sql-agent/
├── app/
│   ├── database.py        # DB engine, sessions, schema introspection
│   ├── models.py          # SQLAlchemy models (5 tables)
│   └── llm_service.py     # 3-step GPT-4o-mini pipeline
├── api/
│   └── main.py            # FastAPI — 10+ endpoints
├── ui/
│   └── streamlit_app.py   # 3-page Streamlit UI
├── scripts/
│   └── seed.py            # Seeds 12 profs, 15 subjects, 100 students
├── data/                  # university.db created here at runtime
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🗄️ Database Schema

```
professors (12 rows)     subjects (15 rows)
├── id                   ├── id
├── name                 ├── name
├── email                ├── subject_code
└── department           └── credits

divisions (60 rows)      students (100 rows)
├── id                   ├── id
├── name (A/B/C/D)       ├── name
├── subject_id (FK)      ├── email
└── professor_id (FK)    ├── enrollment_number
                         └── division_id (FK)

student_subjects (605 rows)
├── student_id (FK)
├── subject_id (FK)
├── division_id (FK)
├── enrollment_date
└── grade
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- OpenAI API key

### Setup

```bash
# 1. Clone
git clone https://github.com/Mihir1107/text-to-sql-agent
cd text-to-sql-agent

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add OpenAI key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 5. Seed the database
python3 scripts/seed.py

# 6. Start backend (Terminal 1)
python3 -m uvicorn api.main:app --reload

# 7. Start frontend (Terminal 2)
python3 -m streamlit run ui/streamlit_app.py

> **Note**: Always use the `python3 -m` prefix to ensure the dependencies from your virtual environment are correctly loaded.
```

Open **http://localhost:8501**

---

## 💬 Example Questions

```
Basic:
"Who is teaching Mathematics?"
"Which division is Mihir in?"
"List all professors"

Complex:
"Which professor teaches the most subjects?"
"List students in Division A who study Machine Learning"
"How many students study both Physics and Mathematics?"

Follow-ups (conversation memory):
"Which professor teaches the most subjects?"
→ "List all their subjects"
→ "How many students do they teach?"
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /ask | Natural language → SQL → answer |
| GET | /schema | Database schema |
| GET | /health | Health check |
| GET | /documents | List all students |
| POST | /students | Add new student |
| PUT | /students/{id} | Update student |
| POST | /professors | Add professor |
| POST | /subjects | Add subject |
| POST | /divisions | Add division |
| GET | /students/next-enrollment | Next ENR number |

---

## 🛡️ Security

- Blocks all destructive SQL: DROP, DELETE, UPDATE, INSERT via agent
- Refuses out-of-scope questions (geography, politics, general knowledge)
- Input validation on all form fields
- Foreign key enforcement enabled
- Unique constraints on email and enrollment numbers

---

Built for an AI agents internship — demonstrates LLM pipeline 
integration with Text-to-SQL, conversation memory, and a 
production-style REST API.
