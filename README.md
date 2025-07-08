# Chat2DB-AI 💬🔍

Chat2DB-AI is a smart, customizable, and locally hosted AI assistant that lets users interact with a **Microsoft SQL Server** database using natural language. It uses **LLMs (like Ollama's DeepSeek)** to generate valid T-SQL queries, supports **admin/user roles**, **schema memory**, and **Streamlit UI** — all without exposing your database.

---

## 🔥 Key Features

- 🧠 **Natural Language to SQL** (CRUD support)
- 👨‍💼 **Role-Based Access** (Admin = full access, User = read-only)
- 💾 **Schema Memory** (permanent global memory and per-user memory)
- 📥 **Admin Upload Mode**: Supports PDF, JSON, .bak files for schema/RAG
- 💬 **Streamlit Chat Interface** with chat history
- 🧠 **Ollama Integration** (DeepSeek model used locally)
- 🔐 **Login System** with secure ID, username, and password
- 📊 **Excel Export**, insights, and chart-ready queries

---

## 🧱 Tech Stack

| Layer       | Tools Used                          |
|-------------|-------------------------------------|
| UI          | Streamlit                           |
| Backend     | Python, FastAPI (optional)          |
| AI Engine   | Ollama (LLMs), DeepSeek R1          |
| DB          | Microsoft SQL Server (local)        |
| Memory      | JSON files (for schema & chat)      |
| RAG Support | ChromaDB, LangChain (optional)      |

---

## 🚀 Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/AliAbedAlHadi/Chat2DB-AI.git
cd Chat2DB-AI

