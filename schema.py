import re

def extract_database_name(sql):
    """
    Extracts the target database name from the last USE statement,
    ignoring 'master' if present earlier in the script.
    """
    use_statements = re.findall(r"USE\s+([^\s;]+);", sql, flags=re.IGNORECASE)
    print(f"Found USE statements: {use_statements}")

    for db in reversed(use_statements):
        if db.lower() != "master":
            print(f"Final target database: {db}")
            return db

    print("No target database found (only master or none).")
    return None

import re

def extract_table_schema(sql_text):
    """
    Extracts table schema from CREATE TABLE statements in the SQL text.
    Returns a list of dicts: [{"database": ..., "table": ..., "columns": [[name, type, nullability, is_primary_key], ...]}, ...]
    """
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL
    )
    matches = pattern.findall(sql_text)
    extracted = []

    db_name = extract_database_name(sql_text) or "UnknownDB"
    print(f"dbname: {db_name}")

    for _, table, cols_block in matches:
        # Split columns by commas, but not inside parentheses (to avoid splitting on types like decimal(10,2))
        column_lines = re.split(r',\s*(?![^()]*\))', cols_block.strip())
        columns = []
        primary_key_columns = set()

        # First, find PRIMARY KEY inline or as constraint (at table level)
        # Extract PRIMARY KEY constraints like: PRIMARY KEY (col1, col2)
        pk_pattern = re.compile(r"PRIMARY\s+KEY\s*\((.*?)\)", re.IGNORECASE)
        pk_match = pk_pattern.search(cols_block)
        if pk_match:
            pk_cols = pk_match.group(1)
            # Clean and split pk columns
            pk_cols = [c.strip(" []`\"") for c in pk_cols.split(",")]
            primary_key_columns.update(pk_cols)

        for line in column_lines:
            line = line.strip()
            if not line:
                continue

            # Skip table constraints lines
            if re.match(r"(CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK)", line, re.IGNORECASE):
                continue

            parts = re.split(r'\s+', line, maxsplit=2)
            if len(parts) < 2:
                continue

            col_name = parts[0].strip("[]`\"")
            col_type = parts[1]

            # Try to detect NULL / NOT NULL, default to NULL if missing
            nullability = "NULL"
            # Look for NOT NULL or NULL in the remainder of line (parts[2] if exists)
            if len(parts) > 2:
                if re.search(r"NOT\s+NULL", parts[2], re.IGNORECASE):
                    nullability = "NOT NULL"
                elif re.search(r"\bNULL\b", parts[2], re.IGNORECASE):
                    nullability = "NULL"

            # Also check if PRIMARY KEY is inline on this column
            is_primary_key = col_name in primary_key_columns
            if len(parts) > 2 and re.search(r"PRIMARY\s+KEY", parts[2], re.IGNORECASE):
                is_primary_key = True
                primary_key_columns.add(col_name)  # Add if inline PK

            columns.append([col_name, col_type, nullability, is_primary_key])

        extracted.append({
            "database": db_name,
            "table": table,
            "columns": columns
        })

    return extracted


def extract_drops_from_sql(sql_text):
    """
    Parses DROP TABLE and DROP DATABASE statements from any SQL string.
    Returns a dictionary of tables and databases to remove from schema memory.
    """
    db_name = extract_database_name(sql_text) or "UnknownDB"
    drops = {"tables": [], "databases": []}

    drop_table_pattern = re.compile(
        r"DROP\s+TABLE\s+(?:\[?(\w+)\]?\.)?\[?(\w+)\]?\s*;",
        re.IGNORECASE
    )
    drop_db_pattern = re.compile(
        r"DROP\s+DATABASE\s+\[?(\w+)\]?\s*;",
        re.IGNORECASE
    )

    for db, table in drop_table_pattern.findall(sql_text):
        drops["tables"].append({
            "database": db or db_name,
            "table": table
        })

    for db in drop_db_pattern.findall(sql_text):
        drops["databases"].append(db)

    return drops
