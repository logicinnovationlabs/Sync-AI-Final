import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

class EmailSender:
    """Email sending utility."""
    
    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
    
    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body: str,
        from_address: Optional[str] = None,
        html: bool = False
    ) -> bool:
        """Send email."""
        try:
            msg = MIMEMultipart()
            msg['From'] = from_address or self.username
            msg['To'] = ', '.join(to_addresses)
            msg['Subject'] = subject
            
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            return True
        except Exception:
            return False
