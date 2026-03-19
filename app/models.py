from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Professor(Base):
    __tablename__ = "professors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    department = Column(String(100), nullable=False)

    divisions = relationship("Division", back_populates="professor")

    def __repr__(self):
        return f"<Professor(id={self.id}, name='{self.name}')>"


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    subject_code = Column(String(20), nullable=False, unique=True)
    credits = Column(Integer, nullable=False)

    divisions = relationship("Division", back_populates="subject")
    student_subjects = relationship("StudentSubject", back_populates="subject")

    def __repr__(self):
        return f"<Subject(id={self.id}, name='{self.name}')>"


class Division(Base):
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("professors.id", ondelete="RESTRICT"), nullable=False)

    subject = relationship("Subject", back_populates="divisions")
    professor = relationship("Professor", back_populates="divisions")
    students = relationship("Student", back_populates="division")
    student_subjects = relationship("StudentSubject", back_populates="division")

    __table_args__ = (
        UniqueConstraint('name', 'subject_id', name='uq_division_subject'),
        Index("ix_divisions_subject_id", "subject_id"),
        Index("ix_divisions_professor_id", "professor_id"),
    )

    def __repr__(self):
        return f"<Division(id={self.id}, name='{self.name}')>"


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    enrollment_number = Column(String(20), nullable=False, unique=True)
    division_id = Column(Integer, ForeignKey("divisions.id"), nullable=False)

    division = relationship("Division", back_populates="students")
    student_subjects = relationship("StudentSubject", back_populates="student")

    __table_args__ = (
        Index("ix_students_division_id", "division_id"),
    )

    def __repr__(self):
        return f"<Student(id={self.id}, name='{self.name}')>"


class StudentSubject(Base):
    __tablename__ = "student_subjects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    division_id = Column(Integer, ForeignKey("divisions.id"), nullable=False)
    enrollment_date = Column(Date, nullable=False)  # e.g. "2024-01-15"
    grade = Column(String(2), nullable=True)  # A, B, C, D, F or None

    student = relationship("Student", back_populates="student_subjects")
    subject = relationship("Subject", back_populates="student_subjects")
    division = relationship("Division", back_populates="student_subjects")

    __table_args__ = (
        UniqueConstraint('student_id', 'subject_id', name='uq_student_subject'),
        CheckConstraint("grade IN ('A','B','C','D','F') OR grade IS NULL", name='valid_grade'),
        Index("ix_student_subjects_student_id", "student_id"),
        Index("ix_student_subjects_subject_id", "subject_id"),
    )

    def __repr__(self):
        return (
            f"<StudentSubject(id={self.id}, student_id={self.student_id}, "
            f"subject_id={self.subject_id})>"
        )
