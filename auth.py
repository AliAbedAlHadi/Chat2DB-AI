# auth.py

import uuid
import streamlit as st
from memory import load_users, save_users, load_user_memory

def login_form():
    st.header("🔐 Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        users = load_users()
        for uid, user in users.items():
            if user["username"] == username and user["password"] == password:
                st.session_state.user_id = uid
                st.session_state.username = user["username"]
                st.session_state.is_admin = user["role"] == "admin"
                st.session_state.memory = (load_user_memory(uid) or [])[-10:]
                st.success(f"Welcome, {username}!")
                st.rerun()
                return
        st.error("❌ Invalid username or password.")

def register_form():
    st.header("🆕 Register (Users Only)")
    with st.form("register_form"):
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        submitted = st.form_submit_button("Register")

    if submitted:
        users = load_users()
        if any(u["username"] == new_username for u in users.values()):
            st.warning("⚠️ Username already exists. Choose another.")
        else:
            new_id = str(uuid.uuid4())
            users[new_id] = {
                "username": new_username,
                "password": new_password,
                "role": "user"
            }
            save_users(users)
            st.success("✅ Registration successful. Please log in.")

def logout_button():
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def is_authenticated():
    return "user_id" in st.session_state
