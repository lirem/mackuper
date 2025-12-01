"""
Unit tests for authentication module (app/auth.py).

Tests password hashing, verification, validation, and UserModel wrapper.
"""

import pytest
from app.auth import hash_password, verify_password, validate_password_strength, UserModel
from app.models import User


class TestPasswordHashing:
    """Test password hashing and verification functions."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_returns_different_from_plain(self):
        """Test that hashed password is different from plain password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert hashed != password

    def test_hash_password_generates_unique_hashes(self):
        """Test that same password generates different hashes (due to salt)."""
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to random salt
        assert hash1 != hash2

    def test_verify_password_with_correct_password(self):
        """Test password verification with correct password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password(hashed, password) is True

    def test_verify_password_with_incorrect_password(self):
        """Test password verification with incorrect password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password(hashed, "WrongPassword456") is False

    def test_password_hash_verify_cycle(self):
        """Test complete hash and verify workflow."""
        password = "ComplexP@ssw0rd!"
        hashed = hash_password(password)

        # Correct password should verify
        assert verify_password(hashed, password) is True

        # Wrong passwords should not verify
        assert verify_password(hashed, "ComplexP@ssw0rd") is False
        assert verify_password(hashed, "complexp@ssw0rd!") is False
        assert verify_password(hashed, "") is False


class TestPasswordValidation:
    """Test password strength validation."""

    def test_validate_password_too_short(self):
        """Test password validation rejects passwords shorter than 8 characters."""
        is_valid, message = validate_password_strength("Short1")

        assert is_valid is False
        assert "8 characters" in message

    def test_validate_password_no_uppercase(self):
        """Test password validation rejects passwords without uppercase letters."""
        is_valid, message = validate_password_strength("nouppercase1")

        assert is_valid is False
        assert "uppercase" in message.lower()

    def test_validate_password_no_lowercase(self):
        """Test password validation rejects passwords without lowercase letters."""
        is_valid, message = validate_password_strength("NOLOWERCASE1")

        assert is_valid is False
        assert "lowercase" in message.lower()

    def test_validate_password_no_digit(self):
        """Test password validation rejects passwords without digits."""
        is_valid, message = validate_password_strength("NoDigitsHere")

        assert is_valid is False
        assert "digit" in message.lower()

    def test_validate_password_valid_minimum(self):
        """Test password validation accepts minimum valid password."""
        is_valid, message = validate_password_strength("ValidP1!")

        assert is_valid is True
        assert message == ""

    def test_validate_password_valid_complex(self):
        """Test password validation accepts complex valid password."""
        is_valid, message = validate_password_strength("MyC0mpl3x!P@ssw0rd")

        assert is_valid is True
        assert message == ""

    @pytest.mark.parametrize("password,expected_valid,expected_error_keyword", [
        ("short", False, "8 characters"),
        ("nouppercase123", False, "uppercase"),
        ("NOLOWERCASE123", False, "lowercase"),
        ("NoDigitsHere", False, "digit"),
        ("ValidPass1", True, ""),
        ("AnotherValid123", True, ""),
        ("C0mpl3x!P@ss", True, ""),
    ])
    def test_validate_password_various_cases(self, password, expected_valid, expected_error_keyword):
        """Test password validation with various input cases."""
        is_valid, message = validate_password_strength(password)

        assert is_valid == expected_valid
        if expected_error_keyword:
            assert expected_error_keyword.lower() in message.lower()


class TestUserModel:
    """Test UserModel wrapper for Flask-Login."""

    def test_user_model_get_id(self, db):
        """Test UserModel.get_id() returns string ID."""
        user = User(username='testuser', password_hash='hashed_password')
        db.session.add(user)
        db.session.commit()

        user_model = UserModel(user)

        assert user_model.get_id() == str(user.id)
        assert isinstance(user_model.get_id(), str)

    def test_user_model_id_property(self, db):
        """Test UserModel.id property returns integer ID."""
        user = User(username='testuser', password_hash='hashed_password')
        db.session.add(user)
        db.session.commit()

        user_model = UserModel(user)

        assert user_model.id == user.id
        assert isinstance(user_model.id, int)

    def test_user_model_username_property(self, db):
        """Test UserModel.username property returns username."""
        user = User(username='testuser', password_hash='hashed_password')
        db.session.add(user)
        db.session.commit()

        user_model = UserModel(user)

        assert user_model.username == 'testuser'
        assert isinstance(user_model.username, str)

    def test_user_model_wraps_user_object(self, db):
        """Test UserModel correctly wraps User object."""
        user = User(username='testuser', password_hash='hashed_password')
        db.session.add(user)
        db.session.commit()

        user_model = UserModel(user)

        assert user_model.user is user
        assert user_model.user.username == 'testuser'
