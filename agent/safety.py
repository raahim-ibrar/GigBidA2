import re

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
PAYMENT = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
INJECTION = re.compile(
    r"ignore (?:all |any |the )?(?:previous|prior|system) instructions|system prompt|"
    r"reveal (?:your |the )?(?:password|secret|token)|<\|(?:system|im_start)\|>",
    re.I,
)
GUARANTEE = re.compile(r"\b(?:guarantee(?:d)?|100% success|risk[- ]free)\b", re.I)
OFF_PLATFORM = re.compile(
    r"\b(?:telegram|whatsapp|pay outside|off.platform payment|unpaid test|free sample work)\b", re.I
)
EXPERIENCE = re.compile(
    r"\b(?:I|we|my|our)\b.*\b(?:built|developed|worked|years|experience|implemented|delivered|created|trained|deployed|led|achieved)\b",
    re.I,
)
SECRET_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "secret",
    "client_secret",
    "authorization",
    "api_key",
    "cookie",
    "set-cookie",
}


def mask_pii(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.casefold() in SECRET_KEYS or key.casefold().endswith(("_password", "_secret"))
            else mask_pii(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_pii(item) for item in value]
    if isinstance(value, str):
        return PAYMENT.sub("[PAYMENT]", PHONE.sub("[PHONE]", EMAIL.sub("[EMAIL]", value)))
    return value
