"""Email service for sending notifications.

This module provides email delivery functionality using SendGrid
or other email service providers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    """An email message to be sent."""

    to_email: str
    subject: str
    text_content: str
    html_content: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    categories: list[str] | None = None


@dataclass(frozen=True)
class EmailResult:
    """Result of an email send operation."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    provider_response: dict[str, Any] | None = None


class EmailSender(ABC):
    """Abstract base class for email senders."""

    @abstractmethod
    def send(self, message: EmailMessage) -> EmailResult:
        """Send an email message."""
        pass

    @abstractmethod
    def send_batch(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Send multiple email messages."""
        pass


class DevEmailSender(EmailSender):
    """
    Development email sender that logs emails instead of sending them.

    Use this for local development and testing.
    """

    def __init__(self, log_content: bool = True) -> None:
        self.log_content = log_content
        self.sent_messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailResult:
        """Log the email instead of sending."""
        self.sent_messages.append(message)

        if self.log_content:
            logger.info(
                "DEV EMAIL: to=%s subject=%s",
                message.to_email,
                message.subject,
            )
            logger.debug("DEV EMAIL CONTENT:\n%s", message.text_content)

        return EmailResult(
            success=True,
            message_id=f"dev-{len(self.sent_messages)}",
        )

    def send_batch(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Log all emails."""
        return [self.send(msg) for msg in messages]


class SendGridEmailSender(EmailSender):
    """
    SendGrid email sender for production use.

    Requires the sendgrid package: pip install sendgrid
    """

    def __init__(
        self,
        api_key: str,
        default_from_email: str = "hello@curious.now",
        default_from_name: str = "Curious Now",
    ) -> None:
        self.api_key = api_key
        self.default_from_email = default_from_email
        self.default_from_name = default_from_name
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-load the SendGrid client."""
        if self._client is None:
            try:
                from sendgrid import SendGridAPIClient

                self._client = SendGridAPIClient(self.api_key)
            except ImportError as exc:
                raise ImportError(
                    "sendgrid package is required for SendGridEmailSender. "
                    "Install it with: pip install sendgrid"
                ) from exc
        return self._client

    def send(self, message: EmailMessage) -> EmailResult:
        """Send an email via SendGrid."""
        try:
            from sendgrid.helpers.mail import (
                Category,
                Content,
                Email,
                Mail,
                To,
            )
        except ImportError:
            return EmailResult(
                success=False,
                error="sendgrid package not installed",
            )

        try:
            from_email = Email(
                message.from_email or self.default_from_email,
                message.from_name or self.default_from_name,
            )
            to_email = To(message.to_email)

            mail = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=message.subject,
            )

            # Add text content
            mail.add_content(Content("text/plain", message.text_content))

            # Add HTML content if provided
            if message.html_content:
                mail.add_content(Content("text/html", message.html_content))

            # Add reply-to if provided
            if message.reply_to:
                from sendgrid.helpers.mail import ReplyTo

                mail.reply_to = ReplyTo(message.reply_to)

            # Add categories if provided
            if message.categories:
                for cat in message.categories:
                    mail.add_category(Category(cat))

            # Send the email
            client = self._get_client()
            response = client.send(mail)

            success = 200 <= response.status_code < 300

            return EmailResult(
                success=success,
                message_id=response.headers.get("X-Message-Id"),
                provider_response={
                    "status_code": response.status_code,
                    "headers": dict(response.headers) if response.headers else {},
                },
                error=None if success else f"Status code: {response.status_code}",
            )

        except Exception as exc:
            logger.exception("SendGrid error sending email to %s", message.to_email)
            return EmailResult(
                success=False,
                error=str(exc),
            )

    def send_batch(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Send multiple emails via SendGrid."""
        # SendGrid supports batch sending, but for simplicity we send one by one
        # In production, you might want to use SendGrid's batch API
        return [self.send(msg) for msg in messages]


class SMTPEmailSender(EmailSender):
    """
    SMTP email sender for self-hosted email servers.

    Use this if you have your own SMTP server or use services like
    Amazon SES with SMTP credentials.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        default_from_email: str = "hello@curious.now",
        default_from_name: str = "Curious Now",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.default_from_email = default_from_email
        self.default_from_name = default_from_name

    def send(self, message: EmailMessage) -> EmailResult:
        """Send an email via SMTP."""
        import smtplib
        import uuid
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.utils import formataddr

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = formataddr(
                (
                    message.from_name or self.default_from_name,
                    message.from_email or self.default_from_email,
                )
            )
            msg["To"] = message.to_email

            if message.reply_to:
                msg["Reply-To"] = message.reply_to

            # Generate message ID
            message_id = f"<{uuid.uuid4()}@curious.now>"
            msg["Message-ID"] = message_id

            # Attach text content
            msg.attach(MIMEText(message.text_content, "plain", "utf-8"))

            # Attach HTML content if provided
            if message.html_content:
                msg.attach(MIMEText(message.html_content, "html", "utf-8"))

            # Connect and send
            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.host, self.port)

            if self.username and self.password:
                server.login(self.username, self.password)

            server.sendmail(
                message.from_email or self.default_from_email,
                [message.to_email],
                msg.as_string(),
            )
            server.quit()

            return EmailResult(
                success=True,
                message_id=message_id,
            )

        except Exception as exc:
            logger.exception("SMTP error sending email to %s", message.to_email)
            return EmailResult(
                success=False,
                error=str(exc),
            )

    def send_batch(self, messages: list[EmailMessage]) -> list[EmailResult]:
        """Send multiple emails via SMTP."""
        return [self.send(msg) for msg in messages]


# ─────────────────────────────────────────────────────────────────────────────
# Factory function
# ─────────────────────────────────────────────────────────────────────────────


def get_email_sender() -> EmailSender:
    """
    Get the configured email sender based on settings.

    Returns DevEmailSender if no email service is configured.
    """
    from curious_now.settings import get_settings

    settings = get_settings()

    # Check for SendGrid
    if hasattr(settings, "sendgrid_api_key") and settings.sendgrid_api_key:
        return SendGridEmailSender(
            api_key=settings.sendgrid_api_key,
            default_from_email=getattr(settings, "email_from_address", "hello@curious.now"),
            default_from_name=getattr(settings, "email_from_name", "Curious Now"),
        )

    # Check for SMTP
    if hasattr(settings, "smtp_host") and settings.smtp_host:
        return SMTPEmailSender(
            host=settings.smtp_host,
            port=getattr(settings, "smtp_port", 587),
            username=getattr(settings, "smtp_username", None),
            password=getattr(settings, "smtp_password", None),
            use_tls=getattr(settings, "smtp_use_tls", True),
            default_from_email=getattr(settings, "email_from_address", "hello@curious.now"),
            default_from_name=getattr(settings, "email_from_name", "Curious Now"),
        )

    # Default to dev sender
    return DevEmailSender(log_content=True)
