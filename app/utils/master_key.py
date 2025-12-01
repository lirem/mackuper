"""
Master key encryption utilities.

Uses Flask SECRET_KEY to encrypt/decrypt sensitive data for persistent storage.
This is separate from crypto.py which uses user passwords for AWS credential encryption.
"""

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class MasterKeyManager:
    """
    Handles encryption/decryption using Flask SECRET_KEY as master key.

    Used for encrypting the user password for persistent storage.
    This is NOT the same as CryptoManager which uses the user password.
    """

    def __init__(self, secret_key: str):
        """
        Initialize with Flask SECRET_KEY.

        Args:
            secret_key: Flask app SECRET_KEY (from config or /data/.secret_key)
        """
        # Derive a consistent Fernet key from SECRET_KEY
        # Use a fixed salt since SECRET_KEY itself is the secret
        fixed_salt = b'mackuper_master_key_salt_v1'  # Version tagged for future rotation

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=fixed_salt,
            iterations=100000,  # Fewer iterations than user password (this is already protected by SECRET_KEY)
        )

        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        self._fernet = Fernet(key)

    def encrypt_password(self, plaintext_password: str) -> str:
        """
        Encrypt a password for persistent storage.

        Args:
            plaintext_password: User's password in plaintext

        Returns:
            Base64-encoded encrypted password
        """
        encrypted_bytes = self._fernet.encrypt(plaintext_password.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    def decrypt_password(self, encrypted_password: str) -> str:
        """
        Decrypt a stored password.

        Args:
            encrypted_password: Base64-encoded encrypted password

        Returns:
            Plaintext password

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode())
        decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()


def get_master_key_manager(app) -> MasterKeyManager:
    """
    Factory function to create MasterKeyManager from Flask app config.

    Args:
        app: Flask application instance

    Returns:
        MasterKeyManager instance

    Raises:
        RuntimeError: If SECRET_KEY not configured
    """
    secret_key = app.config.get('SECRET_KEY')

    if not secret_key:
        raise RuntimeError("SECRET_KEY not configured - cannot initialize MasterKeyManager")

    return MasterKeyManager(secret_key)
