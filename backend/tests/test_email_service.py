import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.email import EmailService


class EmailServiceTest(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            smtp_host="smtp.mx.cloudflare.net",
            smtp_port=465,
            smtp_username="api_token",
            smtp_password="test-token",
            smtp_from_email="noreply@medisense.ai.kr",
            smtp_use_ssl=True,
            smtp_use_tls=False,
            smtp_timeout_seconds=30,
            email_verification_expire_minutes=5,
        )
        self.settings_patch = patch("app.services.email.email_settings", self.settings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.service = EmailService()

    @patch("app.services.email.smtplib.SMTP")
    @patch("app.services.email.smtplib.SMTP_SSL")
    def test_cloudflare_uses_verified_tls_and_sends_verification(self, secure, plain):
        self.assertTrue(self.service.send_verification_code("user@example.com", "012345"))
        plain.assert_not_called()
        context = secure.call_args.kwargs["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(secure.call_args.args, ("smtp.mx.cloudflare.net", 465))
        self.assertEqual(secure.call_args.kwargs["timeout"], 30)
        smtp = secure.return_value.__enter__.return_value
        smtp.starttls.assert_not_called()
        smtp.login.assert_called_once_with("api_token", "test-token")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["From"], "noreply@medisense.ai.kr")
        self.assertEqual(message["To"], "user@example.com")
        self.assertIn("012345", message.get_content())
        self.assertIn("5분", message.get_content())

    @patch("app.services.email.smtplib.SMTP_SSL")
    @patch("app.services.email.smtplib.SMTP")
    def test_existing_starttls_transport_still_works(self, plain, secure):
        self.settings.smtp_use_ssl = False
        self.settings.smtp_use_tls = True
        self.settings.smtp_port = 587
        self.service.send_verification_code("user@example.com", "123456")
        secure.assert_not_called()
        smtp = plain.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        self.assertTrue(smtp.starttls.call_args.kwargs["context"].check_hostname)
        smtp.send_message.assert_called_once()

    @patch("app.services.email.smtplib.SMTP_SSL")
    def test_missing_token_does_not_attempt_delivery(self, secure):
        self.settings.smtp_password = ""
        self.assertFalse(self.service.is_configured)
        self.assertFalse(self.service.send_verification_code("user@example.com", "123456"))
        secure.assert_not_called()

    @patch("app.services.email.smtplib.SMTP_SSL")
    def test_password_reset_uses_same_cloudflare_connection(self, secure):
        url = "https://medisense.ai.kr/reset-password?token=test-token"
        self.assertTrue(self.service.send_password_reset_link("user@example.com", url))
        message = secure.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertIn(url, message.get_content())
        self.assertEqual(message["Subject"], "MediSense 비밀번호 재설정")


if __name__ == "__main__":
    unittest.main()
