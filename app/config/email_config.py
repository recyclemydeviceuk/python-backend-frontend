from app.config.settings import settings

EMAIL_DEFAULTS = {
    "company_name": "CashMyMobile",
    "website_url": settings.FRONTEND_URL,
    "support_email": settings.SUPPORT_EMAIL,
    "support_phone": settings.SUPPORT_PHONE,
    "logo_url": "https://res.cloudinary.com/dn2sab6qc/image/upload/v1771700003/Cashmymobile_logo_y7ndez.png",
    "admin_panel_url": settings.ADMIN_PANEL_URL,
}

EMAIL_TEMPLATES = {
    "otp":                    {"subject": "Admin OTP - CashMyMobile",                     "file": "otp.html"},
    "orderReceived":          {"subject": "Order Confirmation - CashMyMobile",             "file": "orderReceived.html"},
    "orderStatusUpdate":      {"subject": "Order Update - CashMyMobile",                   "file": "orderStatusUpdate.html"},
    "orderCompleted":         {"subject": "Order Completed & Paid - CashMyMobile",         "file": "orderCompleted.html"},
    "priceRevision":          {"subject": "Price Revision - CashMyMobile",                 "file": "priceRevision.html"},
    "paymentConfirmation":    {"subject": "Payment Sent - CashMyMobile",                   "file": "paymentConfirmation.html"},
    "contactConfirmation":    {"subject": "We Received Your Message - CashMyMobile",       "file": "contactConfirmation.html"},
    "counterOfferReceived":   {"subject": "Counter Offer for Your Device - CashMyMobile",  "file": "counterOfferReceived.html"},
    "counterOfferAccepted":   {"subject": "Counter Offer Accepted - CashMyMobile",         "file": "counterOfferAccepted.html"},
    "counterOfferDeclined":   {"subject": "Counter Offer Declined - CashMyMobile",         "file": "counterOfferDeclined.html"},
}

ORDER_STATUS_MESSAGES = {
    "PACK_SENT":          "Your postage pack has been sent",
    "DEVICE_RECEIVED":    "We have received your device",
    "INSPECTION_PASSED":  "Your device has passed inspection",
    "INSPECTION_FAILED":  "Your device did not pass inspection",
    "PRICE_REVISED":      "The price for your device has been revised",
    "PAYOUT_READY":       "Your payment is ready to be processed",
    "PAID":               "Payment has been sent",
    "CLOSED":             "Your order has been completed",
    "CANCELLED":          "Your order has been cancelled",
}
