"""Mail providers. Currently: Gmail via IMAP."""
from weaver.providers.mail.base import MailMessage, MailProvider
from weaver.providers.mail.gmail_imap import GmailIMAPProvider

__all__ = ["MailMessage", "MailProvider", "GmailIMAPProvider"]
