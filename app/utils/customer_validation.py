"""
Customer detail validation shared by the public website order form
(POST /sell/submit) and the public JSON order endpoint (POST /api/orders).

Every rule here exists to stop junk / abusive submissions reaching the
orders list (e.g. a 300-character slur pasted into every field). Each
function returns the *cleaned* value or raises ValueError with a short
customer-facing message.

Limits (characters, after trimming):
    name / account name  2–60    letters, spaces, ' - . only
    email                ≤ 100   standard address format
    phone                10–11 digits, UK mobile or landline (+44 accepted)
    address              5–150   letters, digits, spaces , . ' - / & #
    city                 2–50    letters, spaces, ' - .
    postcode             5–8     valid UK postcode format
    sort code            exactly 6 digits   (stored as 12-34-56)
    account number       exactly 8 digits
"""
import re

MAX_NAME = 60
MAX_EMAIL = 100
MAX_PHONE_RAW = 20
MAX_ADDRESS = 150
MAX_CITY = 50
MAX_POSTCODE = 8

_NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' .\-]*$")
_CITY_RE = _NAME_RE
_ADDRESS_RE = re.compile(r"^[A-Za-z0-9À-ÖØ-öø-ÿ ,.'\-/&#\n\r]+$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# UK postcode: A9 9AA, A99 9AA, AA9 9AA, AA99 9AA, A9A 9AA, AA9A 9AA (+ GIR 0AA)
_POSTCODE_RE = re.compile(
    r"^(GIR ?0AA|[A-PR-UWYZ][A-HK-Y]?[0-9][0-9A-Z]? ?[0-9][ABD-HJLNP-UW-Z]{2})$",
    re.IGNORECASE,
)
# The same 4+ character chunk repeated 3 or more times back-to-back
# ("KILL YOURSELF ... KILL YOURSELF ... KILL YOURSELF ...") is never a real
# name or address.
_REPEAT_RE = re.compile(r"(.{4,}?)\1{2,}", re.IGNORECASE)


def _clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _reject_repetition(value: str, label: str) -> None:
    if _REPEAT_RE.search(value):
        raise ValueError(f"{label} looks invalid — please enter your real {label.lower()}.")


def validate_name(value, label: str = "Name") -> str:
    v = _clean(value)
    if len(v) < 2:
        raise ValueError(f"{label} is too short.")
    if len(v) > MAX_NAME:
        raise ValueError(f"{label} must be {MAX_NAME} characters or fewer.")
    if not _NAME_RE.match(v):
        raise ValueError(f"{label} can only contain letters, spaces, hyphens and apostrophes.")
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2}", v):
        raise ValueError(f"{label} looks invalid.")
    _reject_repetition(v, label)
    return v


def validate_email(value, required: bool = True) -> str:
    v = _clean(value).lower()
    if not v:
        if required:
            raise ValueError("Email address is required.")
        return ""
    if len(v) > MAX_EMAIL:
        raise ValueError(f"Email address must be {MAX_EMAIL} characters or fewer.")
    if " " in v or not _EMAIL_RE.match(v):
        raise ValueError("Please enter a valid email address (e.g. name@example.com).")
    return v


def validate_phone(value) -> str:
    raw = _clean(value)
    if not raw:
        raise ValueError("Phone number is required.")
    if len(raw) > MAX_PHONE_RAW:
        raise ValueError("Phone number is too long.")
    if not re.match(r"^\+?[0-9 ()\-]+$", raw):
        raise ValueError("Phone number can only contain digits.")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("44") and raw.startswith("+"):
        digits = "0" + digits[2:]
    elif digits.startswith("0044"):
        digits = "0" + digits[4:]
    elif digits.startswith("44") and len(digits) == 12:
        digits = "0" + digits[2:]
    # UK: 07xxx xxxxxx mobiles (11) or 01/02/03 landlines (10–11 digits)
    if not re.match(r"^0[1237][0-9]{8,9}$", digits) or len(digits) not in (10, 11):
        raise ValueError("Please enter a valid UK phone number (e.g. 07700 900123).")
    if len(set(digits[1:])) == 1:
        raise ValueError("Please enter a valid UK phone number.")
    return digits


def validate_address(value) -> str:
    v = _clean(value)
    if len(v) < 5:
        raise ValueError("Address is too short.")
    if len(v) > MAX_ADDRESS:
        raise ValueError(f"Address must be {MAX_ADDRESS} characters or fewer.")
    if not _ADDRESS_RE.match(v):
        raise ValueError("Address contains characters that aren't allowed.")
    _reject_repetition(v, "Address")
    return v


def validate_city(value, required: bool = True) -> str:
    v = _clean(value)
    if not v:
        if required:
            raise ValueError("City / town is required.")
        return ""
    if len(v) < 2:
        raise ValueError("City / town is too short.")
    if len(v) > MAX_CITY:
        raise ValueError(f"City / town must be {MAX_CITY} characters or fewer.")
    if not _CITY_RE.match(v):
        raise ValueError("City / town can only contain letters, spaces, hyphens and apostrophes.")
    _reject_repetition(v, "City / town")
    return v


def validate_postcode(value, required: bool = True) -> str:
    v = _clean(value).upper()
    if not v:
        if required:
            raise ValueError("Postcode is required.")
        return ""
    if len(v) > MAX_POSTCODE or not _POSTCODE_RE.match(v):
        raise ValueError("Please enter a valid UK postcode (e.g. SW1A 1AA).")
    # Normalise to "OUTWARD INWARD"
    compact = v.replace(" ", "")
    return f"{compact[:-3]} {compact[-3:]}"


def validate_sort_code(value) -> str:
    raw = _clean(value)
    if not raw:
        raise ValueError("Sort code is required.")
    if not re.match(r"^[0-9 \-]+$", raw):
        raise ValueError("Sort code must be 6 digits (e.g. 12-34-56).")
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 6:
        raise ValueError("Sort code must be exactly 6 digits (e.g. 12-34-56).")
    return f"{digits[0:2]}-{digits[2:4]}-{digits[4:6]}"


def validate_account_number(value) -> str:
    raw = _clean(value)
    if not raw:
        raise ValueError("Account number is required.")
    if not re.match(r"^[0-9 \-]+$", raw):
        raise ValueError("Account number must be 8 digits.")
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 8:
        raise ValueError("Account number must be exactly 8 digits.")
    return digits


def validate_customer_form(data: dict) -> tuple[dict, dict]:
    """
    Validate the full website order form in one go.

    `data` keys: full_name, email, phone, address, city, postcode,
                 account_name, sort_code, account_number.
    Returns (cleaned_values, errors) where errors maps field name -> message.
    An empty errors dict means everything passed.
    """
    checks = {
        "full_name":      lambda: validate_name(data.get("full_name"), "Full name"),
        "email":          lambda: validate_email(data.get("email"), required=True),
        "phone":          lambda: validate_phone(data.get("phone")),
        "address":        lambda: validate_address(data.get("address")),
        "city":           lambda: validate_city(data.get("city"), required=True),
        "postcode":       lambda: validate_postcode(data.get("postcode"), required=True),
        "account_name":   lambda: validate_name(data.get("account_name"), "Account name"),
        "sort_code":      lambda: validate_sort_code(data.get("sort_code")),
        "account_number": lambda: validate_account_number(data.get("account_number")),
    }
    cleaned, errors = {}, {}
    for field, check in checks.items():
        try:
            cleaned[field] = check()
        except ValueError as e:
            errors[field] = str(e)
            cleaned[field] = _clean(data.get(field))
    return cleaned, errors
