import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Optional, Union
from pathlib import Path
from app.config.aws import get_ses_client, SES_FROM, SES_FROM_EMAIL, SES_REPLY_TO
from app.config.email_config import EMAIL_DEFAULTS, EMAIL_TEMPLATES, ORDER_STATUS_MESSAGES
from app.config.settings import settings
from app.utils.logger import logger

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def _replace_vars(template: str, variables: dict) -> str:
    """Replace {{key}} placeholders with values — matches Node.js replaceTemplateVars."""
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(value) if value is not None else "")
    return template


def _load_template(template_name: str) -> str:
    """Load HTML template from /templates folder."""
    try:
        path = TEMPLATES_DIR / f"{template_name}.html"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error loading template {template_name}: {e}")
        return "<p>{{message}}</p>"


def _send_email(to: Union[str, list], subject: str, html: str, text: str = None) -> bool:
    """Send email via AWS SES SendEmail."""
    try:
        client = get_ses_client()
        to_list = to if isinstance(to, list) else [to]
        params = {
            "Source": SES_FROM,
            "Destination": {"ToAddresses": to_list},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
            "ReplyToAddresses": [SES_REPLY_TO],
        }
        if text:
            params["Message"]["Body"]["Text"] = {"Data": text, "Charset": "UTF-8"}

        result = client.send_email(**params)
        logger.info(f"Email sent to {to}: {subject} | MessageId: {result['MessageId']}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


def _send_raw_email(to: Union[str, list], subject: str, html: str, pdf_buffer: bytes = None, pdf_filename: str = None) -> bool:
    """Send email with optional PDF attachment via AWS SES SendRawEmail."""
    try:
        client = get_ses_client()
        to_list = to if isinstance(to, list) else [to]

        msg = MIMEMultipart("mixed")
        msg["From"] = SES_FROM
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject

        # HTML body
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(body_part)

        # PDF attachment
        if pdf_buffer and pdf_filename:
            attachment = MIMEApplication(pdf_buffer, _subtype="pdf")
            attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
            msg.attach(attachment)

        result = client.send_raw_email(
            Source=SES_FROM_EMAIL,
            Destinations=to_list,
            RawMessage={"Data": msg.as_bytes()},
        )
        logger.info(f"Raw email sent to {to}: {subject} | MessageId: {result['MessageId']}")
        return True
    except Exception as e:
        logger.error(f"Failed to send raw email to {to}: {e}")
        return False


async def send_otp_email(email: str, otp_code: str) -> bool:
    template = _load_template("otp")
    html = _replace_vars(template, {
        "otp": otp_code,
        "email": email,
        "companyName": EMAIL_DEFAULTS["company_name"],
        "validityMinutes": str(settings.OTP_EXPIRY_MINUTES),
    })
    return _send_email(email, EMAIL_TEMPLATES["otp"]["subject"], html)


async def send_order_confirmation(order) -> bool:
    if not order.customer_email:
        logger.warning(f"No customer email for order {order.order_number}, skipping confirmation")
        return False
    try:
        template = _load_template("orderReceived")
        html = _replace_vars(template, {
            "orderNumber": order.order_number,
            "customerName": order.customer_name,
            "deviceName": order.device_name,
            "network": order.network,
            "storage": order.storage,
            "deviceGrade": order.device_grade,
            "offeredPrice": f"{order.offered_price:.2f}",
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_raw_email(
            to=order.customer_email,
            subject=f"Order Confirmation - {order.order_number}",
            html=html,
        )
    except Exception as e:
        logger.error(f"Error sending order confirmation for {order.order_number}: {e}")
        return False


async def send_order_status_update(order, old_status: str) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("orderStatusUpdate")
        final_price = order.final_price or order.offered_price
        html = _replace_vars(template, {
            "orderNumber": order.order_number,
            "customerName": order.customer_name,
            "oldStatus": old_status,
            "newStatus": order.status,
            "statusMessage": ORDER_STATUS_MESSAGES.get(order.status, "Status updated"),
            "deviceName": order.device_name,
            "finalPrice": f"£{final_price:.2f}",
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_email(order.customer_email, f"Order Update - {order.order_number}", html)
    except Exception as e:
        logger.error(f"Error sending status update email: {e}")
        return False


async def send_order_completion_email(order) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("orderCompleted")
        final = order.final_price or order.offered_price
        html = _replace_vars(template, {
            "orderNumber": order.order_number,
            "customerName": order.customer_name,
            "deviceName": order.device_name,
            "deviceGrade": order.device_grade,
            "finalPrice": f"{final:.2f}",
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_raw_email(
            to=order.customer_email,
            subject=f"Order Completed & Paid - {order.order_number}",
            html=html,
        )
    except Exception as e:
        logger.error(f"Error sending order completion email: {e}")
        return False


async def send_price_revision_email(order, old_price: float, new_price: float, reason: str) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("priceRevision")
        html = _replace_vars(template, {
            "orderNumber": order.order_number,
            "customerName": order.customer_name,
            "deviceName": order.device_name,
            "originalPrice": f"£{old_price:.2f}",
            "revisedPrice": f"£{new_price:.2f}",
            "revisionReason": reason or "Price adjustment after inspection",
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_email(order.customer_email, f"Price Revision - {order.order_number}", html)
    except Exception as e:
        logger.error(f"Error sending price revision email: {e}")
        return False


async def send_payment_confirmation(order) -> bool:
    if not order.customer_email:
        return False
    try:
        from datetime import datetime
        template = _load_template("paymentConfirmation")
        final = order.final_price or order.offered_price
        acct = ""
        if order.payout_details and order.payout_details.account_number:
            acct = f"****{order.payout_details.account_number[-4:]}"
        payment_date = datetime.utcnow().strftime("%d %B %Y")
        transaction_id = getattr(order, "transaction_id", None) or "N/A"
        html = _replace_vars(template, {
            "orderNumber": order.order_number,
            "customerName": order.customer_name,
            "deviceName": order.device_name,
            "amount": f"{final:.2f}",
            "paidAmount": f"£{final:.2f}",
            "paymentMethod": "UK Bank Transfer",
            "transactionId": transaction_id,
            "paymentDate": payment_date,
            "bankName": (order.payout_details.account_name if order.payout_details else None) or "your bank",
            "accountNumber": acct,
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_email(order.customer_email, f"Payment Sent - {order.order_number}", html)
    except Exception as e:
        logger.error(f"Error sending payment confirmation: {e}")
        return False


async def send_counter_offer_email(order, counter_offer) -> bool:
    if not order.customer_email:
        logger.warning(f"No customer email for order {order.order_number}, skipping counter offer email")
        return False
    try:
        from datetime import datetime
        template = _load_template("counterOfferReceived")
        review_url = f"{settings.FRONTEND_URL.rstrip('/')}/counter-offer/?token={counter_offer.token}"
        expiry_date = counter_offer.expires_at.strftime("%d %B %Y")
        html = _replace_vars(template, {
            "customerName": order.customer_name,
            "orderNumber": order.order_number,
            "originalPrice": f"{order.offered_price:.2f}",
            "revisedPrice": f"{counter_offer.counter_price:.2f}",
            "reason": counter_offer.reason or "",
            "reviewUrl": review_url,
            "expiryDate": expiry_date,
            "supportEmail": EMAIL_DEFAULTS["support_email"],
        })
        return _send_email(
            order.customer_email,
            f"Counter Offer for Your Device - Order #{order.order_number}",
            html,
        )
    except Exception as e:
        logger.error(f"Error sending counter offer email for {order.order_number}: {e}")
        return False


async def send_counter_offer_accepted_email(order, counter_offer) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("counterOfferAccepted")
        html = _replace_vars(template, {
            "customerName": order.customer_name,
            "orderNumber": order.order_number,
            "revisedPrice": f"{counter_offer.counter_price:.2f}",
            "supportEmail": EMAIL_DEFAULTS["support_email"],
        })
        return _send_email(order.customer_email, f"Counter Offer Accepted - Order #{order.order_number}", html)
    except Exception as e:
        logger.error(f"Error sending counter offer accepted email: {e}")
        return False


async def send_counter_offer_declined_email(order, counter_offer) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("counterOfferDeclined")
        html = _replace_vars(template, {
            "customerName": order.customer_name,
            "orderNumber": order.order_number,
            "revisedPrice": f"{counter_offer.counter_price:.2f}",
            "supportEmail": EMAIL_DEFAULTS["support_email"],
        })
        return _send_email(order.customer_email, f"Counter Offer Declined - Order #{order.order_number}", html)
    except Exception as e:
        logger.error(f"Error sending counter offer declined email: {e}")
        return False


async def send_contact_confirmation(submission) -> bool:
    try:
        template = _load_template("contactConfirmation")
        html = _replace_vars(template, {
            "name": submission.name,
            "email": submission.email,
            "phone": submission.phone or "Not provided",
            "subject": submission.subject or "",
            "message": submission.message,
            "companyName": EMAIL_DEFAULTS["company_name"],
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "supportPhone": EMAIL_DEFAULTS["support_phone"],
        })
        return _send_email(submission.email, "We received your message", html)
    except Exception as e:
        logger.error(f"Error sending contact confirmation: {e}")
        return False
