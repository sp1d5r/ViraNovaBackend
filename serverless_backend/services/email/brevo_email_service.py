import os
from datetime import datetime
import logging
from sib_api_v3_sdk import Configuration, ApiClient, TransactionalEmailsApi, SendSmtpEmail

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        api_key = os.getenv('BREVO_API_KEY')
        if not api_key:
            raise ValueError("BREVO_API_KEY environment variable is not set")

        configuration = Configuration()
        configuration.api_key['api-key'] = api_key
        self.api_instance = TransactionalEmailsApi(ApiClient(configuration))

    def send_email(self, to_email, subject, html_content, sender_name="Viranova", sender_email="elijah@conventa.net"):
        sender = {"name": sender_name, "email": sender_email}
        to = [{"email": to_email}]
        send_smtp_email = SendSmtpEmail(
            to=to,
            html_content=html_content,
            sender=sender,
            subject=subject
        )

        try:
            logger.info(f"Attempting to send email to {to_email}")
            api_response = self.api_instance.send_transac_email(send_smtp_email)
            logger.info(f"Email sent successfully. MessageId: {api_response.message_id}")
            return api_response
        except Exception as e:
            logger.error(f"Exception when calling TransactionalEmailsApi->send_transac_email: {e}")
            raise e

    def send_email_template(self, to_email, template_id, template_params, subject=None, sender_name="Viranova",
                            sender_email="elijah@conventa.net"):
        sender = {"name": sender_name, "email": sender_email}
        to = [{"email": to_email}]
        send_smtp_email = SendSmtpEmail(
            to=to,
            template_id=template_id,
            params=template_params,
            sender=sender,
            subject=subject
        )

        try:
            logger.info(f"Attempting to send email using template {template_id} to {to_email}")
            api_response = self.api_instance.send_transac_email(send_smtp_email)
            logger.info(f"Email sent successfully. MessageId: {api_response.message_id}")
            return api_response
        except Exception as e:
            logger.error(f"Exception when calling TransactionalEmailsApi->send_transac_email: {e}")
            raise e

    def send_video_ready_notification(self, to_email, video_title, video_url):
        template_id = 2  # Replace with your actual template ID
        template_params = {
            "video_title": video_title,
            "video_url": video_url,
            "current_date": datetime.now().strftime("%b %d, %Y")
        }
        subject = f"[Video Ready] Your video '{video_title}' is ready!"

        logger.info(f"Sending video ready notification for '{video_title}' to {to_email}")
        return self.send_email_template(to_email, template_id, template_params, subject)

