import os
import logging
import sys
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_email(
    to_email: str,
    subject: str,
    text_content: str = None,
    html_content: str = None
) -> bool:
    """
    Send an email using SendGrid
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        text_content: Plain text content (optional if html_content is provided)
        html_content: HTML content (optional if text_content is provided)
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    sendgrid_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL')
    
    if not sendgrid_key:
        logger.error("SENDGRID_API_KEY environment variable not set")
        return False
        
    if not from_email:
        logger.error("SENDGRID_FROM_EMAIL environment variable not set")
        return False
    
    if not (text_content or html_content):
        logger.error("Either text_content or html_content must be provided")
        return False
    
    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to_email),
        subject=subject
    )

    if html_content:
        message.content = Content("text/html", html_content)
    elif text_content:
        message.content = Content("text/plain", text_content)

    try:
        sg = SendGridAPIClient(sendgrid_key)
        response = sg.send(message)
        logger.info(f"Email sent to {to_email} with status code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False