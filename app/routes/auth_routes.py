"""
Authentication routes: login, logout, and first-run setup wizard.
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required
from app import db
from app.models import User, AWSSettings, EncryptionKey
from app.auth import hash_password, verify_password, validate_password_strength, UserModel
from app.utils.crypto import crypto_manager
import boto3
from botocore.exceptions import ClientError


bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler."""

    # Check if setup is needed (no users exist)
    if User.query.count() == 0:
        return redirect(url_for('auth.setup'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('login.html')

        # Find user
        user = User.query.filter_by(username=username).first()

        if not user or not verify_password(user.password_hash, password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        # Initialize crypto manager with user's password
        encryption_key = EncryptionKey.query.first()
        if encryption_key:
            crypto_manager.initialize(password, encryption_key.key_encrypted)

        # Trigger deferred SSH password migration (for jobs that couldn't be migrated during startup)
        try:
            from app.migrations import _migrate_ssh_passwords
            _migrate_ssh_passwords()
        except Exception as e:
            current_app.logger.warning(f"Failed to migrate SSH passwords on login: {e}")
            # Don't fail login if migration fails

        # Save encrypted password for auto-unlock on startup
        try:
            from app.utils.master_key import get_master_key_manager

            master_key_manager = get_master_key_manager(current_app)
            encrypted_password = master_key_manager.encrypt_password(password)

            # Update the encryption_key record with encrypted password
            if encryption_key:
                encryption_key.password_encrypted = encrypted_password
                encryption_key.updated_at = datetime.utcnow()
                db.session.commit()
                current_app.logger.info("Encrypted password saved for auto-unlock")

        except Exception as e:
            # Don't fail login if password encryption fails
            current_app.logger.error(f"Failed to save encrypted password: {e}")
            flash('Warning: Auto-unlock may not work on restart', 'warning')

        # Store password in session for re-initialization
        session['user_password'] = password

        # Log user in
        login_user(UserModel(user), remember=True)
        flash('Login successful!', 'success')

        # Redirect to next page or home (dashboard will be added in Phase 5)
        next_page = request.args.get('next')
        return redirect(next_page) if next_page else redirect('/')

    return render_template('login.html')


@bp.route('/')
@login_required
def dashboard():
    """Main application dashboard."""
    return render_template('app.html')


@bp.route('/logout')
@login_required
def logout():
    """Logout handler."""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """
    First-run setup wizard (3 steps).
    Only accessible if no users exist in the database.
    """

    # Redirect if setup already completed
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        step = request.form.get('step', '1')

        # Step 1: Create admin account
        if step == '1':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')

            # Validate inputs
            if not username:
                flash('Username is required.', 'error')
                return render_template('setup.html', step=1)

            if password != password_confirm:
                flash('Passwords do not match.', 'error')
                return render_template('setup.html', step=1)

            # Validate password strength
            is_valid, error_msg = validate_password_strength(password)
            if not is_valid:
                flash(error_msg, 'error')
                return render_template('setup.html', step=1)

            # Store in session temporarily (will save after Step 3)
            session['setup_username'] = username
            session['setup_password'] = password

            return render_template('setup.html', step=2)

        # Step 2: Configure AWS credentials
        elif step == '2':
            access_key = request.form.get('access_key', '').strip()
            secret_key = request.form.get('secret_key', '').strip()
            bucket_name = request.form.get('bucket_name', '').strip()
            region = request.form.get('region', 'us-east-1').strip()

            # Validate inputs
            if not all([access_key, secret_key, bucket_name, region]):
                flash('All AWS fields are required.', 'error')
                return render_template('setup.html', step=2)

            # Store in session temporarily
            session['setup_aws_access_key'] = access_key
            session['setup_aws_secret_key'] = secret_key
            session['setup_aws_bucket_name'] = bucket_name
            session['setup_aws_region'] = region

            return render_template('setup.html', step=3)

        # Step 3: Test S3 connection and save everything
        elif step == '3':
            try:
                # Test S3 connection
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=session.get('setup_aws_access_key'),
                    aws_secret_access_key=session.get('setup_aws_secret_key'),
                    region_name=session.get('setup_aws_region')
                )

                # Test bucket access
                s3_client.head_bucket(Bucket=session.get('setup_aws_bucket_name'))

                # Connection successful - save everything to database
                username = session.get('setup_username')
                password = session.get('setup_password')

                # Create user
                user = User(
                    username=username,
                    password_hash=hash_password(password)
                )
                db.session.add(user)

                # Initialize crypto manager and create encryption key
                salt = crypto_manager.initialize(password)
                encryption_key = EncryptionKey(key_encrypted=salt)
                db.session.add(encryption_key)

                # Save encrypted password for auto-unlock
                try:
                    from app.utils.master_key import get_master_key_manager

                    master_key_manager = get_master_key_manager(current_app)
                    encrypted_password = master_key_manager.encrypt_password(password)
                    encryption_key.password_encrypted = encrypted_password

                except Exception as e:
                    # Log but don't fail setup
                    print(f"Warning: Failed to save encrypted password during setup: {e}")

                # Encrypt and save AWS settings
                aws_settings = AWSSettings(
                    access_key_encrypted=crypto_manager.encrypt(session.get('setup_aws_access_key')),
                    secret_key_encrypted=crypto_manager.encrypt(session.get('setup_aws_secret_key')),
                    bucket_name=session.get('setup_aws_bucket_name'),
                    region=session.get('setup_aws_region')
                )
                db.session.add(aws_settings)

                db.session.commit()

                # Clear session data
                session.pop('setup_username', None)
                session.pop('setup_password', None)
                session.pop('setup_aws_access_key', None)
                session.pop('setup_aws_secret_key', None)
                session.pop('setup_aws_bucket_name', None)
                session.pop('setup_aws_region', None)

                flash('Setup completed successfully! Please log in.', 'success')
                return redirect(url_for('auth.login'))

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == '403':
                    flash('Access denied. Check your AWS credentials and bucket permissions.', 'error')
                elif error_code == '404':
                    flash('Bucket not found. Please verify the bucket name.', 'error')
                else:
                    flash(f'AWS connection failed: {str(e)}', 'error')
                return render_template('setup.html', step=3, test_failed=True)

            except Exception as e:
                flash(f'Setup failed: {str(e)}', 'error')
                return render_template('setup.html', step=3, test_failed=True)

    # GET request - show step 1
    return render_template('setup.html', step=1)
