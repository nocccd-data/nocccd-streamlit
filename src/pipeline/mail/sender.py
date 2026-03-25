"""SMTP email sender for Gmail with TLS and PDF attachment."""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(
    smtp_config: dict,
    to_email: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Send a single email with a PDF attachment via Gmail SMTP/TLS.

    Parameters
    ----------
    smtp_config : dict
        Keys: smtp_server, smtp_port, smtp_username, smtp_password,
              from_email, from_name
    to_email : str
        Recipient email address.
    subject : str
        Email subject line.
    body : str
        Plain-text email body.
    pdf_bytes : bytes
        Raw PDF content.
    pdf_filename : str
        Filename for the PDF attachment (e.g. "seat_count_cypress.pdf").
    """
    msg = MIMEMultipart()
    msg["From"] = f"{smtp_config['from_name']} <{smtp_config['from_email']}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(attachment)

    with smtplib.SMTP(smtp_config["smtp_server"], int(smtp_config["smtp_port"])) as server:
        server.starttls()
        server.login(smtp_config["smtp_username"], smtp_config["smtp_password"])
        server.send_message(msg)
