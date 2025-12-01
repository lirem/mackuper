"""
Settings routes - AWS configuration and user settings management.
"""

import logging
import traceback
from datetime import datetime
from flask import Blueprint, jsonify, request, session, current_app
from flask_login import login_required, current_user

from app import db
from app.models import AWSSettings, User, EncryptionKey
from app.utils.crypto import crypto_manager
from app.backup.storage import S3Storage, StorageError
from app.auth import hash_password, validate_password_strength


bp = Blueprint('settings', __name__, url_prefix='/api/settings')
logger = logging.getLogger(__name__)


@bp.route('/aws', methods=['GET'])
@login_required
def get_aws_settings():
    """
    Get AWS settings (credentials are not returned).

    Returns:
        JSON with AWS configuration (without sensitive data)
    """
    settings = AWSSettings.query.first()

    if not settings:
        return jsonify({
            'configured': False,
            'bucket_name': None,
            'region': None
        })

    # Re-initialize crypto_manager if needed
    if not crypto_manager.is_initialized and 'user_password' in session:
        encryption_key = EncryptionKey.query.first()
        if encryption_key:
            crypto_manager.initialize(session['user_password'], encryption_key.key_encrypted)

    # Generate hints if crypto_manager is initialized
    access_key_hint = None
    secret_key_hint = None

    if crypto_manager.is_initialized:
        try:
            access_key = crypto_manager.decrypt(settings.access_key_encrypted)
            secret_key = crypto_manager.decrypt(settings.secret_key_encrypted)

            # Show first 3 and last 3 characters for access key
            if len(access_key) > 6:
                access_key_hint = f"{access_key[:3]}***{access_key[-3:]}"
            else:
                access_key_hint = "***"

            # Show asterisks for secret key
            secret_key_hint = "***" + "*" * min(len(secret_key), 20)
        except Exception:
            # Fallback to generic indicator
            access_key_hint = '••• configured •••'
            secret_key_hint = '••• configured •••'
    else:
        # If crypto_manager not initialized, show generic indicator
        access_key_hint = '••• configured •••'
        secret_key_hint = '••• configured •••'

    return jsonify({
        'configured': True,
        'bucket_name': settings.bucket_name,
        'region': settings.region,
        'access_key_hint': access_key_hint,
        'secret_key_hint': secret_key_hint,
        'updated_at': settings.updated_at.isoformat()
    })


@bp.route('/aws', methods=['POST'])
@login_required
def update_aws_settings():
    """
    Update AWS settings.

    Request body:
        - access_key: AWS access key ID (required)
        - secret_key: AWS secret access key (required)
        - bucket_name: S3 bucket name (required)
        - region: AWS region (required)

    Returns:
        JSON with success message
    """
    data = request.get_json()

    # Validate required fields
    required_fields = ['access_key', 'secret_key', 'bucket_name', 'region']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    # Check crypto manager is initialized
    if not crypto_manager.is_initialized:
        return jsonify({'error': 'Crypto manager not initialized'}), 500

    # Encrypt credentials
    access_key_encrypted = crypto_manager.encrypt(data['access_key'])
    secret_key_encrypted = crypto_manager.encrypt(data['secret_key'])

    # Get or create settings record
    settings = AWSSettings.query.first()

    if settings:
        # Update existing
        settings.access_key_encrypted = access_key_encrypted
        settings.secret_key_encrypted = secret_key_encrypted
        settings.bucket_name = data['bucket_name']
        settings.region = data['region']
    else:
        # Create new
        settings = AWSSettings(
            access_key_encrypted=access_key_encrypted,
            secret_key_encrypted=secret_key_encrypted,
            bucket_name=data['bucket_name'],
            region=data['region']
        )
        db.session.add(settings)

    db.session.commit()

    return jsonify({'message': 'AWS settings updated successfully'})


