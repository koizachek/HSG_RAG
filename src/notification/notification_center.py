from typing import Literal
import mimetypes
import os
import smtplib
from email.message import EmailMessage

import requests

from ..config import NotificationCenterConfig as NC


Channel = Literal["email", "slack"]


class EmailNotifier:
    def __init__(self):
        self.enabled = NC.ENABLE_EMAIL_ALERTS
        self.smtp_host = NC.SMTP_HOST
        self.smtp_port = NC.SMTP_PORT
        self.smtp_user = NC.SMTP_USER
        self.smtp_password = NC.SMTP_PASSWORD
        self.smtp_use_tls = NC.SMTP_USE_TLS
        self.from_email = NC.FROM_EMAIL
        self.to_emails = self._parse_recipients(NC.TO_EMAIL)

        if self.enabled:
            self._validate()

    @staticmethod
    def _parse_recipients(value: str | None) -> list[str]:
        if not value:
            return []
        return [email.strip() for email in value.split(",") if email.strip()]

    def _validate(self) -> None:
        missing = []

        if not self.smtp_host:
            missing.append("NOTIFY_SMTP_HOST")
        if not self.smtp_user:
            missing.append("NOTIFY_SMTP_USER")
        if not self.smtp_password:
            missing.append("NOTIFY_SMTP_PASSWORD")
        if not self.from_email:
            missing.append("NOTIFY_FROM_EMAIL")
        if not self.to_emails:
            missing.append("NOTIFY_TO_EMAIL")

        if missing:
            raise ValueError(f"Missing notification email config: {', '.join(missing)}")

    def send(
        self,
        subject: str,
        body: str,
        attachments: str | list[str] | None = None,
    ) -> None:
        if not self.enabled:
            return

        if isinstance(attachments, str):
            attachments = [attachments]

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)
        msg.set_content(body)

        if attachments:
            for file_path in attachments:
                if not file_path or not os.path.isfile(file_path):
                    continue

                mime_type, _ = mimetypes.guess_type(file_path)
                mime_type = mime_type or "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)

                with open(file_path, "rb") as f:
                    msg.add_attachment(
                        f.read(),
                        maintype=maintype,
                        subtype=subtype,
                        filename=os.path.basename(file_path),
                    )

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
            if self.smtp_use_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)


class SlackNotifier:
    def __init__(self):
        self.enabled = NC.ENABLE_SLACK_ALERTS
        self.webhook_url = NC.SLACK_WEBHOOK_URL

        if self.enabled:
            self._validate()

    def _validate(self) -> None:
        if not self.webhook_url:
            raise ValueError("Missing notification slack config: NOTIFY_SLACK_WEBHOOK_URL")

    def send(self, subject: str, body: str) -> None:
        if not self.enabled:
            return

        text = f"*{subject}*\n{body}"

        response = requests.post(
            self.webhook_url,
            json={"text": text},
            timeout=10,
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise RuntimeError(
                f"Slack notification failed: {response.status_code} {response.text}"
            )


class NotificationCenter:
    def __init__(self):
        self.email = EmailNotifier()
        self.slack = SlackNotifier()

    def send_error(
        self,
        subject: str,
        body: str,
        channel: Channel = "email",
        attachments: str | list[str] | None = None,
    ) -> None:
        if channel == "email":
            self.email.send(subject, body, attachments=attachments)
        elif channel == "slack":
            self.slack.send(subject, body)
        else:
            raise ValueError(f"Unsupported notification channel: {channel}")