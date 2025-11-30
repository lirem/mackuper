"""
Encryption utilities for securing sensitive data (AWS keys, SSH credentials).
Uses Fernet symmetric encryption with a master key derived from the admin password.
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoManager:
    """Handles encryption and decryption of sensitive data."""

    def __init__(self):
        self._fernet = None
        self._salt = None

    def initialize(self, password: str, salt: bytes = None) -> bytes:
        """
        Initialize the encryption manager with a password.

        Args:
            password: Admin password to derive encryption key from
            salt: Optional salt (if None, generates new one)

        Returns:
            The salt used (save this to database on first setup)
        """
        if salt is None:
            salt = os.urandom(16)

        self._salt = salt

        # Derive a 32-byte key from password using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended iterations for 2023+
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))

        self._fernet = Fernet(key)
        return salt

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted string

        Raises:
            RuntimeError: If crypto manager not initialized
        """
        if not self._fernet:
            raise RuntimeError("CryptoManager not initialized. Call initialize() first.")

        encrypted_bytes = self._fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt a string.

        Args:
            encrypted: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string

        Raises:
            RuntimeError: If crypto manager not initialized
            cryptography.fernet.InvalidToken: If decryption fails
        """
        if not self._fernet:
            raise RuntimeError("CryptoManager not initialized. Call initialize() first.")

        encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode())
        decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()

    @property
    def is_initialized(self) -> bool:
        """Check if the crypto manager has been initialized."""
        return self._fernet is not None


# Global instance to be initialized on login
crypto_manager = CryptoManager()
