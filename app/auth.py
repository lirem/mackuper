"""
Authentication utilities for Flask-Login integration and password management.
"""

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.models import User


def hash_password(password: str) -> str:
    """
    Hash a password using werkzeug's pbkdf2:sha256.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return generate_password_hash(password, method='pbkdf2:sha256')


def verify_password(password_hash: str, password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password_hash: Stored password hash
        password: Plain text password to verify

    Returns:
        True if password matches, False otherwise
    """
    return check_password_hash(password_hash, password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    return True, ""


class UserModel(UserMixin):
    """
    Flask-Login user wrapper for the User database model.
    """

    def __init__(self, user: User):
        self.user = user

    def get_id(self):
        """Return user ID as required by Flask-Login."""
        return str(self.user.id)

    @property
    def id(self):
        return self.user.id

    @property
    def username(self):
        return self.user.username
