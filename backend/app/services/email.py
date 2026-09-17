import smtplib
import ssl
from email.message import EmailMessage

from app.core.email_config import email_settings


class EmailService:
    """SMTP 설정이 있을 때 이메일 인증 코드를 발송합니다."""

    @property
    def is_configured(self) -> bool:
        credentials_complete = bool(email_settings.smtp_username) == bool(
            email_settings.smtp_password
        )
        return bool(
            email_settings.smtp_host
            and email_settings.smtp_from_email
            and credentials_complete
        )

    def send_verification_code(self, recipient: str, code: str) -> bool:
        if not self.is_configured:
            return False

        message = EmailMessage()
        message["Subject"] = "MediSense 이메일 인증 코드"
        message["From"] = email_settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            f"MediSense 이메일 인증 코드는 {code}입니다. "
            f"{email_settings.email_verification_expire_minutes}분 안에 입력해주세요."
        )

        self._send(message)
        return True

    def send_password_reset_link(self, recipient: str, reset_url: str) -> bool:
        """사용자가 클릭할 비밀번호 재설정 링크를 SMTP로 발송합니다."""
        if not self.is_configured:
            return False

        message = EmailMessage()
        message["Subject"] = "MediSense 비밀번호 재설정"
        message["From"] = email_settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            "아래 링크에서 비밀번호를 재설정해주세요. 링크는 30분 동안 유효합니다.\n\n"
            f"{reset_url}\n\n본인이 요청하지 않았다면 이 메일을 무시해주세요."
        )
        self._send(message)
        return True

    def _send(self, message: EmailMessage) -> None:
        """SMTP 연결 코드를 한곳에서 관리합니다."""
        context = ssl.create_default_context()
        if email_settings.smtp_use_ssl:
            connection = smtplib.SMTP_SSL(
                email_settings.smtp_host,
                email_settings.smtp_port,
                timeout=email_settings.smtp_timeout_seconds,
                context=context,
            )
        else:
            connection = smtplib.SMTP(
                email_settings.smtp_host,
                email_settings.smtp_port,
                timeout=email_settings.smtp_timeout_seconds,
            )
        with connection as smtp:
            if email_settings.smtp_use_tls and not email_settings.smtp_use_ssl:
                smtp.starttls(context=context)
            if email_settings.smtp_username and email_settings.smtp_password:
                smtp.login(email_settings.smtp_username, email_settings.smtp_password)
            smtp.send_message(message)


email_service = EmailService()
