import base64
import httpx
from typing import Optional, Union
from pathlib import Path
from app.config.aws import (
    BREVO_FROM_EMAIL,
    BREVO_FROM_NAME,
    BREVO_REPLY_TO,
    BREVO_API_URL,
)
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


def _brevo_send(
    to_list: list,
    subject: str,
    html: str,
    text: Optional[str] = None,
    attachments: Optional[list] = None,
) -> bool:
    """POST to Brevo's transactional email API.
    Returns True on a 2xx response, False on any failure — callers treat
    email as best-effort and never propagate the error back to the user."""
    api_key = settings.BREVO_API_KEY
    if not api_key:
        logger.error(
            "BREVO_API_KEY is not configured — cannot send email "
            f"to {to_list}: {subject!r}"
        )
        return False

    payload = {
        "sender": {"name": BREVO_FROM_NAME, "email": BREVO_FROM_EMAIL},
        "to": [{"email": e} for e in to_list],
        "subject": subject,
        "htmlContent": html,
        "replyTo": {"email": BREVO_REPLY_TO},
    }
    if text:
        payload["textContent"] = text
    if attachments:
        payload["attachment"] = attachments

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                BREVO_API_URL,
                json=payload,
                headers={
                    "api-key": api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
            )
        if response.status_code >= 300:
            logger.error(
                f"Brevo rejected email to {to_list} ({response.status_code}): "
                f"{response.text[:500]}"
            )
            return False
        message_id = ""
        try:
            message_id = response.json().get("messageId", "")
        except Exception:
            pass
        logger.info(
            f"Email sent to {to_list}: {subject} | Brevo MessageId: {message_id}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_list} via Brevo: {e}")
        return False


def _send_email(to: Union[str, list], subject: str, html: str, text: str = None) -> bool:
    """Send a plain HTML email via Brevo. Same signature as before so every
    caller keeps working — only the underlying transport changed."""
    to_list = to if isinstance(to, list) else [to]
    return _brevo_send(to_list, subject, html, text=text)


def _send_raw_email(
    to: Union[str, list],
    subject: str,
    html: str,
    pdf_buffer: bytes = None,
    pdf_filename: str = None,
) -> bool:
    """Send an HTML email with an optional PDF attachment via Brevo.
    Brevo accepts attachments as base64-encoded blobs in the JSON body,
    so we encode here and pass through to the shared sender."""
    to_list = to if isinstance(to, list) else [to]
    attachments = None
    if pdf_buffer and pdf_filename:
        attachments = [{
            "name": pdf_filename,
            "content": base64.b64encode(pdf_buffer).decode("ascii"),
        }]
    return _brevo_send(to_list, subject, html, attachments=attachments)


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


def _build_device_images_html(counter_offer) -> str:
    """Render uploaded counter-offer device photos inline in the email so the
    customer can see *why* the price was revised without having to log in."""
    images = getattr(counter_offer, "device_images", None) or []
    if not images:
        return ""
    cells = []
    for img in images[:6]:
        url = getattr(img, "url", None)
        if not url:
            continue
        cells.append(
            f'<td style="padding:4px;width:33%;vertical-align:top;">'
            f'<img src="{url}" alt="Device condition photo" '
            f'style="width:100%;max-width:170px;height:auto;border-radius:8px;'
            f'border:1px solid #e5e7eb;display:block;" /></td>'
        )
    if not cells:
        return ""
    rows = []
    for i in range(0, len(cells), 3):
        rows.append("<tr>" + "".join(cells[i:i + 3]) + "</tr>")
    return (
        '<div style="margin:24px 0;">'
        '<p style="margin:0 0 12px 0;color:#1f2937;font-weight:600;font-size:14px;">'
        'Photos from our inspection:</p>'
        f'<table role="presentation" style="width:100%;border-collapse:separate;border-spacing:4px;">'
        f'{"".join(rows)}</table>'
        '</div>'
    )


WHATSAPP_NUMBER_DISPLAY = "+44 7938 361920"
WHATSAPP_NUMBER_LINK = "447938361920"


def _whatsapp_contact_html() -> str:
    """Inline WhatsApp call-to-action used in counter offer emails.
    Renders as a green pill so it works even when remote images are blocked
    (Gmail/Outlook strip third-party assets by default)."""
    return (
        f'<a href="https://wa.me/{WHATSAPP_NUMBER_LINK}" '
        'style="display:inline-block;background:#25D366;color:#ffffff;'
        'font-weight:700;text-decoration:none;padding:8px 16px;'
        'border-radius:9999px;font-size:14px;">'
        f'WhatsApp us &nbsp;{WHATSAPP_NUMBER_DISPLAY}</a>'
    )


