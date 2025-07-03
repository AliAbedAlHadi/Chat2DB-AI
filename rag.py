import os
import tempfile
from langchain.vectorstores import FAISS
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.document_loaders import PyMuPDFLoader
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import VECTOR_DB_FOLDER
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
embedding = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

vectorstore = None
if os.path.exists(VECTOR_DB_FOLDER):
    vectorstore = FAISS.load_local(VECTOR_DB_FOLDER, embedding)

def ingest_documents(files):
    global vectorstore
    docs = []

    for file in files:
        try:
            suffix = os.path.splitext(file.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(file.read())
                tmp_path = tmp_file.name

            loader = None
            if suffix.lower() == ".pdf":
                loader = PyMuPDFLoader(tmp_path)
            elif suffix.lower() in (".json", ".txt", ".csv"):
                loader = UnstructuredFileLoader(tmp_path)  # updated here
            elif suffix.lower() == ".bak":
                print(f"Warning: .bak file '{file.name}' detected. Please handle SQL Server backup separately.")
                os.unlink(tmp_path)
                continue
            else:
                print(f"Warning: Unsupported file type '{suffix}' for file '{file.name}'. Skipping.")
                os.unlink(tmp_path)
                continue

            raw_docs = loader.load()
            docs.extend(text_splitter.split_documents(raw_docs))

            os.unlink(tmp_path)

        except Exception as e:
            print(f"Error processing file {file.name}: {e}")

    if docs:
        if vectorstore is None:
            vectorstore = FAISS.from_documents(docs, embedding)
        else:
            vectorstore.add_documents(docs)
        vectorstore.save_local(VECTOR_DB_FOLDER)

def retrieve_context_chunks(query, max_tokens=1000):
    """
    Retrieve top-k most similar chunks for a given query from vectorstore,
    limiting total tokens across all chunks.
    """
    if not vectorstore:
        return []

    try:
        # Increase k to 30 for more candidates
        results = vectorstore.similarity_search(query, k=30)
        context_chunks = []
        total_tokens = 0

        for r in results:
            chunk_text = r.page_content
            chunk_tokens = len(tokenizer.encode(chunk_text, add_special_tokens=False))

            if total_tokens + chunk_tokens > max_tokens:
                # Skip this chunk, but continue to see if smaller chunks are ahead
                continue

            context_chunks.append({"role": "system", "content": chunk_text})
            total_tokens += chunk_tokens

            if total_tokens >= max_tokens:
                break

        print(f"Retrieved {len(context_chunks)} chunks, total tokens: {total_tokens}")
        return context_chunks

    except Exception as e:
        print(f"Error retrieving context chunks: {e}")
        return []
