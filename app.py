import streamlit as st
from auth import login_form, register_form, logout_button

# Initialize page state
if "page" not in st.session_state:
    st.session_state.page = "chat"

# Sidebar: Login/Register or Logout
with st.sidebar:
    if st.session_state.get("user_id"):
        st.success(f"Logged in as: {st.session_state.get('username', '')} ({'Admin' if st.session_state.get('is_admin') else 'User'})")
        logout_button()
    else:
        login_form()
        st.markdown("---")
        register_form()

# Block access if not logged in
if not st.session_state.get("user_id"):
    st.warning("⚠️ Please log in or register from the sidebar to continue.")
    st.stop()

# CSS for the header and animated underline
st.markdown(
    """
     <h1 style="
        text-align: center; 
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        color: #2196f3; 
        margin-top: 1rem; 
        margin-bottom: 0.5rem;
        font-weight: 800;
        ">
        🔍 Chat2DB — AI Database Chat Assistant
    </h1>
    <style>
    .header-container {
        display: flex;
        justify-content: center;
        gap: 3rem;
        margin: 2rem 0 1rem 0;
        position: relative;
        user-select: none;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .header-btn {
        cursor: pointer;
        background: none;
        border: none;
        font-weight: 600;
        font-size: 1.25rem;
        color: #555;
        padding: 0.75rem 2.5rem;
        border-radius: 0.5rem;
        position: relative;
        transition: color 0.25s ease;
    }
    .header-btn:hover {
        color: #2196f3;
        background: #e8f0fe;
    }
    .header-btn.selected {
        color: #2196f3;
        font-weight: 700;
    }
    .underline {
        position: absolute;
        bottom: 0;
        height: 4px;
        background-color: #2196f3;
        border-radius: 999px;
        transition: left 0.35s cubic-bezier(0.4, 0, 0.2, 1), width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        will-change: left, width;
        z-index: 10;
    }
    </style>
    """, unsafe_allow_html=True
)

# Define buttons based on user role
if st.session_state.get("is_admin"):
    btn_labels = {
        "chat": "💬 Chat",
        "admin": "🛠️ Admin Tools",
        "live_schema": "📊 Live DB Schema Import",
    }
else:
    btn_labels = {
        "chat": "💬 Chat",
    }

# Create columns dynamically based on number of buttons
num_buttons = len(btn_labels)
cols = st.columns(num_buttons)

button_width = 140  # approx width in px for buttons with padding
gap = 48  # gap between buttons approx

# Calculate left positions for underline (adjusted for fewer buttons)
left_positions = {}
for i, key in enumerate(btn_labels.keys()):
    left_positions[key] = i * (button_width + gap)

# Render buttons and handle clicks
for i, (page_key, label) in enumerate(btn_labels.items()):
    with cols[i]:
        is_selected = st.session_state.page == page_key
        btn_key = f"header_btn_{page_key}"
        if st.button(label, key=btn_key):
            # For admin-only pages, check permission (redundant here, but safe)
            if page_key in ["admin", "live_schema"] and not st.session_state.get("is_admin"):
                st.warning("⚠️ Admins only")
            else:
                st.session_state.page = page_key
                st.rerun()

# Set underline position and width dynamically
underline_left = left_positions.get(st.session_state.page, 0)
underline_style = f"left: {underline_left}px; width: {button_width}px;"

# Render underline div with CSS
st.markdown(
    f"""
    <div class="header-container" style="position:relative;">
        <div class="underline" style="{underline_style}"></div>
    </div>
    """,
    unsafe_allow_html=True
)

# Show the page content below header
if st.session_state.page == "chat":
    import chat_module
    chat_module.run_chat_ui()

elif st.session_state.page == "admin":
    if st.session_state.get("is_admin"):
        import admintools
        admintools.run_admin_tools()
    else:
        st.warning("⚠️ Admins only")

elif st.session_state.page == "live_schema":
    if st.session_state.get("is_admin"):
        import livedatabase
        livedatabase.run_live_schema_import()
    else:
        st.warning("⚠️ Admins only")
