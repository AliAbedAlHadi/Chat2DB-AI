import streamlit as st
import chromadb
from chromadb.utils import embedding_functions
from db import get_connection  # Your DB connection module
from llm import process_query_with_llama  # Your LLM query function

# Constants
CHUNK_COLLECTION_NAME = "schema_chunks"
EMBED_MODEL = "all-MiniLM-L6-v2"
BATCH_SIZE = 25  # Number of tables to summarize per batch

# Initialize ChromaDB client
chroma_client = chromadb.Client()
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
collection = chroma_client.get_or_create_collection(name=CHUNK_COLLECTION_NAME, embedding_function=embedding_fn)


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
            SELECT COLUMN_NAME, DATA_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{table_name}' AND TABLE_SCHEMA = '{schema_name}'
        """)
        columns = cursor.fetchall()
        schema.append({
            "database": db_name,
            "table": table_name,
            "columns": [[col[0], col[1]] for col in columns]
        })
    return schema


def chunk_schema(schema, db_name):
    chunks = []
    for entry in schema:
        table = entry["table"]
        column_str = ", ".join([f"{col[0]} ({col[1]})" for col in entry["columns"]])
        text = f"Database: {db_name}\nTable: {table}\nColumns: {column_str}"
        chunks.append(text)
    return chunks


def embed_and_store(chunks, db_name):
    # Delete the collection if exists to refresh
    try:
        chroma_client.delete_collection(name=CHUNK_COLLECTION_NAME)
    except Exception:
        pass  # Ignore if doesn't exist

    # Recreate collection with embedding function
    global collection
    collection = chroma_client.get_or_create_collection(
        name=CHUNK_COLLECTION_NAME,
        embedding_function=embedding_fn
    )

    ids = [f"{db_name}_{i}" for i in range(len(chunks))]
    collection.add(documents=chunks, ids=ids, metadatas=[{"database": db_name}] * len(chunks))
    return ids


def retrieve_chunks(db_name, top_k=30):
    results = collection.query(query_texts=[f"Schema for {db_name}"], n_results=top_k)
    if results and "documents" in results:
        return results["documents"][0]
    return []


def batch_chunks(chunks, batch_size=BATCH_SIZE):
    for i in range(0, len(chunks), batch_size):
        yield chunks[i:i+batch_size]


def summarize_schema_with_llm(chunks, db_name):
    batch_summaries = []

    for batch_num, batch in enumerate(batch_chunks(chunks), 1):
        st.info(f"🔄 Summarizing batch {batch_num} with {len(batch)} tables...")
        batch_text = "\n\n".join(batch)

        prompt = f"""
You are a professional database expert.

Below are the columns for several tables in the `{db_name}` database:

{batch_text}

Summarize what these tables likely store based ONLY on the column names and types.
Return only the summary.
""".strip()

        summary = process_query_with_llama(prompt, user_memory=[], is_admin=True, is_selecteddatabse=False)
        batch_summaries.append(summary)

    # Combine batch summaries for a final overview
    combined_summaries = "\n".join(batch_summaries)

    final_prompt = f"""
You are a professional database expert.

Here are summaries of batches of tables in the `{db_name}` database:

{combined_summaries}

Write a concise overall summary of what this database is for, its key components, and how its tables might relate.
Limit to 200 words. Return only the summary.
""".strip()

    final_summary = process_query_with_llama(final_prompt, user_memory=[], is_admin=True, is_selecteddatabse=False)
    return final_summary


def run_summary_app():
    st.title("📘 Schema Summary & Embedding")

    # Step 1: Select DB
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sys.databases 
        WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb')
    """)
    db_names = [row[0] for row in cursor.fetchall()]
    db_name = st.selectbox("Select a database", db_names)

    if st.button("🔍 Extract, Embed & Summarize Schema"):
        # Step 2: Extract
        schema = extract_schema_for_database(conn, db_name)
        st.success("✅ Schema extracted")

        # Step 3: Chunk
        chunks = chunk_schema(schema, db_name)
        st.info(f"🧩 Chunked into {len(chunks)} entries")

        # Step 4: Embed & Store
        ids = embed_and_store(chunks, db_name)
        st.success(f"📦 {len(ids)} chunks embedded and stored in ChromaDB")

        # Step 5: Retrieve chunks for summarization
        retrieved_chunks = retrieve_chunks(db_name, top_k=len(chunks))

        # Step 6: Summarize batches
        final_summary = summarize_schema_with_llm(retrieved_chunks, db_name)

        # Step 7: Display final summary
        st.markdown("### 📄 Final Database Summary")
        st.markdown(final_summary)
