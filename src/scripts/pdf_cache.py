"""Helpers for stable Streamlit PDF downloads."""

from collections.abc import Callable, Hashable

import streamlit as st


def clear_pdf_cache(prefix: str) -> None:
    """Clear cached PDF bytes for a tab/report prefix."""
    st.session_state.pop(f"_{prefix}_pdf_key", None)
    st.session_state.pop(f"_{prefix}_pdf_bytes", None)


def cached_pdf_bytes(prefix: str, key: Hashable, build_fn: Callable[[], bytes]) -> bytes:
    """Return cached PDF bytes, rebuilding only when ``key`` changes."""
    key_name = f"_{prefix}_pdf_key"
    bytes_name = f"_{prefix}_pdf_bytes"
    if st.session_state.get(key_name) != key or bytes_name not in st.session_state:
        st.session_state[key_name] = key
        st.session_state[bytes_name] = build_fn()
    return st.session_state[bytes_name]
