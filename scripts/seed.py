"""
Seed the university database with realistic sample data.

Run:  python seed.py
"""
import random
from datetime import date, timedelta

from app.database import SessionLocal, engine, init_db
from app.models import Base, Division, Professor, Student, StudentSubject, Subject

# Deterministic randomness
random.seed(42)

PROFESSORS = [
    {"name": "Dr. Ananya Sharma", "email": "ananya.sharma@university.edu", "department": "Mathematics"},
    {"name": "Dr. Rajesh Kulkarni", "email": "rajesh.kulkarni@university.edu", "department": "Physics"},
    {"name": "Dr. Priya Nair", "email": "priya.nair@university.edu", "department": "Computer Science"},
    {"name": "Dr. Vikram Desai", "email": "vikram.desai@university.edu", "department": "Humanities"},
    {"name": "Dr. Sunita Patel", "email": "sunita.patel@university.edu", "department": "Life Sciences"},
    {"name": "Dr. Karthik Reddy", "email": "karthik.reddy@university.edu", "department": "Computer Science"},
    {"name": "Dr. Meera Iyer", "email": "meera.iyer@university.edu", "department": "Statistics"},
    {"name": "Dr. Arvind Menon", "email": "arvind.menon@university.edu", "department": "Electrical Engineering"},
    {"name": "Dr. Neha Bansal", "email": "neha.bansal@university.edu", "department": "Economics"},
    {"name": "Dr. Sandeep Chatterjee", "email": "sandeep.chatterjee@university.edu", "department": "Computer Science"},
    {"name": "Dr. Pooja Kapoor", "email": "pooja.kapoor@university.edu", "department": "Applied Mathematics"},
    {"name": "Dr. Rohit Bhattacharya", "email": "rohit.bhattacharya@university.edu", "department": "Information Systems"},
]

SUBJECTS = [
    {"name": "Mathematics", "subject_code": "MATH101", "credits": 4},
    {"name": "Physics", "subject_code": "PHY101", "credits": 4},
    {"name": "Chemistry", "subject_code": "CHEM101", "credits": 3},
    {"name": "Computer Science", "subject_code": "CS101", "credits": 4},
    {"name": "English", "subject_code": "ENG101", "credits": 2},
    {"name": "History", "subject_code": "HIST101", "credits": 2},
    {"name": "Biology", "subject_code": "BIO101", "credits": 3},
    {"name": "Economics", "subject_code": "ECO101", "credits": 3},
    {"name": "Data Structures", "subject_code": "CS201", "credits": 4},
    {"name": "Algorithms", "subject_code": "CS202", "credits": 4},
    {"name": "Statistics", "subject_code": "STAT201", "credits": 3},
    {"name": "Machine Learning", "subject_code": "CS301", "credits": 4},
    {"name": "Linear Algebra", "subject_code": "MATH201", "credits": 4},
    {"name": "Discrete Mathematics", "subject_code": "MATH202", "credits": 3},
    {"name": "Database Systems", "subject_code": "CS203", "credits": 4},
    {"name": "Operating Systems", "subject_code": "CS204", "credits": 4},
    {"name": "Computer Networks", "subject_code": "CS205", "credits": 4},
    {"name": "Artificial Intelligence", "subject_code": "CS302", "credits": 4},
    {"name": "Calculus", "subject_code": "MATH102", "credits": 4},
    {"name": "Probability", "subject_code": "STAT202", "credits": 3},
]

# Keep exactly 15 subjects while ensuring all requested additions are present.
# We keep a broad CS/Math heavy curriculum and remove legacy low-priority entries.
SUBJECTS = [
    s
    for s in SUBJECTS
    if s["name"]
    not in {
        "History",
        "Biology",
        "Economics",
        "Chemistry",
        "Computer Science",
    }
]

DIVISION_NAMES = ["A", "B", "C", "D"]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Ananya", "Diya", "Myra", "Sara", "Aanya", "Aadhya", "Ira", "Riya", "Priya", "Kavya",
    "Rohan", "Kabir", "Shaurya", "Atharv", "Advait", "Arnav", "Dhruv", "Yash", "Harsh", "Tanmay",
    "Nisha", "Pooja", "Sneha", "Meera", "Neha", "Shruti", "Divya", "Swati", "Rashmi", "Aishwarya",
    "Raj", "Dev", "Om", "Karan", "Manav", "Nikhil", "Rahul", "Amit", "Sahil", "Varun",
    "Ishita", "Madhav", "Lavanya", "Pranav", "Sanya", "Ritvik", "Trisha", "Hemant", "Aditi", "Yuvraj",
]

