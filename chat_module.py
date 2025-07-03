import streamlit as st
import io
import pandas as pd
import altair as alt
import re
from llm import process_query_with_llama
from memory import load_user_memory, save_user_memory, load_schema_memory, save_schema_memory
from db import query_db, get_connection
from schema import extract_table_schema, extract_drops_from_sql

@st.cache_data(ttl=300)
def get_user_db_names():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sys.databases 
        WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
    """)
    return [row[0] for row in cursor.fetchall()]

import re

def extract_databases_from_system_messages(messages):
    db_names = set()
    pattern = r"Database\s+'([^']+)'"

    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content")
            if isinstance(content, str) and "Database" in content:
                matches = re.findall(pattern, content)
                for db_name in matches:
                    db_names.add(db_name.strip())

    return sorted(db_names)

def deduplicate_columns(columns):
    counts = {}
    new_cols = []
    for col in columns:
        if col in counts:
            counts[col] += 1
            new_cols.append(f"{col}_{counts[col]}")
        else:
            counts[col] = 0
            new_cols.append(col)
    return new_cols

def show_chart(df, key_prefix=""):
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    if not numeric_cols:
        st.info("\U0001F4CA Charting disabled: No numeric columns available.")
        return

    st.markdown("### \U0001F4C8 Chart")
    chart_types = ['Line', 'Bar', 'Area', 'Scatter']
    chart_type = st.selectbox("Select chart type", chart_types, key=f"{key_prefix}_chart_type")
    x_axis = st.selectbox("Select X-axis", df.columns, key=f"{key_prefix}_xaxis")
    y_axis = st.selectbox("Select Y-axis (numeric)", numeric_cols, key=f"{key_prefix}_yaxis")

    chart = None
    if chart_type == "Line":
        chart = alt.Chart(df).mark_line().encode(x=x_axis, y=y_axis)
    elif chart_type == "Bar":
        chart = alt.Chart(df).mark_bar().encode(x=x_axis, y=y_axis)
    elif chart_type == "Area":
        chart = alt.Chart(df).mark_area().encode(x=x_axis, y=y_axis)
    elif chart_type == "Scatter":
        chart = alt.Chart(df).mark_circle(size=60).encode(x=x_axis, y=y_axis)

    if chart:
        st.altair_chart(chart.interactive(), use_container_width=True)

def run_chat_ui():
    all_db_names = get_user_db_names()
    schema_memory = load_schema_memory()
    clarified_db_names = extract_databases_from_system_messages(schema_memory)

    available_dbs = [db for db in all_db_names if db in clarified_db_names]

    if not available_dbs:
        st.sidebar.warning("⚠️ No clarified databases found. Please clarify schema first.")
        return

    st.sidebar.markdown("### \U0001F5C2️ Choose Database")
    selected_db = st.sidebar.selectbox("Select a database", available_dbs)

    if "db_name" not in st.session_state or st.session_state.db_name != selected_db:
        st.session_state.db_name = selected_db
        st.session_state.sql_result = None
        st.session_state.memory = load_user_memory(st.session_state.user_id) or []
        st.rerun()

    is_selected = bool(selected_db)

    if "memory" not in st.session_state:
        memory = load_user_memory(st.session_state.user_id) or []
        st.session_state.memory = memory[-10:]

    st.markdown(f"### \U0001F9D1 Chat as {'Admin' if st.session_state.is_admin else 'User'}")
    for msg in st.session_state.memory:
        role = "\U0001F9D1 You" if msg["role"] == "user" else "\U0001F916 Assistant"
        color = "#d7f0fa" if msg["role"] == "user" else "#e2f7e1"
        st.markdown(
            f"<div style='background-color:{color}; padding:10px; border-radius:10px; margin:5px 0'>"
            f"<b>{role}:</b> {msg['content']}</div>",
            unsafe_allow_html=True,
        )

    user_input = st.chat_input("Ask something about your database...")
    if user_input:
        reply = process_query_with_llama(
            user_input,
            st.session_state.memory,
            is_admin=st.session_state.is_admin,
            is_selecteddatabse=is_selected,
            selected_database=st.session_state.db_name
        )

        st.session_state.memory.append({"role": "user", "content": user_input})
        st.session_state.memory.append({"role": "assistant", "content": reply})
        st.session_state.memory = st.session_state.memory[-10:]
        save_user_memory(st.session_state.user_id, st.session_state.memory)
        
        if st.session_state.is_admin and any(cmd in reply.lower() for cmd in ["create table", "drop table", "delete"]):
            schema_updates = extract_table_schema(reply)
            drops_schema = extract_drops_from_sql(reply)
            if schema_updates:
                schema_mem = load_schema_memory()
                schema_mem.extend(schema_updates)
                save_schema_memory(schema_mem)
            elif drops_schema:
                drop_tables = [entry["table"] for entry in drops_schema.get("tables", [])]
                drop_dbs = drops_schema.get("databases", [])
                schema_mem = load_schema_memory()
                schema_mem = [t for t in schema_mem if t.get("table") not in drop_tables and t.get("database") not in drop_dbs]
                save_schema_memory(schema_mem)
                
        sql_keywords = ["use", "select", "insert", "update", "delete", "create", "drop"]
        if any(reply.lower().startswith(k) for k in sql_keywords):
            try:
                # sql_with_db = f"USE {st.session_state.db_name};\nGO\n{reply}"
                st.session_state.sql_result = query_db(reply)
            except Exception as e:
                st.error(f"SQL Execution Error: {e}")
                st.session_state.sql_result = None
        else:
            st.session_state.sql_result = None
        st.rerun()
    if st.session_state.get("sql_result") is not None:
        st.markdown("### \U0001F5DF SQL Result")
        result = st.session_state.sql_result

        if isinstance(result, pd.DataFrame):
            df = result.copy()
            df.columns = deduplicate_columns(df.columns)
            st.dataframe(df)
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            st.download_button("📁 Export to Excel", data=buffer.getvalue(), file_name="results.xlsx")
            with st.expander("📊 Show Chart"):
                show_chart(df, key_prefix="main")

        elif isinstance(result, (list, tuple)):
            for i, df in enumerate(result):
                if isinstance(df, pd.DataFrame):
                    st.markdown(f"#### Table {i+1}")
                    st.dataframe(df)
                    buffer = io.BytesIO()
                    df.to_excel(buffer, index=False)
                    st.download_button(f"📁 Export Table {i+1}", data=buffer.getvalue(), file_name=f"table_{i+1}.xlsx")
                    with st.expander("📊 Show Chart"):
                        show_chart(df, key_prefix=f"table_{i+1}")
                else:
                    st.write(df)
        else:
            st.success(result)
