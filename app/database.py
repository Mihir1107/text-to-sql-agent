from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker
from app.models import Base

DATABASE_URL = "sqlite:///data/university.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables defined in models."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_schema_string() -> str:
    """Introspect the database and return a human-readable schema string."""
    inspector = inspect(engine)
    schema_parts = []

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        col_descriptions = []
        for col in columns:
            col_type = str(col["type"])
            nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
            pk = " PRIMARY KEY" if col.get("autoincrement", False) or col["name"] == "id" else ""
            col_descriptions.append(f"    {col['name']} {col_type} {nullable}{pk}")

        # Foreign keys
        fks = inspector.get_foreign_keys(table_name)
        fk_descriptions = []
        for fk in fks:
            constrained = ", ".join(fk["constrained_columns"])
            referred_table = fk["referred_table"]
            referred_cols = ", ".join(fk["referred_columns"])
            fk_descriptions.append(
                f"    FOREIGN KEY ({constrained}) REFERENCES {referred_table}({referred_cols})"
            )

        table_schema = f"TABLE: {table_name}\n"
        table_schema += "\n".join(col_descriptions)
        if fk_descriptions:
            table_schema += "\n" + "\n".join(fk_descriptions)

        schema_parts.append(table_schema)

    schema_text = "\n\n".join(schema_parts)

    try:
        with engine.connect() as conn:
            subject_rows = conn.execute(text("SELECT name FROM subjects ORDER BY name")).fetchall()
        subject_names = ", ".join(row[0] for row in subject_rows)
        if subject_names:
            schema_text += f"\n\n-- Available subjects: {subject_names}"
    except Exception:
        # Keep schema introspection resilient before seed data exists.
        pass

    return schema_text


def run_sql(sql: str) -> list[dict]:
    """Execute a raw SQL query and return results as a list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]
