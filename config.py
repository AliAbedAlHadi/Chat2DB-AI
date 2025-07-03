import os
from dotenv import load_dotenv

load_dotenv()

DB_SERVER = os.getenv("DB_SERVER")
USE_WINDOWS_AUTH = os.getenv("USE_WINDOWS_AUTH", "true").lower() == "true"
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME")
API_KEY = os.getenv("LLAMA_API_KEY")
USERS_FILE = "users.json"
SCHEMA_MEMORY_FILE = "schema_memory.json"
GLOBAL_MEMORY_FILE = "global_memory.json"
UPLOAD_FOLDER = "uploads"
VECTOR_DB_FOLDER = "vector_db"
