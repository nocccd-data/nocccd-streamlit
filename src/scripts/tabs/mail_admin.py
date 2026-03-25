"""Mail Admin tab — preview and send filtered PDF reports to recipients."""

import pandas as pd
import streamlit as st

from src.pipeline.mail.mail_config import CAMPAIGNS
from src.pipeline.mail.report_generator import run_campaign


def render():
    st.header("Mail Admin")

    # --- Sidebar: Campaign selection ---
    campaign_names = list(CAMPAIGNS.keys())
    if not campaign_names:
        st.info("No campaigns configured in `mail_config.py`.")
        return

    selected = st.sidebar.selectbox(
        "Campaign",
        options=campaign_names,
        key="ma_campaign",
    )

    campaign = CAMPAIGNS[selected]

    # --- Main: Campaign details ---
    st.subheader(f"Campaign: {selected}")

    col1, col2 = st.columns(2)
    col1.metric("Report Type", campaign["report_type"])
    col2.metric("Recipients", len(campaign["recipients"]))

    with st.expander("Parameters"):
        for k, v in campaign["params"].items():
            st.text(f"{k}: {v}")

    with st.expander("Email Template"):
        st.text(f"Subject: {campaign['subject_template']}")
        st.divider()
        st.text(campaign["body_template"])

    # --- Main: Recipient table ---
    st.subheader("Recipients")
    recipient_data = []
    for r in campaign["recipients"]:
        filters_str = " / ".join(r.get("filters", {}).values()) or "All"
        recipient_data.append({
            "Name": r["name"],
            "Email": r["email"],
            "Filters": filters_str,
        })
    st.dataframe(pd.DataFrame(recipient_data), hide_index=True, use_container_width=True)

    # --- Sidebar: Actions ---
    dry_run_btn = st.sidebar.button("Dry Run (Preview)", key="ma_dry_run_btn")
    send_btn = st.sidebar.button("Send All", key="ma_send_btn", type="primary")

    # --- Execute ---
    if dry_run_btn or send_btn:
        dry_run = dry_run_btn
        mode = "Generating previews..." if dry_run else "Sending emails..."

        email_config = dict(st.secrets.get("email", {}))
        if not dry_run and not email_config.get("smtp_password"):
            st.error("Missing `[email]` config in `.streamlit/secrets.toml`.")
            return

        progress_bar = st.progress(0, text=mode)

        def _st_progress(current, total, name):
            progress_bar.progress(current / total, text=f"{mode} {current}/{total} — {name}")

        results = run_campaign(
            selected,
            email_config,
            dry_run=dry_run,
            progress_callback=_st_progress,
        )

        progress_bar.empty()
        st.session_state["ma_results"] = results
        st.session_state["ma_dry_run"] = dry_run

    # --- Results ---
    if "ma_results" in st.session_state:
        results = st.session_state["ma_results"]
        dry_run = st.session_state.get("ma_dry_run", False)

        sent = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)

        st.subheader("Dry Run Results" if dry_run else "Send Results")

        c1, c2 = st.columns(2)
        c1.metric("Success", sent)
        c2.metric("Failed", failed)

        for r in results:
            if r.success:
                label = f"{r.recipient_name} ({r.filter_desc})"
                if dry_run and r.pdf_bytes:
                    st.download_button(
                        f"Download: {label}",
                        data=r.pdf_bytes,
                        file_name=f"preview_{r.filter_desc.lower().replace(' ', '_').replace('/', '_')}.pdf",
                        mime="application/pdf",
                        key=f"ma_dl_{r.recipient_email}",
                    )
                else:
                    st.success(f"Sent to {r.recipient_name} <{r.recipient_email}> — {r.filter_desc}")
            else:
                st.error(f"Failed: {r.recipient_name} <{r.recipient_email}> — {r.error}")
