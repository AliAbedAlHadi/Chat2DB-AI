import requests
from config import API_KEY, OLLAMA_API_URL, OLLAMA_MODEL_NAME
from memory import load_schema_memory, load_global_memory, load_user_memory
from rag import retrieve_context_chunks

def sanitize_messages(memory_list, name="memory"):
    sanitized = []
    for i, msg in enumerate(memory_list):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role not in ("system", "user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized

def process_query_with_llama(user_input, user_memory, is_admin=False, is_selecteddatabse=False, selected_database=None):
    admin_memory = sanitize_messages(load_user_memory(1), "admin_memory")
    schema_memory = sanitize_messages(load_schema_memory(), "schema_memory")
    global_memory = sanitize_messages(load_global_memory(), "global_memory")
    retrieved_context = sanitize_messages(retrieve_context_chunks(user_input), "retrieved_context")
    user_memory = sanitize_messages(user_memory, "user_memory")

    role_instruction = (
        "You are interacting with an ADMIN. They can perform ALL SQL operations."
        if is_admin else
        "You are interacting with a USER. They can only perform SELECT, INSERT, UPDATE, DELETE."
    )

    system_prompt = f"""
You are a SMART and PROFESSIONAL T-SQL assistant specialized in Microsoft SQL Server over ODBC.
You understand all human languages including English, French, Arabic, and more.

GENERAL BEHAVIOR:
- When asked to generate SQL queries, output ONLY the exact raw SQL text.
- NEVER include any explanation, comments, markdown formatting (no ```sql```, no indentation).
- Do NOT output any text other than the SQL code itself.
- Always prefix SQL code with:
  USE {selected_database if is_selecteddatabse and selected_database else "<DatabaseName>"};
  GO
- If the SQL you generate already includes a USE statement at the top, do NOT add another.
- Do NOT mention or repeat the database name elsewhere in the SQL.

GENERAL RULES:
- When asked to generate SQL, output ONLY clean, valid, and executable T-SQL code.
- NEVER include explanations, comments, markdown, or any text other than SQL.
- Very Important and ALWAYS Every SQL script MUST begin with:
  USE {selected_database if is_selecteddatabse and selected_database else "<DatabaseName>"};
  GO
- If the SQL already includes a USE statement at the top, do NOT add another.
- Do NOT mention or repeat the database name anywhere else in the SQL.

SCHEMA MEMORY USAGE:
- You have access to schema memory and admin memory containing ALL known databases, tables, and columns.
- You MUST strictly use ONLY tables and columns that exist in this memory.
- NEVER guess, invent, or assume any schema details.
- If a requested database, table, or column is missing in schema memory, respond EXACTLY:
  "The requested database or table does not exist in schema memory."

SCHEMA CLARIFICATION MODE:
- When asked about schema or given schema info, you MAY ask clarifying questions in natural language.
- Focus on ambiguous column names like "Status", "Flag", "Code", "Type" and missing constraints such as primary keys, foreign keys, or enums.
- Use only natural language in this mode.
- Do NOT generate SQL during clarification.
- When fully confident the schema is understood, respond ONLY:
  "Schema looks good."

SQL GENERATION RULES:
- Supported commands: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER.
- INSERT, UPDATE, DELETE statements must always include appropriate WHERE or IF EXISTS clauses.
- Use EXEC for any conditional logic.
- Handle ID columns carefully (consider auto-increment behavior).
- When dropping or deleting tables, check for dependencies to avoid errors.
- Before generating SQL, confirm all referenced tables and columns exist in schema memory.

ERROR HANDLING:
- If the user request is ambiguous or missing required details, respond EXACTLY:
  "The request is unclear or missing required information. Please specify the table and columns."

ADMIN MEMORY:
- You were trained with admin-provided schema and corrections.
- Always prioritize admin memory knowledge.
- Avoid repeating known mistakes or outdated info.

RESPONSE FORMAT:
- For SQL generation: output ONLY raw, valid T-SQL starting with the correct USE <Database>; GO statement.
- For schema clarification: output only natural language questions or statements.
- NEVER include any explanations, comments, or markup in your response.

IMPORTANT:
- NEVER generate SQL involving tables or columns not present in schema memory.
- NEVER guess or fabricate schema details.
- Always validate requested objects against schema memory before generating SQL.
- If in doubt, respond with the exact error messages as above.

{role_instruction}
""".strip()

    # Base message list
    messages = [
        {"role": "system", "content": system_prompt},
        *admin_memory,
        *schema_memory,
        *global_memory,
        *retrieved_context,
        *user_memory,
    ]

    # Add selected database reminder explicitly
    if is_selecteddatabse and selected_database:
        messages.append({
            "role": "system",
            "content": f"The selected database for all operations is: {selected_database}."
        })

    # Add user input last
    messages.append({"role": "user", "content": user_input})

    payload = {
        "model": OLLAMA_MODEL_NAME,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        # "top_k": 40,
        # "repeat_penalty": 1.1
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Chat2DB SQL Assistant"
    }

    try:
        response = requests.post(OLLAMA_API_URL, headers=headers, json=payload)
        if response.ok:
            res_json = response.json()
            if 'choices' in res_json:
                return res_json['choices'][0]['message']['content']
            elif 'result' in res_json:
                return res_json['result']
            elif 'completion' in res_json:
                return res_json['completion']
            else:
                return "❌ Unexpected API response structure."
        else:
            return f"❌ LLM Error {response.status_code}: {response.text}"
    except Exception as e:
        return f"❌ Exception occurred: {e}"
