from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st
        value = st.secrets.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def is_configured(name: str) -> bool:
    return bool(get_setting(name, "").strip())
