"""
Streamlit multi-page interface for the Text-to-SQL agent.

Run:  streamlit run streamlit_app.py
"""
import httpx
import pandas as pd
import re
import streamlit as st

from app.database import run_sql

# Config
API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Text-to-SQL Agent",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    """
    <style>
    footer {visibility: hidden;}

    .answer-box {
        background: linear-gradient(135deg, #7C3AED22, #7C3AED11);
        border-left: 4px solid #7C3AED;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin: 0.5rem 0 1rem 0;
        font-size: 1.05rem;
        line-height: 1.6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _reset_student_form():
    st.session_state["student_first_name"] = ""
    st.session_state["student_last_name"] = ""
    st.session_state["student_division"] = "Select a division"


def _reset_professor_form():
    st.session_state["professor_first_name"] = ""
    st.session_state["professor_last_name"] = ""
    st.session_state["professor_department"] = ""


def _reset_subject_form():
    st.session_state["subject_name"] = ""
    st.session_state["subject_code"] = ""
    st.session_state["subject_credits"] = 3


def _reset_division_form():
    st.session_state["division_name"] = "A"
    st.session_state["division_subject"] = "Select subject"
    st.session_state["division_professor"] = "Select professor"


def _show_flash_success(key: str):
    message = st.session_state.pop(key, None)
    if message:
        st.success(message)


def _suggest_email_from_names(first_name: str, last_name: str, domain: str) -> str:
    first_slug = re.sub(r"[^a-z0-9]", "", first_name.strip().lower())
    last_slug = re.sub(r"[^a-z0-9]", "", last_name.strip().lower())
    if not first_slug or not last_slug:
        return f"firstname.lastname@{domain}"
    return f"{first_slug}.{last_slug}@{domain}"


# Shared helpers
@st.cache_data(ttl=30)
def fetch_students_view() -> pd.DataFrame:
    rows = run_sql(
        """
        SELECT
            s.id,
            s.name,
            s.email,
            s.enrollment_number,
            d.name as division,
            GROUP_CONCAT(DISTINCT sub.name) as subjects_enrolled,
            COUNT(DISTINCT ss.subject_id) as subject_count
        FROM students s
        LEFT JOIN divisions d ON s.division_id = d.id
        LEFT JOIN student_subjects ss ON s.id = ss.student_id
        LEFT JOIN subjects sub ON ss.subject_id = sub.id
        GROUP BY s.id
        ORDER BY s.id
        """
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def fetch_professors_view() -> pd.DataFrame:
    rows = run_sql(
        """
        SELECT
            p.id,
            p.name AS professor,
            p.email,
            p.department,
            COUNT(DISTINCT d.subject_id) AS subjects_taught,
            COUNT(DISTINCT d.id) AS divisions_assigned
        FROM professors p
        LEFT JOIN divisions d ON p.id = d.professor_id
        GROUP BY p.id, p.name, p.email, p.department
        ORDER BY p.name
        """
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def fetch_subjects_view() -> pd.DataFrame:
    rows = run_sql("SELECT * FROM subjects ORDER BY id")
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def fetch_divisions_join_view() -> pd.DataFrame:
    rows = run_sql(
        """
        SELECT
            d.name as division,
            s.name as subject,
            p.name as professor,
            COUNT(st.id) as student_count
        FROM divisions d
        JOIN subjects s ON d.subject_id = s.id
        JOIN professors p ON d.professor_id = p.id
        LEFT JOIN students st ON st.division_id = d.id
        GROUP BY d.id
        ORDER BY d.name, s.name
        """
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def fetch_divisions_options() -> list[dict]:
    return run_sql(
        """
        SELECT MIN(id) as id, name
        FROM divisions
        GROUP BY name
        ORDER BY name
        """
    )


@st.cache_data(ttl=10)
def fetch_next_enrollment() -> str:
    try:
        resp = httpx.get(f"{API_URL}/students/next-enrollment", timeout=5)
        resp.raise_for_status()
        return resp.json().get("next_enrollment", "ENR001")
    except Exception:
        row = run_sql(
            """
            SELECT COALESCE(MAX(CAST(SUBSTR(enrollment_number, 4) AS INTEGER)), 0) AS max_enrollment
            FROM students
            """
        )
        max_number = int(row[0]["max_enrollment"]) if row else 0
        next_number = max_number + 1
        return f"ENR{next_number:03d}"


@st.cache_data(ttl=30)
def fetch_all_subjects_options() -> list[dict]:
    return run_sql("SELECT id, name FROM subjects ORDER BY name")


@st.cache_data(ttl=30)
def fetch_all_professors_options() -> list[dict]:
    return run_sql("SELECT id, name FROM professors ORDER BY name")


@st.cache_data(ttl=30)
def fetch_divisions_manage_options() -> list[dict]:
    return run_sql(
        """
        SELECT
            d.id,
            d.name AS division,
            s.name AS subject,
            p.name AS professor,
            d.professor_id
        FROM divisions d
        JOIN subjects s ON s.id = d.subject_id
        JOIN professors p ON p.id = d.professor_id
        ORDER BY d.name, s.name, p.name
        """
    )


@st.cache_data(ttl=20)
def fetch_quick_stats() -> dict:
    total_students = run_sql("SELECT COUNT(*) AS count FROM students")[0]["count"]
    total_professors = run_sql("SELECT COUNT(*) AS count FROM professors")[0]["count"]
    total_subjects = run_sql("SELECT COUNT(*) AS count FROM subjects")[0]["count"]
    total_divisions = run_sql("SELECT COUNT(*) AS count FROM divisions")[0]["count"]

    popular_division_row = run_sql(
        """
        SELECT d.name AS division, COUNT(st.id) AS student_count
        FROM divisions d
        LEFT JOIN students st ON st.division_id = d.id
        GROUP BY d.id
        ORDER BY student_count DESC, d.name ASC
        LIMIT 1
        """
    )

    top_professor_row = run_sql(
        """
        SELECT p.name AS professor, COUNT(DISTINCT d.subject_id) AS subject_count
        FROM professors p
        LEFT JOIN divisions d ON d.professor_id = p.id
        GROUP BY p.id
        ORDER BY subject_count DESC, p.name ASC
        LIMIT 1
        """
    )

    popular_division = "N/A"
    if popular_division_row:
        row = popular_division_row[0]
        popular_division = f"{row['division']} ({row['student_count']})"

    top_professor = "N/A"
    if top_professor_row:
        row = top_professor_row[0]
        top_professor = f"{row['professor']} ({row['subject_count']})"

    return {
        "total_students": total_students,
        "total_professors": total_professors,
        "total_subjects": total_subjects,
        "total_divisions": total_divisions,
        "popular_division": popular_division,
        "top_professor": top_professor,
    }


@st.cache_data(ttl=30)
def fetch_student_subject_names(student_id: int) -> list[str]:
    rows = run_sql(
        f"""
        SELECT sub.name
        FROM student_subjects ss
        JOIN subjects sub ON sub.id = ss.subject_id
        WHERE ss.student_id = {int(student_id)}
        ORDER BY sub.name
        """
    )
    return [row["name"] for row in rows]


def filter_dataframe(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty or not query:
        return df
    text_df = df.astype(str)
    mask = text_df.apply(lambda col: col.str.contains(query, case=False, na=False)).any(axis=1)
    return df[mask]


def render_table_controls(df: pd.DataFrame, table_name: str, include_division_filter: bool = False):
    metric_cols = st.columns(3)

    if table_name == "students":
        metric_cols[0].metric("Total rows", len(df))
        metric_cols[1].metric("Divisions", int(df["division"].nunique()) if not df.empty else 0)
        metric_cols[2].metric("Unique enrollments", int(df["enrollment_number"].nunique()) if not df.empty else 0)

        search_query = st.text_input(
            "🔍 Search...",
            placeholder="Type to filter...",
            key="search_students",
        )

        filtered_df = df
        if include_division_filter and not df.empty:
            division_filter = st.selectbox(
                "Filter by Division",
                ["All", "A", "B", "C", "D"],
                key="students_division_filter",
            )
            if division_filter != "All":
                filtered_df = filtered_df[filtered_df["division"].astype(str) == division_filter]

        filtered_df = filter_dataframe(filtered_df, search_query)

        display_df = filtered_df[["name", "email", "enrollment_number", "division", "subject_count"]].copy()
        display_df["subject_count"] = display_df["subject_count"].apply(
            lambda value: f"{int(value)} subjects"
        )

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            hide_index=True,
        )

        st.download_button(
            "📥 Export as CSV",
            display_df.to_csv(index=False),
            file_name="students.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_students",
        )

        st.markdown("### Student Details")
        if filtered_df.empty:
            st.info("No students available for details view.")
            return

        student_names = filtered_df["name"].tolist()
        selected_name = st.selectbox(
            "Select a student to view subjects",
            student_names,
            key="student_details_select",
        )
        selected_row = filtered_df[filtered_df["name"] == selected_name].iloc[0]
        subjects = fetch_student_subject_names(int(selected_row["id"]))

        pills_html = " ".join([
            f'<span style="background-color:#7C3AED; color:white; '
            f'padding:4px 12px; border-radius:20px; margin:4px; '
            f'font-size:13px; display:inline-block">{s}</span>'
            for s in subjects
        ])
        st.markdown(pills_html or "No subjects found.", unsafe_allow_html=True)

        detail_cols = st.columns(3)
        detail_cols[0].metric("Division", str(selected_row["division"]))
        detail_cols[1].metric("Enrollment", str(selected_row["enrollment_number"]))
        detail_cols[2].metric("Total Subjects", int(selected_row["subject_count"]))
        return
    elif table_name == "professors":
        subjects_total = int(df["subjects_taught"].sum()) if not df.empty else 0
        divisions_total = int(df["divisions_assigned"].sum()) if not df.empty else 0
        metric_cols[0].metric("Total rows", len(df))
        metric_cols[1].metric("Subjects they teach", subjects_total)
        metric_cols[2].metric("Divisions assigned", divisions_total)
    elif table_name == "subjects":
        total_credits = int(df["credits"].sum()) if not df.empty else 0
        avg_credits = round(float(df["credits"].mean()), 1) if not df.empty else 0.0
        metric_cols[0].metric("Total rows", len(df))
        metric_cols[1].metric("Total credits", total_credits)
        metric_cols[2].metric("Average credits", avg_credits)
    else:
        total_students = int(df["student_count"].sum()) if not df.empty else 0
        unique_professors = int(df["professor"].nunique()) if not df.empty else 0
        metric_cols[0].metric("Total rows", len(df))
        metric_cols[1].metric("Total students", total_students)
        metric_cols[2].metric("Unique professors", unique_professors)

    search_query = st.text_input(
        "🔍 Search...",
        placeholder="Type to filter...",
        key=f"search_{table_name}",
    )

    filtered_df = df
    if include_division_filter and not df.empty:
        division_filter = st.selectbox(
            "Filter by Division",
            ["All", "A", "B", "C", "D"],
            key="students_division_filter",
        )
        if division_filter != "All":
            filtered_df = filtered_df[filtered_df["division"].astype(str) == division_filter]

    filtered_df = filter_dataframe(filtered_df, search_query)

    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    st.download_button(
        "📥 Export as CSV",
        filtered_df.to_csv(index=False),
        file_name=f"{table_name}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"download_{table_name}",
    )


def render_ask_agent_page():
    st.markdown("# 🤖 Text-to-SQL Agent")
    st.caption("Ask questions about the university database in plain English.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                data = msg["data"]
                st.markdown(
                    f'<div class="answer-box">{data.get("answer", "")}</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("🔍 Generated SQL"):
                    st.code(data.get("sql") or "", language="sql")
                with st.expander("📊 Raw Results"):
                    results = data.get("results")
                    if results:
                        st.dataframe(results, use_container_width=True)
                    else:
                        st.info("No results returned.")

    user_input = st.chat_input("Ask a question about the university…")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    # Send last 6 messages as history
                    history = [
                        {"role": m["role"], "content": m.get("content") or m.get("data", {}).get("answer", "")}
                        for m in st.session_state.messages[-6:]
                        if m["role"] in ["user", "assistant"]
                    ]
                    payload = {
                        "question": user_input,
                        "history": history
                    }
                    resp = httpx.post(
                        f"{API_URL}/ask",
                        json=payload,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.ConnectError:
                    data = {
                        "answer": "Cannot reach the API. Make sure the FastAPI server is running (`uvicorn main:app --reload`).",
                        "sql": None,
                        "results": None,
                    }
                except Exception as exc:
                    data = {
                        "answer": f"An error occurred: {exc}",
                        "sql": None,
                        "results": None,
                    }

            st.markdown(
                f'<div class="answer-box">{data.get("answer", "")}</div>',
                unsafe_allow_html=True,
            )
            with st.expander("🔍 Generated SQL"):
                st.code(data.get("sql") or "", language="sql")
            with st.expander("📊 Raw Results"):
                results = data.get("results")
                if results:
                    st.dataframe(results, use_container_width=True)
                else:
                    st.info("No results returned.")

        st.session_state.messages.append({"role": "assistant", "data": data})


def render_database_explorer_page():
    st.title("🗄️ Database Explorer")

    if "explorer_tab" not in st.session_state:
        st.session_state.explorer_tab = 0

    tab_names = ["👨‍🎓 Students", "👨‍🏫 Professors", "📚 Subjects", "🏫 Divisions"]
    selected_tab = st.radio(
        "Explorer Tabs",
        options=tab_names,
        index=st.session_state.explorer_tab,
        horizontal=True,
        label_visibility="collapsed",
    )

    current_idx = tab_names.index(selected_tab)
    if current_idx != st.session_state.explorer_tab:
        st.session_state.explorer_tab = current_idx
        st.rerun()

    if current_idx == 0:
        students_df = fetch_students_view()
        render_table_controls(students_df, "students", include_division_filter=True)

    elif current_idx == 1:
        professors_df = fetch_professors_view()
        render_table_controls(professors_df, "professors")

    elif current_idx == 2:
        subjects_df = fetch_subjects_view()
        render_table_controls(subjects_df, "subjects")

    elif current_idx == 3:
        if "selected_division" not in st.session_state:
            st.session_state.selected_division = "A"

        division_cols = st.columns(4)
        for idx, div in enumerate(["A", "B", "C", "D"]):
            with division_cols[idx]:
                btn_type = "primary" if st.session_state.selected_division == div else "secondary"
                if st.button(
                    f"🏫 Division {div}",
                    use_container_width=True,
                    type=btn_type,
                    key=f"div_{div}",
                ):
                    st.session_state.selected_division = div
                    st.session_state.explorer_tab = 3
                    st.session_state.current_page = "explorer"
                    st.rerun()

        selected_division = st.session_state.selected_division

        stats_row = run_sql(
            f"""
            SELECT
                COUNT(DISTINCT d.subject_id) as total_subjects,
                COUNT(DISTINCT d.professor_id) as total_professors
            FROM divisions d
            WHERE d.name = '{selected_division}'
            """
        )[0]
        student_count_row = run_sql(
            f"""
            SELECT COUNT(DISTINCT s.id) as total_students
            FROM students s
            JOIN divisions d ON s.division_id = d.id
            WHERE d.name = '{selected_division}'
            """
        )[0]

        metric_cols = st.columns(3)
        metric_cols[0].metric("Total subjects taught", int(stats_row["total_subjects"]))
        metric_cols[1].metric("Total students", int(student_count_row["total_students"]))
        metric_cols[2].metric("Total professors teaching", int(stats_row["total_professors"]))

        subjects_in_division_df = pd.DataFrame(
            run_sql(
                f"""
                SELECT
                    s.name as subject,
                    p.name as professor,
                    p.email as professor_email,
                    p.department,
                    COUNT(ss.student_id) as enrolled_students
                FROM divisions d
                JOIN subjects s ON d.subject_id = s.id
                JOIN professors p ON d.professor_id = p.id
                LEFT JOIN student_subjects ss ON ss.division_id = d.id
                WHERE d.name = '{selected_division}'
                GROUP BY d.id
                ORDER BY s.name
                """
            )
        )
        st.dataframe(subjects_in_division_df, use_container_width=True, hide_index=True)

        st.subheader(f"👨‍🎓 Students in Division {selected_division}")
        students_in_division_df = pd.DataFrame(
            run_sql(
                f"""
                SELECT
                    s.name,
                    s.email,
                    s.enrollment_number,
                    COUNT(ss.subject_id) as subjects_count
                FROM students s
                JOIN divisions d ON s.division_id = d.id
                LEFT JOIN student_subjects ss ON s.id = ss.student_id
                WHERE d.name = '{selected_division}'
                GROUP BY s.id, s.name, s.email, s.enrollment_number
                ORDER BY s.name
                """
            )
        )
        st.dataframe(students_in_division_df, use_container_width=True, hide_index=True)


def render_manage_data_page():
    st.title("➕ Manage Data")
    tab_student, tab_professor, tab_subject, tab_division, tab_update, tab_delete = st.tabs(
        [
            "👨‍🎓 Add Student",
            "👨‍🏫 Add Professor",
            "📚 Add Subject",
            "🏫 Add Division",
            "✏️ Update Record",
            "🗑️ Delete Record",
        ]
    )

    with tab_student:
        _show_flash_success("student_success_msg")
        divisions = fetch_divisions_options()
        if "next_enrollment" not in st.session_state:
            st.session_state["next_enrollment"] = fetch_next_enrollment()
        next_enrollment = st.session_state["next_enrollment"]
        division_options = ["Select a division"] + [item["name"] for item in divisions]
        division_map = {item["name"]: item["id"] for item in divisions}

        if "add_step" not in st.session_state:
            st.session_state.add_step = 1
        if "new_student" not in st.session_state:
            st.session_state.new_student = {}
        if "selected_subjects" not in st.session_state:
            st.session_state.selected_subjects = []

        step = st.session_state.add_step
        
        steps = ["① Basic Info", "② Choose Subjects", "③ Review & Confirm"]
        colors = []
        for i, curr_step in enumerate(steps, 1):
            if i < st.session_state.add_step:
                colors.append(f'<span style="color:#16A34A;font-weight:bold">{curr_step}</span>')
            elif i == st.session_state.add_step:
                colors.append(f'<span style="color:#7C3AED;font-weight:bold">{curr_step}</span>')
            else:
                colors.append(f'<span style="color:#6B7280">{curr_step}</span>')

        st.markdown(" → ".join(colors), unsafe_allow_html=True)
        st.divider()

        if step == 1:
            st.session_state.setdefault("student_first_name", "")
            st.session_state.setdefault("student_last_name", "")
            st.session_state.setdefault("student_division", "Select a division")

            student_first_name = st.text_input("First Name", value=st.session_state.student_first_name)
            student_last_name = st.text_input("Last Name", value=st.session_state.student_last_name)
            
            base_email = _suggest_email_from_names(
                student_first_name,
                student_last_name,
                "student.university.edu",
            )
            
            unique_email = base_email
            if student_first_name or student_last_name:
                try:
                    resp = httpx.get(f"{API_URL}/students/check-email", params={"email": base_email}, timeout=5)
                    if resp.status_code == 200:
                        unique_email = resp.json().get("suggested", base_email)
                except Exception:
                    pass

            st.info(f"📧 Auto-assigned email: {unique_email}")
            
            info_col, refresh_col = st.columns([5, 1])
            with info_col:
                st.info(f"🎫 Enrollment number: {next_enrollment}")
            with refresh_col:
                if st.button("🔄 Refresh", key="refresh_enr"):
                    if "next_enrollment" in st.session_state:
                        del st.session_state["next_enrollment"]
                    fetch_next_enrollment.clear()
                    st.rerun()

            curr_div = st.session_state.student_division
            div_idx = division_options.index(curr_div) if curr_div in division_options else 0
            student_division = st.selectbox("Division", options=division_options, index=div_idx)

            if st.button("Next → Choose Subjects", type="primary"):
                name_pattern = r"^[A-Za-z][A-Za-z\s'-]*$"
                if not student_first_name.strip() or not re.match(name_pattern, student_first_name.strip()):
                    st.error("Please enter a valid first name")
                elif not student_last_name.strip() or not re.match(name_pattern, student_last_name.strip()):
                    st.error("Please enter a valid last name")
                elif student_division == "Select a division":
                    st.error("Please select a division.")
                else:
                    st.session_state.student_first_name = student_first_name
                    st.session_state.student_last_name = student_last_name
                    st.session_state.student_division = student_division
                    
                    st.session_state.new_student = {
                        "first_name": student_first_name.strip(),
                        "last_name": student_last_name.strip(),
                        "name": f"{student_first_name.strip()} {student_last_name.strip()}",
                        "email": unique_email,
                        "enrollment_number": next_enrollment,
                        "division": student_division,
                        "division_id": division_map[student_division]
                    }
                    st.session_state.add_step = 2
                    st.rerun()

        elif step == 2:
            ns = st.session_state.new_student
            with st.container(border=True):
                st.markdown(f"**👤 Name:** {ns['name']} &nbsp;|&nbsp; **📧 Email:** {ns['email']} &nbsp;|&nbsp; **🎫 Enrollment:** {ns['enrollment_number']} &nbsp;|&nbsp; **🏫 Division:** {ns['division']}")
            
            st.subheader("Choose Subjects (minimum 5, maximum 7)")
            
            subjects_df = fetch_subjects_view()
            all_subject_names = subjects_df["name"].tolist()
            
            selected = st.multiselect(
                "Select subjects",
                options=all_subject_names,
                default=st.session_state.selected_subjects,
                max_selections=7
            )
            
            color = "green" if 5 <= len(selected) <= 7 else "red"
            st.markdown(f"Selected: :{color}[{len(selected)}/7 subjects]")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("← Back"):
                    st.session_state.selected_subjects = selected
                    st.session_state.add_step = 1
                    st.rerun()
            with col2:
                if st.button("Next → Review", type="primary"):
                    if len(selected) < 5:
                        st.error("Please select at least 5 subjects.")
                    else:
                        st.session_state.selected_subjects = selected
                        st.session_state.add_step = 3
                        st.rerun()

        elif step == 3:
            ns = st.session_state.new_student
            st.subheader("📋 Review Your Details")
            
            subjects_df = fetch_subjects_view()
            selected_names = st.session_state.selected_subjects
            
            selected_df = subjects_df[subjects_df["name"].isin(selected_names)]
            total_credits = int(selected_df["credits"].sum())
            
            with st.container(border=True):
                st.markdown("### Personal Information")
                st.markdown(f"| Field | Value |\n|---|---|\n| **Name** | {ns['name']} |\n| **Email** | {ns['email']} |\n| **Enrollment** | {ns['enrollment_number']} |\n| **Division** | {ns['division']} |")
                
                st.markdown("### Enrolled Subjects")
                if selected_names:
                    pills_html = " ".join([
                        f'<span style="background-color:#7C3AED; color:white; padding:4px 12px; border-radius:20px; margin:4px; font-size:13px; display:inline-block">{s}</span>'
                        for s in selected_names
                    ])
                    st.markdown(pills_html, unsafe_allow_html=True)
                else:
                    st.markdown("None")
                st.markdown(f"**Total Credits:** {total_credits}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("← Edit"):
                    st.session_state.add_step = 2
                    st.rerun()
            with col2:
                if st.button("✅ Confirm & Enroll", type="primary"):
                    payload = {
                        "name": ns["name"],
                        "first_name": ns["first_name"],
                        "last_name": ns["last_name"],
                        "email": ns["email"],
                        "enrollment_number": ns["enrollment_number"],
                        "division_id": ns["division_id"],
                    }
                    try:
                        resp = httpx.post(f"{API_URL}/students", json=payload, timeout=10)
                        if resp.status_code >= 400:
                            detail = resp.json().get("detail", "Unable to add student")
                            st.error(str(detail))
                        else:
                            data = resp.json()
                            if data.get("success"):
                                student_id = data.get("student_id")
                                subject_ids = selected_df["id"].tolist()
                                update_payload = {
                                    "name": ns["name"],
                                    "email": data.get("email") or ns["email"],
                                    "division_id": ns["division_id"],
                                    "subject_ids": subject_ids
                                }
                                put_resp = httpx.put(f"{API_URL}/students/{student_id}", json=update_payload, timeout=10)
                                if put_resp.status_code >= 400:
                                    st.error("Student created but failed to assign subjects. " + str(put_resp.json().get("detail")))
                                else:
                                    st.balloons()
                                    st.success("🎉 Student enrolled successfully!")
                                    fetch_students_view.clear()
                                    fetch_divisions_join_view.clear()
                                    fetch_next_enrollment.clear()
                                    st.session_state.add_step = 4
                                    st.rerun()
                            else:
                                st.error(data.get("message", "Unable to add student"))
                    except Exception as e:
                        st.error(f"Could not add student. Please try again. Error: {e}")
                        
        elif step == 4:
            ns = st.session_state.new_student
            with st.container(border=True):
                st.success("Student added to database.")
                st.markdown(f"**Name:** {ns['name']}  \n**Email:** {ns['email']}  \n**Enrollment:** {ns['enrollment_number']}  \n**Division:** {ns['division']}")
                st.markdown("### Enrolled Subjects")
                if st.session_state.selected_subjects:
                    pills_html = " ".join([
                        f'<span style="background-color:#7C3AED; color:white; padding:4px 12px; border-radius:20px; margin:4px; font-size:13px; display:inline-block">{s}</span>'
                        for s in st.session_state.selected_subjects
                    ])
                    st.markdown(pills_html, unsafe_allow_html=True)
            
            if st.button("Add Another Student", type="primary"):
                st.session_state.add_step = 1
                st.session_state.new_student = {}
                st.session_state.selected_subjects = []
                _reset_student_form()
                if "next_enrollment" in st.session_state:
                    del st.session_state["next_enrollment"]
                st.rerun()

    with tab_professor:
        _show_flash_success("professor_success_msg")
        st.session_state.setdefault("professor_first_name", "")
        st.session_state.setdefault("professor_last_name", "")
        st.session_state.setdefault("professor_department", "")

        with st.form("add_professor_form"):
            professor_first_name = st.text_input("First Name", key="professor_first_name")
            professor_last_name = st.text_input("Last Name", key="professor_last_name")
            professor_email_preview = _suggest_email_from_names(
                professor_first_name,
                professor_last_name,
                "university.edu",
            )
            st.caption(f"Email will be auto-assigned, e.g. {professor_email_preview}")
            professor_department = st.text_input(
                "Department",
                placeholder="e.g. Computer Science",
                key="professor_department",
            )
            professor_submitted = st.form_submit_button("➕ Add Professor")

        if professor_submitted:
            name_pattern = r"^[A-Za-z][A-Za-z\s'-]*$"
            if not professor_first_name.strip() or not re.match(name_pattern, professor_first_name.strip()):
                st.error("Please enter a valid first name.")
            elif not professor_last_name.strip() or not re.match(name_pattern, professor_last_name.strip()):
                st.error("Please enter a valid last name.")
            elif not professor_department.strip():
                st.error("Department is required.")
            else:
                payload = {
                    "name": f"{professor_first_name.strip()} {professor_last_name.strip()}",
                    "first_name": professor_first_name.strip(),
                    "last_name": professor_last_name.strip(),
                    "department": professor_department.strip(),
                }
                try:
                    resp = httpx.post(f"{API_URL}/professors", json=payload, timeout=10)
                    if resp.status_code >= 400:
                        detail = resp.json().get("detail", "Unable to add professor")
                        st.error(str(detail))
                    else:
                        data = resp.json()
                        if data.get("success"):
                            fetch_professors_view.clear()
                            fetch_all_professors_options.clear()
                            fetch_divisions_join_view.clear()
                            created_email = data.get("email")
                            st.session_state["professor_success_msg"] = (
                                f"Professor added successfully. Assigned email: {created_email}"
                                if created_email
                                else "Professor added successfully."
                            )
                            _reset_professor_form()
                            st.rerun()
                        else:
                            st.error(data.get("message", "Unable to add professor"))
                except Exception as exc:
                    st.error(f"Unable to add professor: {exc}")

    with tab_subject:
        _show_flash_success("subject_success_msg")
        st.session_state.setdefault("subject_name", "")
        st.session_state.setdefault("subject_code", "")
        st.session_state.setdefault("subject_credits", 3)

        with st.form("add_subject_form"):
            subject_name = st.text_input(
                "Subject Name",
                placeholder="e.g. Data Structures",
                key="subject_name",
            )
            subject_code = st.text_input(
                "Subject Code",
                placeholder="e.g. CS201",
                key="subject_code",
            )
            subject_credits = st.number_input(
                "Credits",
                min_value=1,
                max_value=6,
                value=3,
                step=1,
                key="subject_credits",
            )
            subject_submitted = st.form_submit_button("➕ Add Subject")

        if subject_submitted:
            if not subject_name.strip() or not subject_code.strip():
                st.error("Subject Name and Subject Code are required.")
            else:
                payload = {
                    "name": subject_name.strip(),
                    "subject_code": subject_code.strip(),
                    "credits": int(subject_credits),
                }
                try:
                    resp = httpx.post(f"{API_URL}/subjects", json=payload, timeout=10)
                    if resp.status_code >= 400:
                        detail = resp.json().get("detail", "Unable to add subject")
                        st.error(str(detail))
                    else:
                        data = resp.json()
                        if data.get("success"):
                            fetch_subjects_view.clear()
                            fetch_all_subjects_options.clear()
                            fetch_divisions_join_view.clear()
                            st.session_state["subject_success_msg"] = "Subject added successfully."
                            _reset_subject_form()
                            st.rerun()
                        else:
                            st.error(data.get("message", "Unable to add subject"))
                except Exception as exc:
                    st.error(f"Unable to add subject: {exc}")

    with tab_division:
        _show_flash_success("division_success_msg")
        subjects = fetch_all_subjects_options()
        professors = fetch_all_professors_options()

        subject_options = ["Select subject"] + [item["name"] for item in subjects]
        subject_map = {item["name"]: item["id"] for item in subjects}
        professor_options = ["Select professor"] + [item["name"] for item in professors]
        professor_map = {item["name"]: item["id"] for item in professors}
        st.session_state.setdefault("division_name", "A")
        st.session_state.setdefault("division_subject", "Select subject")
        st.session_state.setdefault("division_professor", "Select professor")

        with st.form("add_division_form"):
            division_name = st.selectbox("Division Name", ["A", "B", "C", "D", "E", "F"], key="division_name")
            selected_subject = st.selectbox("Subject", options=subject_options, key="division_subject")
            selected_professor = st.selectbox("Professor", options=professor_options, key="division_professor")
            division_submitted = st.form_submit_button("➕ Add Division")

        if division_submitted:
            if selected_subject == "Select subject" or selected_professor == "Select professor":
                st.error("Subject and Professor are required.")
            else:
                payload = {
                    "name": division_name,
                    "subject_id": subject_map[selected_subject],
                    "professor_id": professor_map[selected_professor],
                }
                try:
                    resp = httpx.post(f"{API_URL}/divisions", json=payload, timeout=10)
                    if resp.status_code >= 400:
                        detail = resp.json().get("detail", "Unable to add division")
                        st.error(str(detail))
                    else:
                        data = resp.json()
                        if data.get("success"):
                            fetch_divisions_join_view.clear()
                            fetch_divisions_options.clear()
                            st.session_state["division_success_msg"] = "Division added successfully."
                            _reset_division_form()
                            st.rerun()
                        else:
                            st.error(data.get("message", "Unable to add division"))
                except Exception as exc:
                    st.error(f"Unable to add division: {exc}")

    with tab_update:
        st.subheader("✏️ Update Record")
        up_student, up_professor, up_subject, up_division_tab = st.tabs(
            ["Update Student", "Update Professor", "Update Subject", "Update Division"]
        )

        with up_student:
            search_q = st.text_input(
                "Search student by name",
                placeholder="Type a student name...",
                key="update_student_search",
            )
            students_found: list[dict] = []
            if search_q.strip():
                try:
                    resp = httpx.get(
                        f"{API_URL}/students/search",
                        params={"q": search_q.strip()},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    students_found = resp.json().get("students", [])
                except Exception as exc:
                    st.error(f"Search failed: {exc}")

            if students_found:
                option_map = {
                    f"{row['name']} ({row['enrollment_number']})": row
                    for row in students_found
                }
                picked_label = st.selectbox("Matching students", list(option_map.keys()))
                selected_student = option_map[picked_label]

                divisions = fetch_divisions_options()
                division_options = [item["name"] for item in divisions]
                division_map = {item["name"]: item["id"] for item in divisions}

                all_subjects = fetch_all_subjects_options()
                subject_name_to_id = {item["name"]: item["id"] for item in all_subjects}
                subject_names = list(subject_name_to_id.keys())

                default_division = selected_student.get("division") if selected_student.get("division") in division_options else division_options[0]
                default_subjects = [
                    name for name in selected_student.get("subject_names", [])
                    if name in subject_name_to_id
                ]

                with st.form("update_student_form"):
                    up_name = st.text_input("Name", value=selected_student.get("name", ""))
                    up_email = st.text_input("Email", value=selected_student.get("email", ""))
                    up_division_name = st.selectbox(
                        "Division",
                        division_options,
                        index=division_options.index(default_division),
                    )
                    up_subjects = st.multiselect(
                        "Subjects",
                        options=subject_names,
                        default=default_subjects,
                    )
                    up_submit = st.form_submit_button("💾 Update Student")

                if up_submit:
                    if not up_name.strip() or not up_email.strip():
                        st.error("Name and email are required.")
                    else:
                        payload = {
                            "name": up_name.strip(),
                            "email": up_email.strip(),
                            "division_id": division_map[up_division_name],
                            "subject_ids": [subject_name_to_id[name] for name in up_subjects],
                        }
                        try:
                            resp = httpx.put(
                                f"{API_URL}/students/{selected_student['id']}",
                                json=payload,
                                timeout=15,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to update student")
                                st.error(str(detail))
                            else:
                                st.success("Student updated successfully.")
                                fetch_students_view.clear()
                                fetch_divisions_join_view.clear()
                                st.session_state["update_student_search"] = ""
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to update student: {exc}")
            elif search_q.strip():
                st.info("No students matched your search.")

        with up_professor:
            prof_q = st.text_input(
                "Search professor by name",
                placeholder="Type a professor name...",
                key="update_professor_search",
            )
            prof_df = fetch_professors_view()
            prof_matches = filter_dataframe(prof_df, prof_q) if prof_q.strip() else pd.DataFrame()

            if not prof_matches.empty:
                prof_options = {
                    f"{row['professor']} ({row['email']})": row
                    for _, row in prof_matches.iterrows()
                }
                prof_label = st.selectbox("Matching professors", list(prof_options.keys()))
                selected_prof = prof_options[prof_label]

                with st.form("update_professor_form"):
                    up_prof_name = st.text_input("Name", value=str(selected_prof["professor"]))
                    up_prof_email = st.text_input("Email", value=str(selected_prof["email"]))
                    up_prof_dept = st.text_input("Department", value=str(selected_prof["department"]))
                    up_prof_submit = st.form_submit_button("💾 Update Professor")

                if up_prof_submit:
                    if not up_prof_name.strip():
                        st.error("Name is required.")
                    else:
                        payload = {
                            "name": up_prof_name.strip(),
                            "email": up_prof_email.strip(),
                            "department": up_prof_dept.strip(),
                        }
                        try:
                            resp = httpx.put(
                                f"{API_URL}/professors/{int(selected_prof['id'])}",
                                json=payload,
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to update professor")
                                st.error(str(detail))
                            else:
                                st.success("Professor updated successfully.")
                                fetch_professors_view.clear()
                                fetch_all_professors_options.clear()
                                fetch_divisions_join_view.clear()
                                st.session_state["update_professor_search"] = ""
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to update professor: {exc}")
            elif prof_q.strip():
                st.info("No professors matched your search.")

        with up_subject:
            subj_q = st.text_input(
                "Search subject by name",
                placeholder="Type a subject name...",
                key="update_subject_search",
            )
            subj_df = fetch_subjects_view()
            subj_matches = filter_dataframe(subj_df, subj_q) if subj_q.strip() else pd.DataFrame()

            if not subj_matches.empty:
                subj_options = {
                    f"{row['name']} ({row['subject_code']})": row
                    for _, row in subj_matches.iterrows()
                }
                subj_label = st.selectbox("Matching subjects", list(subj_options.keys()))
                selected_subj = subj_options[subj_label]

                with st.form("update_subject_form"):
                    up_subj_name = st.text_input("Name", value=str(selected_subj["name"]))
                    up_subj_code = st.text_input("Subject Code", value=str(selected_subj["subject_code"]))
                    up_subj_credits = st.number_input(
                        "Credits",
                        min_value=1,
                        max_value=6,
                        value=int(selected_subj["credits"]),
                        step=1,
                    )
                    up_subj_submit = st.form_submit_button("💾 Update Subject")

                if up_subj_submit:
                    if not up_subj_name.strip() or not up_subj_code.strip():
                        st.error("Name and subject code are required.")
                    else:
                        payload = {
                            "name": up_subj_name.strip(),
                            "subject_code": up_subj_code.strip(),
                            "credits": int(up_subj_credits),
                        }
                        try:
                            resp = httpx.put(
                                f"{API_URL}/subjects/{int(selected_subj['id'])}",
                                json=payload,
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to update subject")
                                st.error(str(detail))
                            else:
                                st.success("Subject updated successfully.")
                                fetch_subjects_view.clear()
                                fetch_all_subjects_options.clear()
                                fetch_divisions_join_view.clear()
                                st.session_state["update_subject_search"] = ""
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to update subject: {exc}")
            elif subj_q.strip():
                st.info("No subjects matched your search.")

        with up_division_tab:
            division_rows = fetch_divisions_manage_options()
            professor_rows = fetch_all_professors_options()

            if division_rows and professor_rows:
                division_options = {
                    f"{row['division']} - {row['subject']} ({row['professor']})": row
                    for row in division_rows
                }
                selected_div_label = st.selectbox("Division", list(division_options.keys()))
                selected_div = division_options[selected_div_label]

                professor_options = [p["name"] for p in professor_rows]
                professor_map = {p["name"]: p["id"] for p in professor_rows}
                current_professor_name = selected_div["professor"]
                default_idx = professor_options.index(current_professor_name) if current_professor_name in professor_options else 0

                with st.form("update_division_form"):
                    new_professor = st.selectbox("Professor", options=professor_options, index=default_idx)
                    up_div_submit = st.form_submit_button("💾 Update Division")

                if up_div_submit:
                    payload = {"professor_id": professor_map[new_professor]}
                    try:
                        resp = httpx.put(
                            f"{API_URL}/divisions/{int(selected_div['id'])}",
                            json=payload,
                            timeout=10,
                        )
                        if resp.status_code >= 400:
                            detail = resp.json().get("detail", "Unable to update division")
                            st.error(str(detail))
                        else:
                            st.success("Division updated successfully.")
                            fetch_divisions_join_view.clear()
                            fetch_divisions_manage_options.clear()
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Unable to update division: {exc}")
            else:
                st.info("No division/professor data available.")

    with tab_delete:
        st.subheader("⚠️ Delete Record")
        st.warning("Warning: Deletions are permanent and cannot be undone.")

        del_student_tab, del_prof_tab, del_subject_tab, del_division_tab = st.tabs(
            ["Delete Student", "Delete Professor", "Delete Subject", "Delete Division"]
        )

        with del_student_tab:
            student_df = fetch_students_view()
            if student_df.empty:
                st.info("No students available to delete.")
            else:
                student_options = {
                    f"{row['name']} ({row['enrollment_number']})": int(row["id"])
                    for _, row in student_df.iterrows()
                }
                selected_student_label = st.selectbox(
                    "Student",
                    options=list(student_options.keys()),
                    key="delete_student_select",
                )
                confirm_student_delete = st.checkbox(
                    "⚠️ I understand this will permanently delete the selected student.",
                    key="confirm_delete_student",
                )
                if st.button("🗑️ Delete Student", type="primary", key="delete_student_btn"):
                    if not confirm_student_delete:
                        st.error("Please confirm deletion first.")
                    else:
                        try:
                            resp = httpx.delete(
                                f"{API_URL}/students/{student_options[selected_student_label]}",
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to delete student")
                                st.error(str(detail))
                            else:
                                fetch_students_view.clear()
                                fetch_divisions_join_view.clear()
                                st.success("Student deleted successfully.")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to delete student: {exc}")

        with del_prof_tab:
            prof_df = fetch_professors_view()
            if prof_df.empty:
                st.info("No professors available to delete.")
            else:
                prof_options = {
                    f"{row['professor']} ({row['email']})": int(row["id"])
                    for _, row in prof_df.iterrows()
                }
                selected_prof_label = st.selectbox(
                    "Professor",
                    options=list(prof_options.keys()),
                    key="delete_professor_select",
                )
                confirm_prof_delete = st.checkbox(
                    "⚠️ I understand this will permanently delete the selected professor.",
                    key="confirm_delete_professor",
                )
                if st.button("🗑️ Delete Professor", type="primary", key="delete_professor_btn"):
                    if not confirm_prof_delete:
                        st.error("Please confirm deletion first.")
                    else:
                        try:
                            resp = httpx.delete(
                                f"{API_URL}/professors/{prof_options[selected_prof_label]}",
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to delete professor")
                                st.error(str(detail))
                            else:
                                fetch_professors_view.clear()
                                fetch_all_professors_options.clear()
                                fetch_divisions_join_view.clear()
                                fetch_divisions_manage_options.clear()
                                st.success("Professor deleted successfully.")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to delete professor: {exc}")

        with del_subject_tab:
            subj_df = fetch_subjects_view()
            if subj_df.empty:
                st.info("No subjects available to delete.")
            else:
                subject_options = {
                    f"{row['name']} ({row['subject_code']})": int(row["id"])
                    for _, row in subj_df.iterrows()
                }
                selected_subject_label = st.selectbox(
                    "Subject",
                    options=list(subject_options.keys()),
                    key="delete_subject_select",
                )
                confirm_subject_delete = st.checkbox(
                    "⚠️ I understand this will permanently delete the selected subject.",
                    key="confirm_delete_subject",
                )
                if st.button("🗑️ Delete Subject", type="primary", key="delete_subject_btn"):
                    if not confirm_subject_delete:
                        st.error("Please confirm deletion first.")
                    else:
                        try:
                            resp = httpx.delete(
                                f"{API_URL}/subjects/{subject_options[selected_subject_label]}",
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to delete subject")
                                st.error(str(detail))
                            else:
                                fetch_subjects_view.clear()
                                fetch_all_subjects_options.clear()
                                fetch_divisions_join_view.clear()
                                fetch_divisions_manage_options.clear()
                                st.success("Subject deleted successfully.")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to delete subject: {exc}")

        with del_division_tab:
            division_rows = fetch_divisions_manage_options()
            if not division_rows:
                st.info("No divisions available to delete.")
            else:
                division_options = {
                    f"{row['division']} - {row['subject']} ({row['professor']})": int(row["id"])
                    for row in division_rows
                }
                selected_division_label = st.selectbox(
                    "Division",
                    options=list(division_options.keys()),
                    key="delete_division_select",
                )
                confirm_division_delete = st.checkbox(
                    "⚠️ I understand this will permanently delete the selected division.",
                    key="confirm_delete_division",
                )
                if st.button("🗑️ Delete Division", type="primary", key="delete_division_btn"):
                    if not confirm_division_delete:
                        st.error("Please confirm deletion first.")
                    else:
                        try:
                            resp = httpx.delete(
                                f"{API_URL}/divisions/{division_options[selected_division_label]}",
                                timeout=10,
                            )
                            if resp.status_code >= 400:
                                detail = resp.json().get("detail", "Unable to delete division")
                                st.error(str(detail))
                            else:
                                fetch_divisions_join_view.clear()
                                fetch_divisions_manage_options.clear()
                                fetch_divisions_options.clear()
                                st.success("Division deleted successfully.")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"Unable to delete division: {exc}")


# Sidebar navigation
if "current_page" not in st.session_state:
    st.session_state.current_page = "ask"

with st.sidebar:
    st.title("🎓 University Agent")
    st.caption("AI-powered database assistant")
    st.divider()

    pages = [
        ("💬 Ask Agent", "ask"),
        ("🗄️ Database Explorer", "explorer"),
        ("➕ Manage Data", "manage"),
    ]

    for label, page_key in pages:
        button_type = "primary" if st.session_state.current_page == page_key else "secondary"
        if st.button(
            label,
            use_container_width=True,
            type=button_type,
            key=f"nav_{page_key}",
        ):
            if st.session_state.current_page != page_key:
                st.session_state.pop("add_step", None)
                st.session_state.pop("new_student", None)
                st.session_state.pop("selected_subjects", None)
                if "next_enrollment" in st.session_state:
                    del st.session_state["next_enrollment"]
                _reset_student_form()
            st.session_state.current_page = page_key
            st.rerun()

    st.divider()
    st.caption("Powered by GPT-4o-mini")


# Router
if st.session_state.current_page == "ask":
    render_ask_agent_page()
elif st.session_state.current_page == "explorer":
    render_database_explorer_page()
else:
    render_manage_data_page()
