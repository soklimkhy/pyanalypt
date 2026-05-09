import re
from datetime import date
from django.core.exceptions import ValidationError

def validate_birthday_not_future(value):
    """
    Validator to ensure birthday is not in the future and within a reasonable age range.
    """
    if not value:
        return
    today = date.today()
    if value >= today:
        raise ValidationError("Birthday must be in the past.")
    if (today - value).days > 365 * 120:
        raise ValidationError("Enter a valid date of birth (max 120 years).")

def sanitize_username(username_base):
    """
    Sanitize a string to be used as a base for a username.
    Matches the RegexValidator in models.py: r"^[a-zA-Z0-9._-]+$"
    """
    # Replace any character that's not a letter, number, dot, underscore, or hyphen with an underscore.
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", username_base)
    # Ensure it doesn't start or end with a prohibited character if needed, though the regex is broad.
    return sanitized
