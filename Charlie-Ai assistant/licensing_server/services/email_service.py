"""
licensing_server/services/email_service.py — Production-grade transactional email service.
Supports standard SMTP (STARTTLS / SSL) with automatic fallback to structured log audit in dev/test.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from licensing_server.config import config

logger = logging.getLogger("charlie-licensing.email")


class EmailService:
    def __init__(self):
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.user = config.SMTP_USER
        self.password = config.SMTP_PASSWORD
        self.from_email = config.SMTP_FROM_EMAIL or "noreply@charlie.ai"
        self.use_tls = config.SMTP_USE_TLS

    def is_configured(self) -> bool:
        return bool(self.host and self.port and self.user and self.password)

    def send_email(self, to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> bool:
        """Send an email using SMTP or log for development."""
        if not self.is_configured():
            logger.warning(
                f"[EMAIL SERVICE (DEV MODE)] SMTP not configured. Simulating delivery to {to_email}:\n"
                f"Subject: {subject}\n"
                f"Body: {text_content or html_content[:200]}..."
            )
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"CHARLIE AI Assistant <{self.from_email}>"
            msg["To"] = to_email

            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            if self.port == 465:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=10)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=10)
                if self.use_tls:
                    server.starttls()

            server.login(self.user, self.password)
            server.sendmail(self.from_email, [to_email], msg.as_string())
            server.quit()
            logger.info(f"Email successfully delivered to {to_email} with subject '{subject}'")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_password_reset_email(self, to_email: str, reset_token: str) -> bool:
        reset_url = f"https://charlie.ai/login.html?token={reset_token}"
        subject = "Reset Your CHARLIE AI Password"
        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: auto; padding: 32px 24px; background: #0c1017; color: #f1f5f9; border-radius: 12px; border: 1px solid #1e293b;">
            <h2 style="color: #00f5ff; margin-top: 0;">Password Reset Request</h2>
            <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1;">We received a request to reset your password for your CHARLIE AI Assistant account.</p>
            <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1;">Click the button below to choose a new password. This link is valid for 15 minutes.</p>
            <div style="margin: 28px 0;">
                <a href="{reset_url}" style="background: linear-gradient(135deg, #00f5ff, #0077ff); color: #000; font-weight: 700; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block;">Reset Password</a>
            </div>
            <p style="font-size: 12px; color: #64748b; line-height: 1.5;">If you did not request a password reset, you can safely ignore this email. Your password will not change.</p>
            <hr style="border: none; border-top: 1px solid #1e293b; margin: 24px 0;">
            <p style="font-size: 11px; color: #475569;">© 2026 CHARLIE AI Desktop Assistant. Anees Chaudhary.</p>
        </div>
        """
        text = f"Reset your password by opening this link: {reset_url}\nValid for 15 minutes."
        return self.send_email(to_email, subject, html, text)

    def send_verification_email(self, to_email: str, verify_token: str) -> bool:
        verify_url = f"https://charlie.ai/login.html?verify={verify_token}"
        subject = "Verify Your CHARLIE AI Email Address"
        html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: auto; padding: 32px 24px; background: #0c1017; color: #f1f5f9; border-radius: 12px; border: 1px solid #1e293b;">
            <h2 style="color: #00f5ff; margin-top: 0;">Verify Your Email Address</h2>
            <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1;">Thank you for registering with CHARLIE AI Assistant.</p>
            <p style="font-size: 15px; line-height: 1.6; color: #cbd5e1;">Click below to verify your email and activate your account:</p>
            <div style="margin: 28px 0;">
                <a href="{verify_url}" style="background: linear-gradient(135deg, #00f5ff, #0077ff); color: #000; font-weight: 700; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block;">Verify Email</a>
            </div>
            <p style="font-size: 12px; color: #64748b; line-height: 1.5;">Valid for 24 hours.</p>
            <hr style="border: none; border-top: 1px solid #1e293b; margin: 24px 0;">
            <p style="font-size: 11px; color: #475569;">© 2026 CHARLIE AI Desktop Assistant. Anees Chaudhary.</p>
        </div>
        """
        text = f"Verify your email by opening: {verify_url}"
        return self.send_email(to_email, subject, html, text)
