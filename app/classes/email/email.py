from flask import current_app
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class Email:

    def __init__(self):
        pass

    # method that automatically sends an email from one address to another using SSL - pieces together the customer support ticket
    @staticmethod
    def send_email(from_email, app_password, to_email, subject, body):
        msg = MIMEMultipart()
        current_app.logger.info(f"from_email received: {from_email}")
        current_app.logger.info(f"app_password received: {app_password}")
        current_app.logger.info(f"to_email received: {to_email}")
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(from_email, app_password)
                server.send_message(msg)
            current_app.logger.info("Email sent successfully!")
        except Exception as e:
            current_app.logger.info(f"Failed to send email: {e}")