async def send_counter_offer_email(order, counter_offer) -> bool:
    if not order.customer_email:
        logger.warning(f"No customer email for order {order.order_number}, skipping counter offer email")
        return False
    try:
        from datetime import datetime
        template = _load_template("counterOfferReceived")
        review_url = f"{settings.FRONTEND_URL.rstrip('/')}/counter-offer/?token={counter_offer.review_token}"
        expiry_date = counter_offer.expires_at.strftime("%d %B %Y")
        html = _replace_vars(template, {
            "customerName": order.customer_name,
            "orderNumber": order.order_number,
            "originalPrice": f"{order.offered_price:.2f}",
            "revisedPrice": f"{counter_offer.revised_price:.2f}",
            "reason": counter_offer.reason or "",
            "reviewUrl": review_url,
            "expiryDate": expiry_date,
            "supportEmail": EMAIL_DEFAULTS["support_email"],
            "deviceImagesHtml": _build_device_images_html(counter_offer),
            "whatsappContact": _whatsapp_contact_html(),
            "whatsappNumber": WHATSAPP_NUMBER_DISPLAY,
            "whatsappLink": f"https://wa.me/{WHATSAPP_NUMBER_LINK}",
        })
        return _send_email(
            order.customer_email,
            f"Counter Offer for Your Device - Order #{order.order_number}",
            html,
        )
    except Exception as e:
        logger.error(f"Error sending counter offer email for {order.order_number}: {e}")
        return False


def _admin_recipients() -> list:
    raw = getattr(settings, "ADMIN_EMAILS", "") or ""
    emails = [e.strip() for e in raw.split(",") if e.strip()]
    return emails


async def send_admin_counter_offer_response(order, counter_offer, accepted: bool) -> bool:
    """Notify the admins that the customer has acted on a counter offer.
    The admin panel orders list will also surface this — this email is the
    out-of-band ping so staff don't have to be watching the page."""
    recipients = _admin_recipients()
    if not recipients:
        logger.info(
            f"No ADMIN_EMAILS configured — skipping admin counter offer "
            f"{'accepted' if accepted else 'declined'} notification for "
            f"{order.order_number}"
        )
        return False
    try:
        action = "ACCEPTED" if accepted else "DECLINED"
        color = "#16a34a" if accepted else "#dc2626"
        bg = "#f0fdf4" if accepted else "#fef2f2"
        admin_url = (
            f"{settings.ADMIN_PANEL_URL.rstrip('/')}/orders/{order.id}"
        )
        feedback = getattr(counter_offer, "customer_feedback", None) or ""
        feedback_block = (
            f'<p style="margin:12px 0 0 0;color:#374151;font-size:14px;">'
            f'<strong>Customer feedback:</strong> {feedback}</p>'
        ) if feedback else ""
        html = f"""
        <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
                    max-width:560px;margin:0 auto;padding:24px;">
          <div style="background:{bg};border:1px solid {color};border-radius:12px;
                      padding:20px;text-align:center;">
            <h2 style="margin:0;color:{color};font-size:22px;">
              Customer {action} the counter offer
            </h2>
            <p style="margin:6px 0 0 0;color:#374151;font-size:14px;">
              Order <strong>#{order.order_number}</strong>
            </p>
          </div>
          <div style="margin-top:20px;background:#f9fafb;border:1px solid #e5e7eb;
                      border-radius:12px;padding:16px;">
            <p style="margin:0 0 6px 0;color:#374151;font-size:14px;">
              <strong>Customer:</strong> {order.customer_name}
            </p>
            <p style="margin:0 0 6px 0;color:#374151;font-size:14px;">
              <strong>Device:</strong> {order.device_name} ({order.storage} · {order.network})
            </p>
            <p style="margin:0 0 6px 0;color:#374151;font-size:14px;">
              <strong>Original offer:</strong> £{order.offered_price:.2f}
            </p>
            <p style="margin:0 0 6px 0;color:{color};font-size:14px;font-weight:700;">
              Revised offer: £{counter_offer.revised_price:.2f}
            </p>
            {feedback_block}
          </div>
          <div style="text-align:center;margin-top:24px;">
            <a href="{admin_url}" style="display:inline-block;background:#dc2626;
                    color:#fff;text-decoration:none;font-weight:600;
                    padding:12px 28px;border-radius:10px;">Open order in admin</a>
          </div>
        </div>
        """
        return _send_email(
            recipients,
            f"Counter offer {action.lower()} — Order #{order.order_number}",
            html,
        )
    except Exception as e:
        logger.error(
            f"Error sending admin counter offer response email "
            f"for {order.order_number}: {e}"
        )
        return False


async def send_counter_offer_accepted_email(order, counter_offer) -> bool:
    if not order.customer_email:
        return False
    try:
        template = _load_template("counterOfferAccepted")
        html = _replace_vars(template, {
            "customerName": order.customer_name,
            "orderNumber": order.order_number,
            "revisedPrice": f"{counter_offer.revised_price:.2f}",
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
            "revisedPrice": f"{counter_offer.revised_price:.2f}",
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
