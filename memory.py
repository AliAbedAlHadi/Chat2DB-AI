import os
import json
from config import USERS_FILE, SCHEMA_MEMORY_FILE, GLOBAL_MEMORY_FILE

def load_global_memory():
    if os.path.exists(GLOBAL_MEMORY_FILE):
        with open(GLOBAL_MEMORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_global_memory(memory):
    with open(GLOBAL_MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_user_memory(user_id):
    path = f"memory_{user_id}.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_user_memory(user_id, memory):
    with open(f"memory_{user_id}.json", "w") as f:
        json.dump(memory, f, indent=2)



def load_schema_memory_raw():
    """Load the raw schema memory JSON file as-is (no parsing/modification)."""
    try:
        with open(SCHEMA_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def convert_schema_to_messages(schema_json):
    messages = []
    seen_tables = set()

    for entry in schema_json:
        db = entry.get("database", "").strip()
        table = entry.get("table", "").strip()
        if not db or not table:
            continue
        key = (db.lower(), table.lower())
        if key in seen_tables:
            continue
        seen_tables.add(key)

        columns = entry.get("columns", [])
        cols_formatted_list = []
        for col in columns:
            # Support extended info: [name, type, nullability, primary_key, foreign_key]
            col_name = col[0]
            col_type = col[1]
            nullability = "NULL"
            primary_key = False
            foreign_key = None

            if len(col) > 2 and col[2] is not None:
                nullability = col[2]
            if len(col) > 3 and col[3] is True:
                primary_key = True
            if len(col) > 4:
                foreign_key = col[4]

            col_desc = f"- {col_name} ({col_type}, {nullability}"
            if primary_key:
                col_desc += ", PRIMARY KEY"
            if foreign_key:
                col_desc += f", FOREIGN KEY to {foreign_key}"
            col_desc += ")"

            cols_formatted_list.append(col_desc)

        content = f"Database '{db}' has table '{table}' with columns:\n" + "\n".join(cols_formatted_list)
        messages.append({"role": "system", "content": content})

    return messages

def load_schema_memory():
    raw_schema = load_schema_memory_raw()
    return convert_schema_to_messages(raw_schema)

def save_schema_memory(new_entries):
    """
    Saves new schema entries to the schema memory file, avoiding duplicates.
    Each entry must have a 'database' and 'table' key.
    """
    raw_memory = load_schema_memory_raw()

    if not isinstance(new_entries, list):
        new_entries = [new_entries]

    # Set of (database, table) to check for duplicates
    existing_keys = {
        (entry.get("database", "").lower(), entry.get("table", "").lower())
        for entry in raw_memory
    }

    for entry in new_entries:
        db = entry.get("database", "").lower()
        table = entry.get("table", "").lower()

        # Optional: normalize columns (sort alphabetically by column name)
        if "columns" in entry and isinstance(entry["columns"], list):
            entry["columns"] = sorted(entry["columns"], key=lambda col: col[0].lower())

        if (db, table) not in existing_keys:
            raw_memory.append(entry)
            existing_keys.add((db, table))

    # Save back to file
    with open(SCHEMA_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_memory, f, indent=2, ensure_ascii=False)
