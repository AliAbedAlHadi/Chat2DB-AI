import os
import re
import tempfile
import time
import traceback
import streamlit as st
import pytesseract
from PIL import Image

from langchain.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    JSONLoader,
    CSVLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document

from chromadb import PersistentClient
from chromadb.utils.embedding_functions import EmbeddingFunction


# Wrapper to adapt Langchain embedder to Chroma interface
class LangchainEmbeddingWrapper(EmbeddingFunction):
    def __init__(self, embedder):
        self.embedder = embedder

    def __call__(self, texts):
        return self.embedder.embed_documents(texts)


# Langchain embedder
embedder = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    encode_kwargs={"batch_size": 64}
)
wrapped_embedder = LangchainEmbeddingWrapper(embedder)


def get_loader(file_path, ext):
    if ext == ".pdf":
        return PyMuPDFLoader(file_path)
    elif ext in [".txt", ".md"]:
        return TextLoader(file_path, encoding="utf-8")
    elif ext == ".json":
        return JSONLoader(file_path)
    elif ext == ".csv":
        return CSVLoader(file_path)
    elif ext in [".html", ".xml", ".pptx", ".xlsx", ".ppt", ".xls"]:
        try:
            from langchain_community.document_loaders import UnstructuredFileLoader
            return UnstructuredFileLoader(file_path)
        except ImportError:
            st.warning("Install `langchain-unstructured` for more file types.")
            return None
    else:
        return None


def extract_text_from_image(image_path):
    try:
        image = Image.open(image_path)
        return pytesseract.image_to_string(image)
    except Exception as e:
        return f"Failed to process image: {e}"


def extract_text_from_bak(file_path):
    try:
        with open(file_path, "rb") as f:
            binary = f.read()
        matches = re.findall(rb"[ -~]{3,}", binary)
        return "\n".join(m.decode("utf-8", errors="ignore") for m in matches)
    except Exception as e:
        return f"Failed to extract text from .bak: {e}"


def ingest_file(file, user_id):
    tmp_path = None
    vector_store_name = f"user_{user_id}_collection"
    vector_store_dir = f"./vector_store/{user_id}"

    try:
        os.makedirs(vector_store_dir, exist_ok=True)

        suffix = os.path.splitext(file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        ext = suffix.lower()
        docs = []

        if ext in [".jpg", ".jpeg", ".png"]:
            text = extract_text_from_image(tmp_path)
            if not text.strip() or text.startswith("Failed"):
                st.error("❌ No text could be extracted from the image.")
                return
            docs = [Document(page_content=text)]

        elif ext == ".bak":
            text = extract_text_from_bak(tmp_path)
            if not text.strip() or text.startswith("Failed"):
                st.error("❌ No readable text found in the .bak file.")
                return
            docs = [Document(page_content=text)]

        else:
            loader = get_loader(tmp_path, ext)
            if loader is None:
                st.error(f"❌ Unsupported file type: {ext}")
                return
            try:
                docs = loader.load()
            except Exception as e:
                st.error(f"❌ Error loading document: {e}")
                return

        if not docs:
            st.error("❌ No documents loaded.")
            return

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)
        start_split = time.time()
        chunks = splitter.split_documents(docs)
        end_split = time.time()
        st.info(f"📄 Split into {len(chunks)} chunks in {end_split - start_split:.2f} sec")

        if not chunks:
            st.error("❌ Splitting failed: no chunks produced.")
            return

        # Connect to Chroma
        client = PersistentClient(path=vector_store_dir)

        try:
            if vector_store_name in [c.name for c in client.list_collections()]:
                client.delete_collection(vector_store_name)
                del client
                time.sleep(0.5)
                client = PersistentClient(path=vector_store_dir)
        except Exception as e:
            st.warning(f"⚠️ Could not delete old collection: {e}")

        # Create collection
        collection = client.create_collection(
            name=vector_store_name,
            embedding_function=wrapped_embedder
        )

        documents = [chunk.page_content for chunk in chunks]
        metadatas = [{"source": file.name} for _ in documents]
        ids = [f"{vector_store_name}_{i}" for i in range(len(documents))]

        start_embed = time.time()
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        end_embed = time.time()
        st.success(f"✅ Ingested {len(documents)} chunks in {end_embed - start_embed:.2f} sec.")

    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
        st.text(traceback.format_exc())

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception as e:
                st.warning(f"⚠️ Could not delete temp file: {e}")
