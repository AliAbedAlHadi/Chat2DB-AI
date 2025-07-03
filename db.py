import pyodbc
import re
import pandas as pd
from config import DB_SERVER, USE_WINDOWS_AUTH

def get_connection():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"{'Trusted_Connection=yes;' if USE_WINDOWS_AUTH else ''}"
    )
    return pyodbc.connect(conn_str, autocommit=True)
def split_sql_batches(query):
    # Step 1: First split by GO
    raw_batches = re.split(r'^\s*GO\s*$', query, flags=re.IGNORECASE | re.MULTILINE)

    final_batches = []
    crud_pattern = re.compile(r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b', re.IGNORECASE)

    for batch in raw_batches:
        lines = batch.strip().splitlines()
        current_stmt = []
        for line in lines:
            if crud_pattern.match(line) and current_stmt:
                final_batches.append('\n'.join(current_stmt).strip())
                current_stmt = [line]
            else:
                current_stmt.append(line)
        if current_stmt:
            final_batches.append('\n'.join(current_stmt).strip())

    return [stmt for stmt in final_batches if stmt]

def query_db(query):
    conn = get_connection()
    cursor = conn.cursor()
    # Normalize GO
    query = re.sub(r'(?<!\n)(?<!\r)\bGO\b', r'\nGO', query, flags=re.IGNORECASE)
    batches = split_sql_batches(query)
    batches = [b.strip() for b in batches if b.strip()]

    results = []

    try:
        # Handle initial USE statement
        if batches and batches[0].lower().startswith("use "):
            cursor.execute(batches[0])
            batches = batches[1:]

        for batch in batches:
            cursor.execute(batch)

            if batch.lower().startswith("select"):
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                clean_rows = [tuple(r) for r in rows]
                df = pd.DataFrame(clean_rows, columns=columns)
                results.append(df)
            else:
                conn.commit()

        if results:
            return results[0] if len(results) == 1 else results
        else:
            return "✅ Query executed successfully."

    except Exception as e:
        return str(e)