LAST_NAMES = [
    "Patel", "Shah", "Kumar", "Singh", "Joshi", "Mehta", "Verma", "Gupta", "Reddy", "Nair",
    "Iyer", "Menon", "Rao", "Pillai", "Bhat", "Chauhan", "Thakur", "Mishra", "Pandey", "Saxena",
    "Kulkarni", "Deshpande", "Chatterjee", "Mukherjee", "Bansal", "Agarwal", "Bhatt", "Kapoor", "Srinivasan",
    "Subramanian", "Narayanan", "Mahajan", "Tiwari", "Tripathi", "Shukla", "Goswami",
]


def _make_email(name: str, idx: int) -> str:
    slug = name.lower().replace(" ", ".").replace("'", "")
    return f"{slug}.{idx}@student.university.edu"


def _random_enrollment_date():
    base = date(2024, 1, 10)
    delta = timedelta(days=random.randint(0, 240))
    return base + delta


def seed():
    Base.metadata.drop_all(bind=engine)
    init_db()

    session = SessionLocal()

    professors = [Professor(**p) for p in PROFESSORS]
    session.add_all(professors)
    session.flush()

    subjects = [Subject(**s) for s in SUBJECTS]
    session.add_all(subjects)
    session.flush()

    divisions = []
    for subj in subjects:
        for div_name in DIVISION_NAMES:
            prof = random.choice(professors)
            divisions.append(
                Division(name=div_name, subject_id=subj.id, professor_id=prof.id)
            )
    session.add_all(divisions)
    session.flush()

    division_map_by_subject_letter = {
        (d.subject_id, d.name): d
        for d in divisions
    }

    division_a_list = [d for d in divisions if d.name == "A"]

    students = []
    mihir_div = division_a_list[0]
    students.append(
        Student(
            name="Mihir Mandavia",
            email="mihir.mandavia@student.university.edu",
            enrollment_number="ENR001",
            division_id=mihir_div.id,
        )
    )

    used_names = {"Mihir Mandavia"}
    idx = 2
    while len(students) < 100:
        full_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if full_name in used_names:
            continue
        used_names.add(full_name)

        home_division = random.choice(division_a_list if len(students) % 4 == 0 else divisions)
        students.append(
            Student(
                name=full_name,
                email=_make_email(full_name, idx),
                enrollment_number=f"ENR{idx:03d}",
                division_id=home_division.id,
            )
        )
        idx += 1

    session.add_all(students)
    session.flush()

    grades = ["A", "B", "C", "D", "F", None]
    grade_weights = [0.22, 0.30, 0.24, 0.14, 0.03, 0.07]

    student_subject_rows = []
    for student in students:
        home_division = next(d for d in divisions if d.id == student.division_id)
        home_letter = home_division.name

        subject_count = random.randint(5, 7)
        selected_subjects = random.sample(subjects, k=subject_count)

        for subj in selected_subjects:
            mapped_division = division_map_by_subject_letter.get((subj.id, home_letter))
            if not mapped_division:
                candidate_divs = [d for d in divisions if d.subject_id == subj.id]
                mapped_division = random.choice(candidate_divs)

            student_subject_rows.append(
                StudentSubject(
                    student_id=student.id,
                    subject_id=subj.id,
                    division_id=mapped_division.id,
                    enrollment_date=_random_enrollment_date(),
                    grade=random.choices(grades, weights=grade_weights, k=1)[0],
                )
            )

    session.add_all(student_subject_rows)
    session.commit()
    session.close()

    print("✅ Database seeded successfully!")
    print(f"   Professors        : {len(professors)}")
    print(f"   Subjects          : {len(subjects)}")
    print(f"   Divisions         : {len(divisions)}")
    print(f"   Students          : {len(students)}")
    print(f"   Student Subjects  : {len(student_subject_rows)}")


if __name__ == "__main__":
    seed()
