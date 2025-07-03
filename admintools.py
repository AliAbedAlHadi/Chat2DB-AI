import streamlit as st
import pandas as pd
from memory import load_schema_memory, save_schema_memory, load_global_memory, save_global_memory
from llm import process_query_with_llama
from db import query_db
from schema import extract_table_schema, extract_drops_from_sql
from utils.vector import ingest_file

def run_admin_tools():
    if not st.session_state.is_admin:
        st.error("🚫 Access denied: Admins only.")
        return

    st.markdown("### 🛠️ Admin Tools")

    uploaded_file = st.file_uploader("Upload PDF/CSV/TXT/JSON/Images/BAK", type=['pdf', 'csv', 'txt', 'json', 'png', 'jpg', 'jpeg','bak'])

    if uploaded_file and not st.session_state.get("pending_schema_suggestion"):
        ingest_file(uploaded_file, st.session_state.user_id)    
        uploaded_file.seek(0)
        content = ""
        try:
            if uploaded_file.type.startswith("text") or uploaded_file.name.endswith((".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".json", ".bak")):
                content = uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception:
            content = ""

        clarification_prompt = (
            f"Here is some uploaded content:\n{content}\n\n"
            "Before generating SQL, carefully review the uploaded content.\n"
            "It may contain schema definitions, or examples of INSERT, DELETE, or UPDATE operations.\n"
            "Clearly identify what type of content has been uploaded (e.g., schema structure, CRUD examples).\n\n"
            "Always Ask clarifying questions to confirm the structure and relationships of the tables, especially if:\n"
            "- Table names are represented as symbols or unclear labels (ask what each symbol represents).\n"
            "- The relationships between tables are not obvious (ask about foreign keys or related tables).\n\n"
            "Finally, ask the admin to confirm whether the uploaded content is correct and complete before generating SQL."
        )

        clarification_msg = process_query_with_llama(clarification_prompt, st.session_state.memory, is_admin=True,is_selecteddatabse=False)

        st.session_state.pending_schema_suggestion = {
            "filename": uploaded_file.name,
            "raw_content": content,
            "clarification_msg": clarification_msg,
            "clarified_content": "",
            "confirmed": False,
            "executed": False,
            "final_sql": ""
        }
        st.session_state.clarification_stage = True
        st.rerun()

    pending = st.session_state.get("pending_schema_suggestion")
    if pending and st.session_state.get("clarification_stage"):
        st.markdown("### 🤖 Clarification Questions")
        st.markdown(f"**File:** `{pending['filename']}`")
        st.markdown(f"**Model asks:** {pending['clarification_msg']}")
        clarified = st.text_area("✍️ Your Answer / Clarification:", value=pending.get("clarified_content", ""))
        if st.button("Submit Clarification"):
            st.session_state.pending_schema_suggestion["clarified_content"] = clarified
            st.session_state.clarification_stage = False
            st.rerun()

    if pending and not st.session_state.get("clarification_stage") and not pending.get("confirmed"):
        if st.button("✅ Confirm to Generate SQL"):
            db_name = st.session_state.db_name or "YourDatabase"
            final_prompt = (
                "Based on this clarification:\n"
                f"{pending['clarified_content']}\n\n"
                "And this content:\n"
                f"{pending['raw_content']}\n\n"
                "Generate clean, valid, and executable T-SQL code according to these strict rules:\n\n"
                "1. Start by switching to the master database:\n"
                "   USE master;\n"
                "   GO\n\n"
                f"2. Check if the database '{db_name}' exists. If not, create it using:\n"
                f"   IF DB_ID(N'{db_name}') IS NULL\n"
                f"       EXEC('CREATE DATABASE {db_name}');\n"
                "   GO\n\n"
                f"3. Switch to the newly created or existing database:\n"
                f"   USE {db_name};\n"
                "   GO\n\n"
                "4. For each table to be created:\n"
                "   - Check if it exists using:\n"
                "       IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'<TableName>')\n"
                "   - If it does not exist, create it using EXEC with the full CREATE TABLE statement as a string:\n"
                "       EXEC('CREATE TABLE <TableName>(<Column1> <Type>, <Column2> <Type>, ...)');\n"
                "   GO\n\n"
                "5. Do NOT use BEGIN ... END blocks at any point.\n"
                "6. For INSERT, UPDATE, or DELETE:\n"
                "   - Use standard T-SQL with IF EXISTS / IF NOT EXISTS where needed.\n"
                "   - Do NOT wrap DML statements inside EXEC.\n\n"
                "7. Always separate logical blocks using GO.\n"
                "8. Output only the raw executable T-SQL code:\n"
                "   - No comments\n"
                "   - No markdown\n"
                "   - No explanations\n"
                "   - No phrases like 'Here is your code'\n\n"
                "9. Only produce the T-SQL code based on the provided content and clarification. Do not assume or fabricate any structure.\n"
            )

            final_sql = process_query_with_llama(final_prompt, st.session_state.memory, is_admin=True,is_selecteddatabse=False)
            st.session_state.pending_schema_suggestion["final_sql"] = final_sql.strip()
            st.session_state.pending_schema_suggestion["confirmed"] = True
            st.rerun()

    if pending and pending.get("confirmed"):
        st.subheader("✅ Final SQL")
        st.code(pending["final_sql"], language="sql")

        if not pending.get("executed"):
            if st.button("▶️ Execute SQL"):
                try:
                    result = query_db(pending["final_sql"])
                    if result is not None:
                        if isinstance(result, pd.DataFrame):
                            st.dataframe(result)
                        else:
                            st.text(str(result))

                        extracted_schema = extract_table_schema(pending["final_sql"])
                        drops_schema = extract_drops_from_sql(pending["final_sql"])

                        if extracted_schema:
                            current_schema_mem = load_schema_memory()
                            current_schema_mem.extend(extracted_schema)
                            save_schema_memory(current_schema_mem)

                            # 🔥 Save clarification to global memory
                            memory = load_global_memory()
                            memory.append({
                                "role": "admin",
                                "content": (
                                    f"[#clarification]\nDatabase: {st.session_state.db_name}\n"
                                    f"File: {pending['filename']}\n"
                                    f"Clarification:\n{pending['clarified_content']}\n"
                                    f"Generated SQL:\n{pending['final_sql']}"
                                )
                            })
                            save_global_memory(memory)

                        elif drops_schema:
                            drop_tables = [entry["table"] for entry in drops_schema.get("tables", [])]
                            drop_dbs = drops_schema.get("databases", [])
                            current_schema_mem = load_schema_memory()
                            current_schema_mem = [
                                t for t in current_schema_mem
                                if t.get("table") not in drop_tables and t.get("database") not in drop_dbs
                            ]
                            save_schema_memory(current_schema_mem)

                        st.session_state.pending_schema_suggestion["executed"] = True
                        st.success("✅ SQL executed and schema created.")
                        st.session_state.pending_schema_suggestion = None
                except Exception as e:
                    st.error(f"SQL Execution Error: {e}")
            else:
                st.warning("⚠️ Review the SQL carefully before executing.")
