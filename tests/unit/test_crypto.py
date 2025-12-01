"""
Unit tests for cryptography module (app/utils/crypto.py).

Tests CryptoManager for encrypting/decrypting sensitive data.
"""

import pytest
from cryptography.fernet import InvalidToken

from app.utils.crypto import CryptoManager


class TestCryptoManagerInitialization:
    """Test CryptoManager initialization."""

    def test_crypto_manager_initialize_without_salt(self):
        """Test initialization without providing salt generates new salt."""
        cm = CryptoManager()
        salt = cm.initialize('test_password_123')

        assert salt is not None
        assert isinstance(salt, bytes)
        assert len(salt) == 16  # PBKDF2 salt is 16 bytes

    def test_crypto_manager_initialize_with_salt(self):
        """Test initialization with provided salt uses that salt."""
        cm = CryptoManager()
        provided_salt = b'1234567890123456'  # 16 bytes

        returned_salt = cm.initialize('test_password_123', salt=provided_salt)

        assert returned_salt == provided_salt

    def test_crypto_manager_initialize_sets_initialized(self):
        """Test initialization sets is_initialized property to True."""
        cm = CryptoManager()

        assert cm.is_initialized is False

        cm.initialize('test_password_123')

        assert cm.is_initialized is True

    def test_crypto_manager_different_passwords_different_keys(self):
        """Test that different passwords produce different encryption results."""
        plaintext = "secret_data"

        # Initialize with password 1
        cm1 = CryptoManager()
        cm1.initialize('password1')
        encrypted1 = cm1.encrypt(plaintext)

        # Initialize with password 2
        cm2 = CryptoManager()
        cm2.initialize('password2')
        encrypted2 = cm2.encrypt(plaintext)

        # Encrypted values should be different
        assert encrypted1 != encrypted2


class TestCryptoManagerEncryption:
    """Test CryptoManager encryption functionality."""

    def test_encrypt_encrypts_data(self):
        """Test that encrypt() returns encrypted data different from plaintext."""
        cm = CryptoManager()
        cm.initialize('test_password_123')

        plaintext = "sensitive_aws_key_12345"
        encrypted = cm.encrypt(plaintext)

        assert encrypted != plaintext
        assert isinstance(encrypted, str)
        assert len(encrypted) > len(plaintext)

    def test_encrypt_without_initialization_raises_error(self):
        """Test that encrypting without initialization raises RuntimeError."""
        cm = CryptoManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            cm.encrypt("test_data")

    def test_encrypt_same_data_multiple_times(self):
        """Test encrypting the same data multiple times produces different ciphertexts."""
        cm = CryptoManager()
        cm.initialize('test_password_123')

        plaintext = "same_data"
        encrypted1 = cm.encrypt(plaintext)
        encrypted2 = cm.encrypt(plaintext)

        # Fernet includes a timestamp, so encryptions will differ
        assert encrypted1 != encrypted2


class TestCryptoManagerDecryption:
    """Test CryptoManager decryption functionality."""

    def test_decrypt_recovers_original_data(self):
        """Test that decrypt() recovers the original plaintext."""
        cm = CryptoManager()
        cm.initialize('test_password_123')

        plaintext = "aws_secret_key_XYZ123"
        encrypted = cm.encrypt(plaintext)
        decrypted = cm.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_without_initialization_raises_error(self):
        """Test that decrypting without initialization raises RuntimeError."""
        cm = CryptoManager()

        with pytest.raises(RuntimeError, match="not initialized"):
            cm.decrypt("encrypted_data")

    def test_decrypt_with_wrong_password_raises_error(self):
        """Test that decrypting with wrong password raises InvalidToken error."""
        # Encrypt with password1
        cm1 = CryptoManager()
        cm1.initialize('password1')
        encrypted = cm1.encrypt("secret_data")

        # Try to decrypt with password2
        cm2 = CryptoManager()
        cm2.initialize('password2')

        with pytest.raises(InvalidToken):
            cm2.decrypt(encrypted)

    def test_decrypt_with_invalid_data_raises_error(self):
        """Test that decrypting invalid data raises error."""
        cm = CryptoManager()
        cm.initialize('test_password_123')

        # Invalid data can raise either InvalidToken or other base64/decoding errors
        with pytest.raises(Exception):
            cm.decrypt("this_is_not_encrypted_data")


class TestCryptoManagerFullCycle:
    """Test complete encryption/decryption workflows."""

    def test_encrypt_decrypt_cycle_preserves_data(self):
        """Test that encrypt -> decrypt preserves the original data."""
        cm = CryptoManager()
        cm.initialize('admin_password_secure')

        test_cases = [
            "simple_text",
            "AWS_ACCESS_KEY_123456",
            "complex!@#$%^&*()_+characters",
            "unicode_テスト_文字",
            "long_" * 100 + "text",
            "",  # Empty string
        ]

        for plaintext in test_cases:
            encrypted = cm.encrypt(plaintext)
            decrypted = cm.decrypt(encrypted)

            assert decrypted == plaintext, f"Failed for: {plaintext}"

    def test_encrypt_decrypt_with_same_salt(self):
        """Test that using same salt allows decryption with same password."""
        plaintext = "important_secret_key"

        # Encrypt with cm1
        cm1 = CryptoManager()
        salt = cm1.initialize('my_password')
        encrypted = cm1.encrypt(plaintext)

        # Decrypt with cm2 using same password and salt
        cm2 = CryptoManager()
        cm2.initialize('my_password', salt=salt)
        decrypted = cm2.decrypt(encrypted)

        assert decrypted == plaintext

    def test_is_initialized_property(self):
        """Test is_initialized property reflects initialization state."""
        cm = CryptoManager()

        # Before initialization
        assert cm.is_initialized is False

        # After initialization
        cm.initialize('test_password')
        assert cm.is_initialized is True

    def test_multiple_encrypt_decrypt_operations(self):
        """Test multiple encrypt/decrypt operations in sequence."""
        cm = CryptoManager()
        cm.initialize('test_password_123')

        # Encrypt multiple values
        data1 = "access_key_1"
        data2 = "secret_key_2"
        data3 = "session_token_3"

        enc1 = cm.encrypt(data1)
        enc2 = cm.encrypt(data2)
        enc3 = cm.encrypt(data3)

        # All encrypted values should be different
        assert enc1 != enc2 != enc3

        # Decrypt in different order
        assert cm.decrypt(enc3) == data3
        assert cm.decrypt(enc1) == data1
        assert cm.decrypt(enc2) == data2