@bp.route('/aws/test', methods=['POST'])
@login_required
def test_aws_connection():
    """
    Test AWS S3 connection.

    Can test with provided credentials or existing settings.

    Request body (optional):
        - access_key: AWS access key ID
        - secret_key: AWS secret access key
        - bucket_name: S3 bucket name
        - region: AWS region

    If no credentials provided, uses existing settings.

    Returns:
        JSON with test result
    """
    try:
        logger.info("AWS connection test started")

        # Handle empty request body gracefully
        try:
            data = request.get_json(silent=True) or {}
        except Exception as e:
            logger.warning(f"Failed to parse JSON request body: {str(e)}")
            data = {}

        # Determine which credentials to use
        if all(k in data for k in ['access_key', 'secret_key', 'bucket_name', 'region']):
            logger.info("Using provided credentials for test")
            access_key = data['access_key']
            secret_key = data['secret_key']
            bucket_name = data['bucket_name']
            region = data['region']
        else:
            logger.info("Using existing settings for test")
            settings = AWSSettings.query.first()
            if not settings:
                logger.warning("AWS settings not configured")
                return jsonify({'error': 'AWS settings not configured'}), 400

            # Re-initialize crypto_manager if needed
            if not crypto_manager.is_initialized:
                logger.info("Crypto manager not initialized, attempting initialization")
                encryption_key = EncryptionKey.query.first()
                if encryption_key and 'user_password' in session:
                    crypto_manager.initialize(session['user_password'], encryption_key.key_encrypted)
                    logger.info("Crypto manager initialized successfully")
                else:
                    logger.error("Cannot initialize crypto manager - session expired")
                    return jsonify({'error': 'Session expired. Please log out and log back in.'}), 401

            try:
                access_key = crypto_manager.decrypt(settings.access_key_encrypted)
                secret_key = crypto_manager.decrypt(settings.secret_key_encrypted)
                logger.info("Credentials decrypted successfully")
            except Exception as e:
                logger.error(f"Failed to decrypt credentials: {str(e)}")
                logger.debug(traceback.format_exc())
                return jsonify({'error': f'Failed to decrypt credentials: {str(e)}'}), 500

            bucket_name = settings.bucket_name
            region = settings.region

        logger.info(f"Testing connection to bucket: {bucket_name} in region: {region}")

        # Test connection
        try:
            s3_storage = S3Storage(access_key, secret_key, bucket_name, region)
            logger.info("S3Storage instance created successfully")

            s3_storage.test_connection()
            logger.info("S3 connection test successful")

            return jsonify({
                'success': True,
                'message': f'Successfully connected to S3 bucket: {bucket_name}'
            })

        except StorageError as e:
            logger.warning(f"Storage error during test: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}")
            logger.debug(traceback.format_exc())
            return jsonify({
                'success': False,
                'error': f'Connection test failed: {str(e)}'
            }), 500

    except Exception as e:
        # Catch-all for any unexpected errors
        logger.error(f"Unhandled exception in test_aws_connection: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@bp.route('/password', methods=['POST'])
@login_required
def change_password():
    """
    Change user password.

    Request body:
        - current_password: Current password (required)
        - new_password: New password (required)

    Returns:
        JSON with success message
    """
    data = request.get_json()

    # Validate required fields
    if not data.get('current_password'):
        return jsonify({'error': 'Current password is required'}), 400

    if not data.get('new_password'):
        return jsonify({'error': 'New password is required'}), 400

    # Get current user from database
    user = User.query.get(current_user.id)

    # Verify current password
    from app.auth import verify_password
    if not verify_password(user.password_hash, data['current_password']):
        return jsonify({'error': 'Current password is incorrect'}), 400

    # Validate new password
    is_valid, error = validate_password_strength(data['new_password'])
    if not is_valid:
        return jsonify({'error': error}), 400

    # Hash and save new password
    user.password_hash = hash_password(data['new_password'])

    # Update encrypted password storage
    try:
        from app.utils.master_key import get_master_key_manager

        # Re-initialize crypto manager with new password
        encryption_key = EncryptionKey.query.first()
        if encryption_key:
            # Re-initialize crypto manager with new password
            crypto_manager.initialize(data['new_password'], encryption_key.key_encrypted)

            # Update session password
            session['user_password'] = data['new_password']

            # Save encrypted password
            master_key_manager = get_master_key_manager(current_app)
            encrypted_password = master_key_manager.encrypt_password(data['new_password'])
            encryption_key.password_encrypted = encrypted_password
            encryption_key.updated_at = datetime.utcnow()

            logger.info("Encrypted password updated after password change")

    except Exception as e:
        logger.error(f"Failed to update encrypted password: {e}")
        # Don't fail the password change, but warn the user
        db.session.commit()  # Commit password hash change
        return jsonify({'message': 'Password changed but auto-unlock may not work. Please re-login.'}), 200

    db.session.commit()

    return jsonify({'message': 'Password changed successfully'})


@bp.route('/about', methods=['GET'])
@login_required
def get_about():
    """
    Get application information.

    Returns:
        JSON with app details
    """
    return jsonify({
        'app_name': 'Mackuper',
        'version': '1.0.0',
        'description': 'Docker-based backup solution for AWS S3',
        'author': 'Mackuper Team'
    })
