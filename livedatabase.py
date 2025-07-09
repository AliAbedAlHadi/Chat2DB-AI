import streamlit as st
import json
from db import get_connection
from llm import process_query_with_llama
from memory import load_schema_memory, save_schema_memory, load_global_memory, save_global_memory
from summary import summarize_schema_with_llm
import re
def extract_schema_for_database(conn, db_name):
    cursor = conn.cursor()
    cursor.execute(f"USE [{db_name}]")

    cursor.execute("""
        SELECT TABLE_SCHEMA, TABLE_NAME 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE'
    """)
    tables = cursor.fetchall()

    schema = []
    for schema_name, table_name in tables:
        cursor.execute(f"""
            SELECT 
                c.COLUMN_NAME, 
                c.DATA_TYPE, 
                c.IS_NULLABLE,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_PRIMARY_KEY,
                CASE WHEN fk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_FOREIGN_KEY
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN (
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc 
                  ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                WHERE 
                    tc.TABLE_NAME = '{table_name}'
                    AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND tc.TABLE_SCHEMA = '{schema_name}'
            ) pk ON c.COLUMN_NAME = pk.COLUMN_NAME
            LEFT JOIN (
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                  ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                WHERE 
                    tc.TABLE_NAME = '{table_name}'
                    AND tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
                    AND tc.TABLE_SCHEMA = '{schema_name}'
            ) fk ON c.COLUMN_NAME = fk.COLUMN_NAME
            WHERE c.TABLE_NAME = '{table_name}' AND c.TABLE_SCHEMA = '{schema_name}'
            ORDER BY c.ORDINAL_POSITION
        """)
        columns = cursor.fetchall()

        formatted_columns = [
            [col[0], col[1], col[2], bool(col[3]), bool(col[4])] for col in columns
        ]

        schema.append({
            "database": db_name,
            "table": table_name,
            "columns": formatted_columns
        })
    return schema


def import_and_clarify_schema(db_name):
    

    if "clarification_history" not in st.session_state:
        st.session_state.clarification_history = []
    if "user_reply" not in st.session_state:
        st.session_state.user_reply = ""
    if "schema" not in st.session_state:
        conn = get_connection()
        st.session_state.schema = extract_schema_for_database(conn, db_name)

        chunks = [
            f"Table: {entry['table']}, Columns: {', '.join([f'{col[0]} ({col[1]})' for col in entry['columns']])}"
            for entry in st.session_state.schema
        ]
        st.session_state.schema_summary = summarize_schema_with_llm(chunks, db_name)

        model_input = f"""
You are a database expert reviewing a summarized schema for the database `{db_name}`.

Summary:

{st.session_state.schema_summary}

Instructions:
- ONLY ask clarification questions.
- DO NOT generate SQL or mention queries.
- Focus on vague table purposes, ambiguous column names, unclear relationships.
- If everything is clear, say exactly:

    Schema looks good
""".strip()

        st.session_state.model_response = process_query_with_llama(
            model_input,
            user_memory=[],
            is_admin=True,
            is_selecteddatabse=False
        )
        st.session_state.last_model_question = st.session_state.model_response.strip()

    st.markdown(f"### 🧠 Model Clarification for `{db_name}`")

    for entry in st.session_state.clarification_history:
        st.markdown(f"**Model:** {entry['q']}")
        st.markdown(f"**Admin:** {entry['a']}")

    st.markdown(f"**Model asks:** {st.session_state.model_response.strip()}")

    if "schema looks good" in st.session_state.model_response.lower():
        if st.button(f"✅ Save schema for `{db_name}`"):
            existing_schemas = load_schema_memory()
            updated_schemas = [s for s in existing_schemas if s.get("database") != db_name]
            updated_schemas.extend(st.session_state.schema)
            save_schema_memory(updated_schemas)

            clarification_block = "\n\n".join(
                f"Model: {entry['q']}\nAdmin: {entry['a']}" for entry in st.session_state.clarification_history
            )

            memory = load_global_memory()
            memory.append({
                "role": "admin",
                "content": (
                    f"[#clarification]\nDatabase: {db_name}\n{clarification_block}\n\n[#summary]\n{st.session_state.schema_summary}"
                )
            })
            save_global_memory(memory)

            st.success(f"✅ Schema, summary, and clarification saved for `{db_name}`!")
            for key in ["model_response", "user_reply", "schema", "schema_summary", "clarification_history", "last_model_question"]:
                st.session_state.pop(key, None)
    else:
        user_input = st.text_area("✏️ Your answer to the model:", value=st.session_state.user_reply)
        if st.button("Submit answer"):
            if user_input.strip():
                st.session_state.clarification_history.append({
                    "q": st.session_state.get("last_model_question", ""),
                    "a": user_input.strip()
                })
                clarification_block = "\n\n".join(
                    f"Model: {entry['q']}\nAdmin: {entry['a']}" for entry in st.session_state.clarification_history
                )
                followup_prompt = f"Database: {db_name}\n\nClarification History:\n{clarification_block}\n\nContinue with the schema clarification as needed."
                st.session_state.model_response = process_query_with_llama(
                    followup_prompt,
                    user_memory=[],
                    is_admin=True,
                    is_selecteddatabse=False
                )
                st.session_state.last_model_question = st.session_state.model_response.strip()
                st.session_state.user_reply = ""
                st.rerun()


def run_live_schema_import():
    conn = get_connection()
    db_names = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sys.databases 
            WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
        """)
        db_names = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        st.error(f"Error fetching databases: {e}")
        return

    # Load existing schema memory and extract database names
    existing_schemas = load_schema_memory()
    imported_db_names = set()
    for entry in existing_schemas:
        if "content" in entry:
            match = re.search(r"Database\s+'([^']+)'", entry["content"])
            if match:
                imported_db_names.add(match.group(1))

    # Filter out databases that are already in schema memory
    available_dbs = [db for db in db_names if db not in imported_db_names]

    if not available_dbs:
        st.sidebar.info("✅ All available databases have been imported.")
        return

    st.sidebar.markdown("## Select Database")
    selected_db = st.sidebar.selectbox("Choose a database to import schema", available_dbs)

    if selected_db:
        if "db_name" not in st.session_state or st.session_state.db_name != selected_db:
            st.session_state.db_name = selected_db
            for key in ["schema", "model_response", "user_reply", "schema_summary", "clarification_history", "last_model_question"]:
                st.session_state.pop(key, None)

        import_and_clarify_schema(selected_db)
