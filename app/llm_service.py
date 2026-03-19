"""
Text-to-SQL LLM service using OpenAI GPT-4o-mini.

Three-step pipeline:
  1. Schema + question  →  GPT  →  SQL query
  2. SQL query  →  execute against DB  →  raw results
  3. Question + results  →  GPT  →  plain-English answer
"""
import os
import re
from dotenv import load_dotenv
from openai import OpenAI

from app.database import get_schema_string, run_sql

load_dotenv()

MODEL = "gpt-4o-mini"
_client = None


def _get_client() -> OpenAI:
    """Lazy-initialize the OpenAI client so the server can start without an API key."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )
        _client = OpenAI(api_key=api_key)
    return _client

SYSTEM_PROMPT_SQL = (
    "You are a SQL expert. Given a database schema and a natural language "
    "question, generate a SQLite SQL query that answers the question. "
    "Return ONLY the SQL query, nothing else. No markdown, no explanation, "
    "no code fences.\n\n"
    "Only return OUT_OF_SCOPE for questions that are completely "
    "unrelated to a university — like geography, politics, sports, "
    "weather, or personal questions.\n\n"
    "NEVER return OUT_OF_SCOPE for questions about:\n"
    "- Students, professors, subjects, divisions\n"
    "- Enrollment, popularity, counts, rankings\n"
    "- Anything that could be answered from the university database\n"
    "- Even if phrased informally\n\n"
    "OUT_OF_SCOPE examples (very limited):\n"
    "- capital of India\n"
    "- who is Modi\n"
    "- what is 2+2\n"
    "- sports scores\n\n"
    "IMPORTANT RULES for generating SQL:\n"
    "1. For ANY name search (student, professor, subject), ALWAYS use LIKE with wildcards. "
    "Example: WHERE s.name LIKE '%Mihir%'. Never use exact = match for names.\n\n"
    "2. Subject name aliases - map these automatically:\n"
    "   maths/math -> Mathematics\n"
    "   CS/comp sci -> Computer Science\n"
    "   bio -> Biology\n"
    "   chem -> Chemistry\n"
    "   eco/econ -> Economics\n"
    "   physics/phy -> Physics\n"
    "   english/eng -> English\n"
    "   history/hist -> History\n"
    "   Use LIKE '%Mathematics%' and never exact match for subject names.\n\n"
    "3. If a name search might match multiple people, select all matches and include full names in results "
    "so the user can see who was found.\n\n"
    "4. IMPORTANT: The divisions table has 60 rows (4 letters × 15 subjects).\n"
    "When asked about division student counts, ALWAYS group by \n"
    "division letter name, not by division ID.\n\n"
    "Correct query for division student counts:\n"
    "SELECT d.name as division, COUNT(DISTINCT s.id) as student_count\n"
    "FROM students s\n"
    "JOIN divisions d ON s.division_id = d.id\n"
    "GROUP BY d.name\n"
    "ORDER BY student_count DESC\n\n"
    "NEVER do: GROUP BY d.id — this gives per-subject counts not \n"
    "per-division counts.\n\n"
    "5. When conversation history references multiple people or items\n"
    "and the follow-up question uses 'they', 'their', 'it', 'those' etc:\n"
    "- If the previous answer had ONE result, resolve the pronoun to that result\n"
    "- If the previous answer had MULTIPLE results, return ALL of them\n"
    "- Never return empty results for pronoun-based follow-up questions\n"
    "  when the context clearly establishes what the pronoun refers to\n\n"
    "CRITICAL DATABASE FACTS — never contradict these:\n"
    "- divisions table ONLY has 4 division letters: A, B, C, D\n"
    "- There are NO divisions E, F, G, H or any other letters\n"
    "- Total divisions = 60 rows (15 subjects × 4 division letters)\n"
    "- Never mention or reference divisions that don't exist\n"
    "- If your SQL returns division names other than A/B/C/D, \n"
    "  your query is wrong — fix it\n\n"
    "When answering questions about WHO teaches something, ALWAYS \n"
    "include the division in your SELECT:\n\n"
    "SELECT p.name as professor, d.name as division\n"
    "FROM professors p\n"
    "JOIN divisions d ON p.id = d.professor_id  \n"
    "JOIN subjects s ON d.subject_id = s.id\n"
    "WHERE s.name LIKE '%subject%'\n"
    "ORDER BY p.name, d.name\n\n"
    "NEVER select only professor names when division context is needed.\n"
    "Always include all columns needed to give a complete answer.\n"
    "If the question asks who teaches something, include division.\n"
    "If the question asks what someone teaches, include subject name.\n"
    "If the question asks about students, include their name and enrollment.\n\n"
    "When answering questions about grades or marks, ALWAYS include \n"
    "the subject name alongside the grade:\n\n"
    "SELECT sub.name as subject, ss.grade\n"
    "FROM students s\n"
    "JOIN student_subjects ss ON s.id = ss.student_id\n"
    "JOIN subjects sub ON ss.subject_id = sub.id\n"
    "WHERE s.name LIKE '%Mihir%'\n"
    "ORDER BY sub.name\n\n"
    "Never return just grades without subject context."
)

SYSTEM_PROMPT_ANSWER = (
    "You are a helpful assistant. Convert the given SQL query results into "
    "a clear, concise natural language answer for the user's question. "
    "Be friendly and precise. "
    "When listing professors for a subject, always mention which divisions they teach. "
    "Example: 'Dr. Ananya Sharma teaches Computer Science in divisions A and B. "
    "Dr. Rajesh Kulkarni teaches it in divisions C and D.' "
    "Never just list names without division context for subject queries.\n\n"
    "CRITICAL: Base your answer ONLY on the SQL results provided.\n"
    "NEVER add information not present in the results.\n"
    "If division is not in the results, do not mention division.\n"
    "If a value is not in the raw results, do not include it in your answer.\n\n"
    "If a grade is NULL in the SQL results, show it as 'Not graded yet' in your answer."
)


def _seems_single_person_question(question: str) -> bool:
    """Heuristic: detect prompts likely targeting one person, not a list."""
    q = question.lower()
    single_patterns = [
        r"\bwhich division is\b",
        r"\bwho is\b",
        r"\bfor\s+[a-z]+\s+[a-z]+\b",
        r"\bof\s+[a-z]+\s+[a-z]+\b",
    ]
    plural_markers = [
        "students",
        "professors",
        "subjects",
        "list all",
        "show all",
        "all ",
    ]
    if any(marker in q for marker in plural_markers):
        return False
    return any(re.search(pattern, q) for pattern in single_patterns)


def answer_question(question: str, history: list = []) -> dict:
    """
    End-to-end text-to-SQL pipeline.

    Returns:
        dict with keys: question, sql, results, answer
    """
    # ── Step 1: Generate SQL from schema + question ───────────────────
    schema = get_schema_string()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_SQL},
    ]

    # Add conversation history for context
    for msg in history[-6:]:
        if msg["role"] == "user":
            messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            messages.append({"role": "assistant", "content": msg["content"]})

    # Add current question
    messages.append({
        "role": "user",
        "content": (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}"
        ),
    })

    sql_response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=messages,
    )
    sql_query = sql_response.choices[0].message.content.strip()

    # Clean up any accidental markdown fencing
    if sql_query.startswith("```"):
        sql_query = sql_query.strip("`").removeprefix("sql").strip()

    if sql_query.strip() == "OUT_OF_SCOPE":
        return {
            "question": question,
            "sql": None,
            "results": None,
            "answer": "I can only answer questions about the university — students, professors, subjects, and divisions.",
        }

    # ── Step 2: Execute the SQL against the database ──────────────────
    try:
        results = run_sql(sql_query)
    except Exception as e:
        return {
            "question": question,
            "sql": sql_query,
            "results": [],
            "answer": f"Sorry, the generated SQL caused an error: {e}",
        }

    # ── Step 3: Convert results to natural language answer ────────────
    result_context = ""
    if len(results) > 5 and _seems_single_person_question(question):
        result_context = "\nNote: multiple people matched this name."

    answer_response = _get_client().chat.completions.create(
        model=MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_ANSWER},
            {
                "role": "user",
                "content": (
                    f"User's question: {question}\n\n"
                    f"Additional context: {result_context or 'None'}\n\n"
                    f"SQL query used:\n{sql_query}\n\n"
                    f"Query results:\n{results}"
                ),
            },
        ],
    )
    answer = answer_response.choices[0].message.content.strip()

    return {
        "question": question,
        "sql": sql_query,
        "results": results,
        "answer": answer,
    }
