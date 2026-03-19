"""
FastAPI backend for the Text-to-SQL agent.

Endpoints:
  POST /ask     — answer a natural language question
  GET  /schema  — return the database schema
  GET  /health  — health check
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import init_db, get_schema_string, SessionLocal
from app.models import Division, Professor, Student, StudentSubject, Subject
from app.llm_service import answer_question

app = FastAPI(
    title="Text-to-SQL Agent",
    description="Ask questions about a university database in plain English.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()


# ── Request / Response models ────────────────────────────────────────
class QuestionRequest(BaseModel):
    question: str
    history: list = []


class AnswerResponse(BaseModel):
    question: str
    sql: str | None
    results: list | None
    answer: str


class StudentCreateRequest(BaseModel):
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    enrollment_number: str
    division_id: int


class ProfessorCreateRequest(BaseModel):
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    department: str


class SubjectCreateRequest(BaseModel):
    name: str
    subject_code: str
    credits: int


class DivisionCreateRequest(BaseModel):
    name: str
    subject_id: int
    professor_id: int


class StudentUpdateRequest(BaseModel):
    name: str
    email: str
    division_id: int
    subject_ids: list[int]


class ProfessorUpdateRequest(BaseModel):
    name: str
    email: str
    department: str


class SubjectUpdateRequest(BaseModel):
    name: str
    subject_code: str
    credits: int


class DivisionUpdateRequest(BaseModel):
    professor_id: int


def _normalize_name_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _split_full_name(name: str) -> tuple[str, str]:
    parts = [p for p in name.split() if p]
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[-1]


def _build_unique_email(db: Session, model, first_name: str, last_name: str, domain: str) -> str:
    first_slug = _normalize_name_part(first_name)
    last_slug = _normalize_name_part(last_name)
    if not first_slug or not last_slug:
        raise HTTPException(status_code=400, detail="First name and last name are required")

    base_local = f"{first_slug}.{last_slug}"
    pattern = re.compile(rf"^{re.escape(base_local)}(\d*)@{re.escape(domain)}$", re.IGNORECASE)

    existing_rows = (
        db.query(model.email)
        .filter(model.email.like(f"{base_local}%@{domain}"))
        .all()
    )

    used_suffixes: set[int] = set()
    for row in existing_rows:
        email_value = (row[0] or "").lower()
        match = pattern.match(email_value)
        if not match:
            continue
        suffix_text = match.group(1)
        used_suffixes.add(int(suffix_text) if suffix_text else 0)

    next_suffix = 0
    while next_suffix in used_suffixes:
        next_suffix += 1

    local_part = f"{base_local}{next_suffix if next_suffix > 0 else ''}"
    return f"{local_part}@{domain}"


# ── Endpoints ─────────────────────────────────────────────────────────
@app.post("/ask", response_model=AnswerResponse)
def ask(request: QuestionRequest):
    """Accept a natural language question and return the AI-generated answer."""
    return answer_question(request.question, request.history)


@app.get("/schema")
def schema():
    """Return the current database schema (useful for debugging)."""
    return {"schema": get_schema_string()}


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/students/divisions")
def get_divisions():
    """Return all divisions for student creation UI."""
    db: Session = SessionLocal()
    try:
        divisions = db.query(Division).order_by(Division.name.asc(), Division.id.asc()).all()
        return {
            "divisions": [
                {"id": division.id, "name": division.name}
                for division in divisions
            ]
        }
    finally:
        db.close()


@app.get("/students/next-enrollment")
def get_next_enrollment():
    """Return the next enrollment number in ENR### format."""
    db: Session = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT COALESCE(MAX(CAST(SUBSTR(enrollment_number, 4) AS INTEGER)), 0)
                FROM students
                """
            )
        ).first()
        max_number = int(row[0]) if row and row[0] is not None else 0
        next_number = max_number + 1
        return {"next_enrollment": f"ENR{next_number:03d}"}
    finally:
        db.close()


@app.get("/students/check-email")
def check_email(email: str):
    """Check if an email exists and return a suggestion if it does."""
    db: Session = SessionLocal()
    try:
        exists = db.query(Student).filter(Student.email == email).first() is not None
        if not exists:
            return {"available": True, "suggested": email}
        
        prefix, domain = email.split("@")
        base = prefix.rstrip('0123456789')
        counter = 2
        suggestion = f"{base}{counter}@{domain}"
        while db.query(Student).filter(Student.email == suggestion).first():
            counter += 1
            suggestion = f"{base}{counter}@{domain}"
            
        return {"available": False, "suggested": suggestion}
    finally:
        db.close()

@app.post("/students")
def create_student(request: StudentCreateRequest):
    """Insert a new student record."""
    db: Session = SessionLocal()
    try:
        first_name = (request.first_name or "").strip()
        last_name = (request.last_name or "").strip()
        full_name = (request.name or "").strip()
        if first_name and last_name:
            full_name = f"{first_name} {last_name}".strip()
        elif full_name:
            inferred_first, inferred_last = _split_full_name(full_name)
            first_name = first_name or inferred_first
            last_name = last_name or inferred_last

        if not full_name or not first_name or not last_name:
            raise HTTPException(status_code=400, detail="Please provide first name and last name")

        if (
            not request.enrollment_number.strip()
            or not request.division_id
        ):
            raise HTTPException(status_code=400, detail="Please fill in all required fields")

        division = db.query(Division).filter(Division.id == request.division_id).first()
        if not division:
            raise HTTPException(status_code=400, detail="Invalid division_id")

        email_value = (request.email or "").strip().lower()
        if not email_value:
            email_value = _build_unique_email(db, Student, first_name, last_name, "student.university.edu")

        email_exists = (
            db.query(Student)
            .filter(Student.email == email_value)
            .first()
        )
        if email_exists:
            raise HTTPException(status_code=409, detail="An account with this email already exists")

        enrollment_exists = (
            db.query(Student)
            .filter(Student.enrollment_number == request.enrollment_number.strip())
            .first()
        )
        if enrollment_exists:
            raise HTTPException(status_code=409, detail="Enrollment number already exists")

        student = Student(
            name=full_name,
            email=email_value,
            enrollment_number=request.enrollment_number.strip(),
            division_id=request.division_id,
        )
        db.add(student)
        db.commit()
        db.refresh(student)
        return {
            "success": True,
            "student_id": student.id,
            "email": student.email,
            "message": "Student added successfully",
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )
    finally:
        db.close()


@app.post("/professors")
def create_professor(request: ProfessorCreateRequest):
    """Insert a new professor record."""
    db: Session = SessionLocal()
    try:
        first_name = (request.first_name or "").strip()
        last_name = (request.last_name or "").strip()
        full_name = (request.name or "").strip()
        if first_name and last_name:
            full_name = f"{first_name} {last_name}".strip()
        elif full_name:
            inferred_first, inferred_last = _split_full_name(full_name)
            first_name = first_name or inferred_first
            last_name = last_name or inferred_last

        if not full_name or not first_name or not last_name:
            raise HTTPException(status_code=400, detail="Please provide first name and last name")

        if not request.department.strip():
            raise HTTPException(status_code=400, detail="Department is required")

        email_value = (request.email or "").strip().lower()
        if not email_value:
            email_value = _build_unique_email(db, Professor, first_name, last_name, "university.edu")

        professor = Professor(
            name=full_name,
            email=email_value,
            department=request.department.strip(),
        )
        db.add(professor)
        db.commit()
        db.refresh(professor)
        return {
            "success": True,
            "professor_id": professor.id,
            "email": professor.email,
            "message": "Professor added successfully",
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Professor with this email already exists")
    finally:
        db.close()


@app.post("/subjects")
def create_subject(request: SubjectCreateRequest):
    """Insert a new subject record."""
    if not request.name.strip() or not request.subject_code.strip():
        raise HTTPException(status_code=400, detail="Name and subject_code are required")

    db: Session = SessionLocal()
    try:
        existing_subject = (
            db.query(Subject)
            .filter(Subject.subject_code == request.subject_code.strip())
            .first()
        )
        if existing_subject:
            raise HTTPException(status_code=409, detail="Subject code already exists")

        subject = Subject(
            name=request.name.strip(),
            subject_code=request.subject_code.strip(),
            credits=request.credits,
        )
        db.add(subject)
        db.commit()
        db.refresh(subject)
        return {
            "success": True,
            "subject_id": subject.id,
            "message": "Subject added successfully",
        }
    finally:
        db.close()


@app.post("/divisions")
def create_division(request: DivisionCreateRequest):
    """Insert a new division record."""
    if not request.name.strip() or not request.subject_id or not request.professor_id:
        raise HTTPException(status_code=400, detail="name, subject_id and professor_id are required")

    db: Session = SessionLocal()
    try:
        subject = db.query(Subject).filter(Subject.id == request.subject_id).first()
        if not subject:
            raise HTTPException(status_code=400, detail="Invalid subject_id")

        professor = db.query(Professor).filter(Professor.id == request.professor_id).first()
        if not professor:
            raise HTTPException(status_code=400, detail="Invalid professor_id")

        division = Division(
            name=request.name.strip(),
            subject_id=request.subject_id,
            professor_id=request.professor_id,
        )
        db.add(division)
        db.commit()
        db.refresh(division)
        return {
            "success": True,
            "division_id": division.id,
            "message": "Division added successfully",
        }
    finally:
        db.close()


@app.put("/students/{student_id}")
def update_student(student_id: int, request: StudentUpdateRequest):
    """Update a student and refresh student_subjects mappings."""
    db: Session = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        division = db.query(Division).filter(Division.id == request.division_id).first()
        if not division:
            raise HTTPException(status_code=400, detail="Invalid division_id")

        if not request.name.strip():
            raise HTTPException(status_code=400, detail="Name is required")
        if not request.email.strip():
            raise HTTPException(status_code=400, detail="Email is required")

        student.name = request.name.strip()
        student.email = request.email.strip()
        student.division_id = request.division_id

        db.query(StudentSubject).filter(StudentSubject.student_id == student.id).delete()

        home_letter = division.name
        valid_subjects = (
            db.query(Subject)
            .filter(Subject.id.in_(request.subject_ids))
            .all()
            if request.subject_ids
            else []
        )
        valid_subject_ids = {s.id for s in valid_subjects}
        if valid_subject_ids != set(request.subject_ids):
            raise HTTPException(status_code=400, detail="One or more subject_ids are invalid")

        for subject_id in request.subject_ids:
            mapped_division = (
                db.query(Division)
                .filter(Division.subject_id == subject_id, Division.name == home_letter)
                .order_by(Division.id.asc())
                .first()
            )
            if not mapped_division:
                raise HTTPException(
                    status_code=400,
                    detail=f"No matching division for subject_id={subject_id} and division={home_letter}",
                )

            db.add(
                StudentSubject(
                    student_id=student.id,
                    subject_id=subject_id,
                    division_id=mapped_division.id,
                    enrollment_date=date.today(),
                    grade=None,
                )
            )

        db.commit()
        return {"success": True, "message": "Student updated successfully"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not update student due to unique constraint")
    finally:
        db.close()


@app.put("/professors/{professor_id}")
def update_professor(professor_id: int, request: ProfessorUpdateRequest):
    """Update professor record."""
    db: Session = SessionLocal()
    try:
        professor = db.query(Professor).filter(Professor.id == professor_id).first()
        if not professor:
            raise HTTPException(status_code=404, detail="Professor not found")
        if not request.name.strip() or not request.email.strip() or not request.department.strip():
            raise HTTPException(status_code=400, detail="name, email and department are required")

        professor.name = request.name.strip()
        professor.email = request.email.strip()
        professor.department = request.department.strip()
        db.commit()
        return {"success": True, "message": "Professor updated successfully"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Professor update violates unique constraint")
    finally:
        db.close()


@app.put("/subjects/{subject_id}")
def update_subject(subject_id: int, request: SubjectUpdateRequest):
    """Update subject record."""
    db: Session = SessionLocal()
    try:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        if not request.name.strip() or not request.subject_code.strip():
            raise HTTPException(status_code=400, detail="Name and subject_code are required")

        existing_code = (
            db.query(Subject)
            .filter(Subject.subject_code == request.subject_code.strip(), Subject.id != subject_id)
            .first()
        )
        if existing_code:
            raise HTTPException(status_code=409, detail="Subject code already exists")

        subject.name = request.name.strip()
        subject.subject_code = request.subject_code.strip()
        subject.credits = request.credits
        db.commit()
        return {"success": True, "message": "Subject updated successfully"}
    finally:
        db.close()


@app.put("/divisions/{division_id}")
def update_division(division_id: int, request: DivisionUpdateRequest):
    """Reassign division professor."""
    db: Session = SessionLocal()
    try:
        division = db.query(Division).filter(Division.id == division_id).first()
        if not division:
            raise HTTPException(status_code=404, detail="Division not found")

        professor = db.query(Professor).filter(Professor.id == request.professor_id).first()
        if not professor:
            raise HTTPException(status_code=400, detail="Invalid professor_id")

        division.professor_id = request.professor_id
        db.commit()
        return {"success": True, "message": "Division updated successfully"}
    finally:
        db.close()


@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    """Delete a student and related student_subject mappings."""
    db: Session = SessionLocal()
    try:
        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        db.query(StudentSubject).filter(StudentSubject.student_id == student.id).delete()
        db.delete(student)
        db.commit()
        return {"success": True, "message": "Student deleted successfully"}
    finally:
        db.close()


@app.delete("/professors/{professor_id}")
def delete_professor(professor_id: int):
    """Delete a professor only when no divisions are assigned."""
    db: Session = SessionLocal()
    try:
        professor = db.query(Professor).filter(Professor.id == professor_id).first()
        if not professor:
            raise HTTPException(status_code=404, detail="Professor not found")

        division_count = db.query(Division).filter(Division.professor_id == professor.id).count()
        if division_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete professor: reassign or delete linked divisions first",
            )

        db.delete(professor)
        db.commit()
        return {"success": True, "message": "Professor deleted successfully"}
    finally:
        db.close()


@app.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int):
    """Delete a subject only when no divisions or enrollments reference it."""
    db: Session = SessionLocal()
    try:
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")

        division_count = db.query(Division).filter(Division.subject_id == subject.id).count()
        if division_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete subject: delete linked divisions first",
            )

        enrollment_count = db.query(StudentSubject).filter(StudentSubject.subject_id == subject.id).count()
        if enrollment_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete subject: student enrollments still reference it",
            )

        db.delete(subject)
        db.commit()
        return {"success": True, "message": "Subject deleted successfully"}
    finally:
        db.close()


@app.delete("/divisions/{division_id}")
def delete_division(division_id: int):
    """Delete a division only when no students or enrollments reference it."""
    db: Session = SessionLocal()
    try:
        division = db.query(Division).filter(Division.id == division_id).first()
        if not division:
            raise HTTPException(status_code=404, detail="Division not found")

        student_count = db.query(Student).filter(Student.division_id == division.id).count()
        if student_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete division: move or delete students in this division first",
            )

        enrollment_count = db.query(StudentSubject).filter(StudentSubject.division_id == division.id).count()
        if enrollment_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete division: student_subject records still reference it",
            )

        db.delete(division)
        db.commit()
        return {"success": True, "message": "Division deleted successfully"}
    finally:
        db.close()


@app.get("/students/search")
def search_students(q: str):
    """Search students by name and return subjects list."""
    query = (q or "").strip()
    if not query:
        return {"students": []}

    db: Session = SessionLocal()
    try:
        students = (
            db.query(Student)
            .filter(Student.name.ilike(f"%{query}%"))
            .order_by(Student.name.asc())
            .limit(25)
            .all()
        )

        result = []
        for student in students:
            subject_rows = (
                db.query(Subject.id, Subject.name)
                .join(StudentSubject, StudentSubject.subject_id == Subject.id)
                .filter(StudentSubject.student_id == student.id)
                .order_by(Subject.name.asc())
                .all()
            )
            division = db.query(Division).filter(Division.id == student.division_id).first()
            result.append(
                {
                    "id": student.id,
                    "name": student.name,
                    "email": student.email,
                    "enrollment_number": student.enrollment_number,
                    "division": division.name if division else None,
                    "subject_ids": [sid for sid, _ in subject_rows],
                    "subject_names": [name for _, name in subject_rows],
                }
            )

        return {"students": result}
    finally:
        db.close()
