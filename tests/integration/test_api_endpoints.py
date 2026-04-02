"""
Integration tests for all HTTP route blueprints.

Covers happy-path behaviour and key error cases for:
  - Auth routes    (/login, /logout, /setup, /)
  - Dashboard API  (/api/dashboard/*)
  - Jobs API       (/api/jobs/*)
  - Settings API   (/api/settings/*)
  - History API    (/api/history/*)
"""

import os
import tempfile
import shutil
from unittest.mock import patch

import pytest

from app.models import EncryptionKey
from app.utils.crypto import crypto_manager


# ---------------------------------------------------------------------------
# Module-level fixtures that override the conftest ones for integration tests.
#
# The conftest `app` fixture calls create_app() first and then overrides
# SQLALCHEMY_DATABASE_URI.  create_app() runs init_database_schema() and the
# auto-unlock query inside its own app context using whatever URI was set at
# construction time.  When the URI is later replaced with sqlite:///:memory:
# those tables vanish, so every subsequent query fails with "no such table".
#
# The fix is to build the app once with the in-memory URI already in place.
# We do this by monkeypatching the config object before create_app() reads it.
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def app():
    """
    Flask app fixture for integration tests.

    Creates the application with a temp-directory-based SQLite database so
    that init_database_schema() and all subsequent route queries operate on
    the same database file.  Using a file (rather than :memory:) avoids the
    issue where create_app() tries to mkdir the parent of the DB path.
    """
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_integration.db')
    db_uri = f'sqlite:///{db_path}'

    # Patch the development config class before create_app() reads it so that
    # init_database_schema() and the auto-unlock query both use the temp file.
    from app import config as app_config
    original_uri = app_config.config['development'].SQLALCHEMY_DATABASE_URI
    original_temp = app_config.config['development'].TEMP_DIR
    original_backup = app_config.config['development'].LOCAL_BACKUP_DIR

    app_config.config['development'].SQLALCHEMY_DATABASE_URI = db_uri
    app_config.config['development'].TEMP_DIR = os.path.join(temp_dir, 'temp')
    app_config.config['development'].LOCAL_BACKUP_DIR = os.path.join(temp_dir, 'backups')

    try:
        from app import create_app

        flask_app = create_app('development')
        flask_app.config.update({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret-key-integration',
        })

        yield flask_app
    finally:
        app_config.config['development'].SQLALCHEMY_DATABASE_URI = original_uri
        app_config.config['development'].TEMP_DIR = original_temp
        app_config.config['development'].LOCAL_BACKUP_DIR = original_backup
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope='function')
def db(app):
    """Fresh database for each integration test."""
    from app import db as _db
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Test client bound to the integration app fixture."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope='function')
def authenticated_client(client, app, admin_user):
    """
    Return a test client that is fully logged in as the admin user.

    Steps:
    1. Create an EncryptionKey row so the login handler can initialise the
       global crypto_manager.
    2. Manually initialise the global crypto_manager with the admin password
       and the resulting salt so encrypted-credential endpoints work.
    3. POST form data to /login, which is the real login route.
    """
    with app.app_context():
        # Initialise the global crypto_manager and capture the derived salt.
        salt = crypto_manager.initialize('Admin123')

        # Persist an EncryptionKey record that the login route reads.
        enc_key = EncryptionKey(key_encrypted=salt)
        from app import db
        db.session.add(enc_key)
        db.session.commit()

    response = client.post(
        '/login',
        data={'username': 'admin', 'password': 'Admin123'},
        follow_redirects=False,
    )
    # A successful login should redirect (302) to '/'.
    assert response.status_code in (200, 302), (
        f"Login failed with status {response.status_code}: {response.data[:400]}"
    )

    return client


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

class TestAuthRoutes:
    """Tests for the auth blueprint (no url_prefix)."""

    # --- unauthenticated access ------------------------------------------

    def test_login_page_get(self, client, admin_user):
        """GET /login returns 200 for an unauthenticated visitor."""
        response = client.get('/login')
        assert response.status_code == 200

    def test_login_page_content_type(self, client, admin_user):
        """GET /login returns HTML."""
        response = client.get('/login')
        assert b'html' in response.content_type.lower().encode() or b'<html' in response.data.lower()

    # --- successful login --------------------------------------------------

    def test_login_valid_credentials_redirects(self, client, app, admin_user):
        """POST /login with valid credentials redirects away from login page."""
        with app.app_context():
            salt = crypto_manager.initialize('Admin123')
            enc_key = EncryptionKey(key_encrypted=salt)
            from app import db
            db.session.add(enc_key)
            db.session.commit()

        response = client.post(
            '/login',
            data={'username': 'admin', 'password': 'Admin123'},
            follow_redirects=False,
        )
        # A successful login must redirect (302), never re-render the login page (200)
        assert response.status_code == 302
        location = response.headers.get('Location', '')
        assert '/login' not in location, f"Login redirected back to login page: {location}"

    def test_login_redirects_to_home(self, client, app, admin_user):
        """POST /login follows redirect to the dashboard root '/'."""
        with app.app_context():
            salt = crypto_manager.initialize('Admin123')
            enc_key = EncryptionKey(key_encrypted=salt)
            from app import db
            db.session.add(enc_key)
            db.session.commit()

        response = client.post(
            '/login',
            data={'username': 'admin', 'password': 'Admin123'},
            follow_redirects=True,
        )
        assert response.status_code == 200
        # Must land on the dashboard — confirmed by logout link presence in app shell
        body = response.data.lower()
        assert b'logout' in body or b'dashboard' in body, (
            "Expected dashboard content after successful login"
        )

    # --- failed login ------------------------------------------------------

    def test_login_invalid_password(self, client, admin_user):
        """POST /login with a wrong password stays on the login page (no redirect)."""
        response = client.post(
            '/login',
            data={'username': 'admin', 'password': 'WrongPassword!'},
            follow_redirects=False,
        )
        # Should render login template again (200) — not redirect to home.
        assert response.status_code == 200
        assert b'Invalid' in response.data or b'invalid' in response.data

    def test_login_unknown_user(self, client, admin_user):
        """POST /login with an unknown username stays on the login page."""
        response = client.post(
            '/login',
            data={'username': 'nobody', 'password': 'Admin123'},
            follow_redirects=False,
        )
        assert response.status_code == 200

    def test_login_missing_fields(self, client, admin_user):
        """POST /login with empty credentials shows an error."""
        response = client.post(
            '/login',
            data={'username': '', 'password': ''},
            follow_redirects=False,
        )
        assert response.status_code == 200

    # --- open redirect regression ------------------------------------------

    def test_login_open_redirect_blocked(self, client, app, admin_user):
        """
        Regression: passing next=https://evil.com must NOT redirect to an
        external URL after successful login.
        """
        with app.app_context():
            salt = crypto_manager.initialize('Admin123')
            enc_key = EncryptionKey(key_encrypted=salt)
            from app import db
            db.session.add(enc_key)
            db.session.commit()

        response = client.post(
            '/login?next=https://evil.com',
            data={'username': 'admin', 'password': 'Admin123'},
            follow_redirects=False,
        )
        # Successful login must redirect (not 200)
        assert response.status_code in (301, 302, 303, 307, 308), (
            f"Expected a redirect after login, got {response.status_code}"
        )
        location = response.headers.get('Location', '')
        assert 'evil.com' not in location, (
            f"Open redirect vulnerability: redirected to {location}"
        )

    # --- session safety regression -----------------------------------------

    def test_login_session_does_not_store_plaintext_password(self, client, app, admin_user):
        """
        Regression: after login the session must NOT contain the key
        'user_password' in plaintext.
        """
        with app.app_context():
            salt = crypto_manager.initialize('Admin123')
            enc_key = EncryptionKey(key_encrypted=salt)
            from app import db
            db.session.add(enc_key)
            db.session.commit()

        with client.session_transaction() as pre_session:
            pre_session.clear()

        client.post(
            '/login',
            data={'username': 'admin', 'password': 'Admin123'},
            follow_redirects=False,
        )

        with client.session_transaction() as sess:
            assert 'user_password' not in sess, (
                "Session stores plaintext password — security regression"
            )

    # --- logout ------------------------------------------------------------

    def test_logout_redirects_to_login(self, authenticated_client):
        """GET /logout redirects to /login."""
        response = authenticated_client.get('/logout', follow_redirects=False)
        assert response.status_code in (301, 302, 303, 307, 308)
        location = response.headers.get('Location', '')
        assert 'login' in location

    def test_logout_unauthenticated_redirects(self, client, admin_user):
        """GET /logout when not logged in redirects to /login (Flask-Login behaviour)."""
        response = client.get('/logout', follow_redirects=False)
        assert response.status_code in (301, 302, 303, 307, 308)

    # --- dashboard root (protected) ----------------------------------------

    def test_dashboard_root_requires_auth(self, client, admin_user):
        """GET / when unauthenticated redirects to login."""
        response = client.get('/', follow_redirects=False)
        assert response.status_code in (301, 302, 303, 307, 308)

    def test_dashboard_root_authenticated(self, authenticated_client):
        """GET / when authenticated returns 200."""
        response = authenticated_client.get('/', follow_redirects=True)
        assert response.status_code == 200

    # --- setup wizard ------------------------------------------------------

    def test_setup_redirects_when_users_exist(self, client, admin_user):
        """GET /setup redirects to /login when a user already exists."""
        response = client.get('/setup', follow_redirects=False)
        assert response.status_code in (301, 302, 303, 307, 308)
        location = response.headers.get('Location', '')
        assert 'login' in location


# ---------------------------------------------------------------------------
# Dashboard routes  (/api/dashboard/*)
# ---------------------------------------------------------------------------

class TestDashboardRoutes:
    """Tests for the dashboard blueprint."""

    def test_overview_requires_auth(self, client, admin_user):
        """/api/dashboard/overview is protected."""
        response = client.get('/api/dashboard/overview')
        assert response.status_code in (301, 302, 401)

    def test_overview_returns_200(self, authenticated_client):
        """GET /api/dashboard/overview returns 200 with expected JSON keys."""
        response = authenticated_client.get('/api/dashboard/overview')
        assert response.status_code == 200
        data = response.get_json()
        assert 'total_jobs' in data
        assert 'active_jobs' in data

    def test_overview_json_content_type(self, authenticated_client):
        """GET /api/dashboard/overview has application/json content type."""
        response = authenticated_client.get('/api/dashboard/overview')
        assert 'application/json' in response.content_type

    def test_overview_counts_are_integers(self, authenticated_client, local_backup_job):
        """total_jobs and active_jobs are non-negative integers."""
        response = authenticated_client.get('/api/dashboard/overview')
        data = response.get_json()
        assert isinstance(data['total_jobs'], int)
        assert isinstance(data['active_jobs'], int)
        assert data['total_jobs'] >= 0
        assert data['active_jobs'] >= 0

    def test_statistics_requires_auth(self, client, admin_user):
        """/api/dashboard/statistics is protected."""
        response = client.get('/api/dashboard/statistics')
        assert response.status_code in (301, 302, 401)

    def test_statistics_returns_200(self, authenticated_client):
        """GET /api/dashboard/statistics returns 200 with expected keys."""
        response = authenticated_client.get('/api/dashboard/statistics')
        assert response.status_code == 200
        data = response.get_json()
        assert 'total_backups' in data
        assert 'successful_backups' in data

    def test_statistics_contains_all_fields(self, authenticated_client):
        """Statistics response contains the full expected field set."""
        response = authenticated_client.get('/api/dashboard/statistics')
        data = response.get_json()
        for key in ('total_backups', 'successful_backups', 'failed_backups',
                    'success_rate', 'total_size_gb',
                    'backups_last_7_days', 'backups_last_30_days'):
            assert key in data, f"Missing key: {key}"

    def test_recent_activity_requires_auth(self, client, admin_user):
        """/api/dashboard/recent-activity is protected."""
        response = client.get('/api/dashboard/recent-activity')
        assert response.status_code in (301, 302, 401)

    def test_recent_activity_returns_list(self, authenticated_client):
        """GET /api/dashboard/recent-activity returns 200 and a JSON list."""
        response = authenticated_client.get('/api/dashboard/recent-activity')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def test_recent_activity_with_history(self, authenticated_client, backup_history):
        """Recent-activity list is non-empty when history records exist."""
        response = authenticated_client.get('/api/dashboard/recent-activity')
        data = response.get_json()
        assert len(data) >= 1
        record = data[0]
        assert 'job_name' in record
        assert 'status' in record

    def test_scheduled_jobs_returns_200(self, authenticated_client):
        """GET /api/dashboard/scheduled-jobs returns 200."""
        response = authenticated_client.get('/api/dashboard/scheduled-jobs')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Jobs routes  (/api/jobs/*)
# ---------------------------------------------------------------------------

class TestJobsRoutes:
    """Tests for the jobs CRUD blueprint."""

    @pytest.fixture(autouse=True)
    def _patch_scheduler(self):
        """
        Suppress scheduler calls for all jobs mutation tests.

        create_job, update_job, delete_job, and toggle_job all call
        sync_backup_jobs() after persisting changes.  The scheduler is not
        initialised in tests, so we patch it out for the whole class.
        """
        with patch('app.routes.jobs_routes.sync_backup_jobs'):
            yield

    # --- auth enforcement --------------------------------------------------

    def test_list_jobs_requires_auth(self, client, admin_user):
        response = client.get('/api/jobs/')
        assert response.status_code in (301, 302, 401)

    # --- list --------------------------------------------------------------

    def test_list_jobs_empty(self, authenticated_client):
        """GET /api/jobs/ returns 200 and an empty list when no jobs exist."""
        response = authenticated_client.get('/api/jobs/')
        assert response.status_code == 200
        assert response.get_json() == []

    def test_list_jobs_with_fixture(self, authenticated_client, local_backup_job):
        """GET /api/jobs/ includes the fixture job."""
        response = authenticated_client.get('/api/jobs/')
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        names = [j['name'] for j in data]
        assert local_backup_job.name in names

    def test_list_jobs_schema(self, authenticated_client, local_backup_job):
        """Each job object contains the expected top-level keys."""
        response = authenticated_client.get('/api/jobs/')
        jobs = response.get_json()
        job = jobs[0]
        for key in ('id', 'name', 'enabled', 'source_type',
                    'compression_format', 'created_at', 'updated_at'):
            assert key in job, f"Missing key: {key}"

    # --- get single --------------------------------------------------------

    def test_get_job_returns_200(self, authenticated_client, local_backup_job):
        """GET /api/jobs/<id> returns 200 and correct job data."""
        response = authenticated_client.get(f'/api/jobs/{local_backup_job.id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == local_backup_job.id
        assert data['name'] == local_backup_job.name

    def test_get_job_includes_source_config(self, authenticated_client, local_backup_job):
        """GET /api/jobs/<id> response includes source_config."""
        response = authenticated_client.get(f'/api/jobs/{local_backup_job.id}')
        data = response.get_json()
        assert 'source_config' in data

    def test_get_job_not_found(self, authenticated_client):
        """GET /api/jobs/9999 returns 404."""
        response = authenticated_client.get('/api/jobs/9999')
        assert response.status_code == 404

    # --- create ------------------------------------------------------------

    def test_create_job_returns_201(self, authenticated_client):
        """POST /api/jobs/ with valid data returns 201."""
        payload = {
            'name': 'integration_test_job',
            'source_type': 'local',
            'source_config': {'paths': ['/tmp']},
            'compression_format': 'tar.gz',
        }
        response = authenticated_client.post(
            '/api/jobs/',
            json=payload,
        )
        assert response.status_code == 201
        data = response.get_json()
        assert 'id' in data

    def test_create_job_missing_name(self, authenticated_client):
        """POST /api/jobs/ without name returns 400."""
        payload = {
            'source_type': 'local',
            'source_config': {'paths': ['/tmp']},
            'compression_format': 'tar.gz',
        }
        response = authenticated_client.post('/api/jobs/', json=payload)
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_create_job_invalid_source_type(self, authenticated_client):
        """POST /api/jobs/ with unsupported source_type returns 400."""
        payload = {
            'name': 'bad_source_job',
            'source_type': 'ftp',
            'source_config': {},
            'compression_format': 'tar.gz',
        }
        response = authenticated_client.post('/api/jobs/', json=payload)
        assert response.status_code == 400

    def test_create_job_invalid_compression(self, authenticated_client):
        """POST /api/jobs/ with unsupported compression format returns 400."""
        payload = {
            'name': 'bad_fmt_job',
            'source_type': 'local',
            'source_config': {'paths': ['/tmp']},
            'compression_format': 'rar',
        }
        response = authenticated_client.post('/api/jobs/', json=payload)
        assert response.status_code == 400

    def test_create_job_duplicate_name(self, authenticated_client, local_backup_job):
        """POST /api/jobs/ with a duplicate name returns 400."""
        payload = {
            'name': local_backup_job.name,
            'source_type': 'local',
            'source_config': {'paths': ['/tmp']},
            'compression_format': 'zip',
        }
        response = authenticated_client.post('/api/jobs/', json=payload)
        assert response.status_code == 400
        assert 'error' in response.get_json()

    # --- update ------------------------------------------------------------

    def test_update_job_returns_200(self, authenticated_client, local_backup_job):
        """PUT /api/jobs/<id> with valid data returns 200."""
        response = authenticated_client.put(
            f'/api/jobs/{local_backup_job.id}',
            json={'description': 'Updated description'},
        )
        assert response.status_code == 200
        assert 'message' in response.get_json()

    def test_update_job_not_found(self, authenticated_client):
        """PUT /api/jobs/9999 returns 404."""
        response = authenticated_client.put('/api/jobs/9999', json={'description': 'x'})
        assert response.status_code == 404

    def test_update_job_persists_change(self, authenticated_client, local_backup_job, app):
        """After PUT /api/jobs/<id> the field change is readable via GET."""
        authenticated_client.put(
            f'/api/jobs/{local_backup_job.id}',
            json={'description': 'Persisted update'},
        )
        get_response = authenticated_client.get(f'/api/jobs/{local_backup_job.id}')
        assert get_response.get_json()['description'] == 'Persisted update'

    # --- delete ------------------------------------------------------------

    def test_delete_job_returns_200(self, authenticated_client, local_backup_job):
        """DELETE /api/jobs/<id> returns 200 and a success message."""
        response = authenticated_client.delete(f'/api/jobs/{local_backup_job.id}')
        assert response.status_code == 200
        assert 'message' in response.get_json()

    def test_delete_job_removes_from_list(self, authenticated_client, local_backup_job):
        """After DELETE /api/jobs/<id> the job no longer appears in GET /api/jobs/."""
        job_id = local_backup_job.id
        authenticated_client.delete(f'/api/jobs/{job_id}')
        response = authenticated_client.get('/api/jobs/')
        ids = [j['id'] for j in response.get_json()]
        assert job_id not in ids

    def test_delete_job_not_found(self, authenticated_client):
        """DELETE /api/jobs/9999 returns 404."""
        response = authenticated_client.delete('/api/jobs/9999')
        assert response.status_code == 404

    # --- toggle ------------------------------------------------------------

    def test_toggle_job_returns_200(self, authenticated_client, local_backup_job):
        """POST /api/jobs/<id>/toggle returns 200 with new enabled state."""
        original = local_backup_job.enabled
        response = authenticated_client.post(f'/api/jobs/{local_backup_job.id}/toggle')
        assert response.status_code == 200
        data = response.get_json()
        assert 'enabled' in data
        assert data['enabled'] != original

    # --- per-job history ---------------------------------------------------

    def test_job_history_returns_list(self, authenticated_client, local_backup_job, backup_history):
        """GET /api/jobs/<id>/history returns 200 and a JSON list."""
        response = authenticated_client.get(f'/api/jobs/{local_backup_job.id}/history')
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)


# ---------------------------------------------------------------------------
# Settings routes  (/api/settings/*)
# ---------------------------------------------------------------------------

class TestSettingsRoutes:
    """Tests for the settings blueprint."""

    # --- auth enforcement --------------------------------------------------

    def test_aws_settings_requires_auth(self, client, admin_user):
        response = client.get('/api/settings/aws')
        assert response.status_code in (301, 302, 401)

    def test_about_requires_auth(self, client, admin_user):
        response = client.get('/api/settings/about')
        assert response.status_code in (301, 302, 401)

    # --- GET aws -----------------------------------------------------------

    def test_get_aws_settings_no_config(self, authenticated_client):
        """GET /api/settings/aws returns 200 and configured=False when no record exists."""
        response = authenticated_client.get('/api/settings/aws')
        assert response.status_code == 200
        data = response.get_json()
        assert 'configured' in data

    def test_get_aws_settings_with_config(self, authenticated_client, aws_settings):
        """GET /api/settings/aws returns configured=True when a record exists."""
        response = authenticated_client.get('/api/settings/aws')
        assert response.status_code == 200
        data = response.get_json()
        assert data['configured'] is True
        assert 'bucket_name' in data
        assert 'region' in data

    def test_get_aws_settings_does_not_expose_secrets(self, authenticated_client, aws_settings):
        """GET /api/settings/aws must not return raw access_key or secret_key fields."""
        response = authenticated_client.get('/api/settings/aws')
        data = response.get_json()
        assert 'access_key' not in data
        assert 'secret_key' not in data

    # --- about -------------------------------------------------------------

    def test_get_about_returns_200(self, authenticated_client):
        """GET /api/settings/about returns 200."""
        response = authenticated_client.get('/api/settings/about')
        assert response.status_code == 200

    def test_get_about_contains_app_name(self, authenticated_client):
        """GET /api/settings/about response includes app_name."""
        response = authenticated_client.get('/api/settings/about')
        data = response.get_json()
        assert 'app_name' in data
        assert data['app_name'] == 'Mackuper'

    def test_get_about_contains_version(self, authenticated_client):
        """GET /api/settings/about response includes a version field."""
        response = authenticated_client.get('/api/settings/about')
        data = response.get_json()
        assert 'version' in data

    # --- POST aws ----------------------------------------------------------

    def test_update_aws_settings_missing_field(self, authenticated_client):
        """POST /api/settings/aws with a missing required field returns 400."""
        response = authenticated_client.post(
            '/api/settings/aws',
            json={
                'access_key': 'AKIAIOSFODNN7EXAMPLE',
                'secret_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                # bucket_name and region intentionally omitted
            },
        )
        assert response.status_code == 400

    # --- password change ---------------------------------------------------

    def test_change_password_wrong_current(self, authenticated_client):
        """POST /api/settings/password with wrong current_password returns 400."""
        response = authenticated_client.post(
            '/api/settings/password',
            json={
                'current_password': 'NotTheRightOne1',
                'new_password': 'NewPassword1',
            },
        )
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_change_password_missing_field(self, authenticated_client):
        """POST /api/settings/password without required fields returns 400."""
        response = authenticated_client.post(
            '/api/settings/password',
            json={'current_password': 'Admin123'},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# History routes  (/api/history/*)
# ---------------------------------------------------------------------------

class TestHistoryRoutes:
    """Tests for the history blueprint."""

    # --- auth enforcement --------------------------------------------------

    def test_list_history_requires_auth(self, client, admin_user):
        response = client.get('/api/history/')
        assert response.status_code in (301, 302, 401)

    # --- list --------------------------------------------------------------

    def test_list_history_empty(self, authenticated_client):
        """GET /api/history/ returns 200 with an empty records list."""
        response = authenticated_client.get('/api/history/')
        assert response.status_code == 200
        data = response.get_json()
        assert 'records' in data
        assert isinstance(data['records'], list)

    def test_list_history_metadata(self, authenticated_client):
        """GET /api/history/ response includes pagination metadata."""
        response = authenticated_client.get('/api/history/')
        data = response.get_json()
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data

    def test_list_history_with_fixture(self, authenticated_client, backup_history):
        """GET /api/history/ includes the fixture record."""
        response = authenticated_client.get('/api/history/')
        data = response.get_json()
        assert data['total'] >= 1
        assert len(data['records']) >= 1

    def test_list_history_record_schema(self, authenticated_client, backup_history):
        """History list records contain the expected fields."""
        response = authenticated_client.get('/api/history/')
        record = response.get_json()['records'][0]
        for key in ('id', 'job_id', 'job_name', 'status', 'started_at'):
            assert key in record, f"Missing key: {key}"

    def test_list_history_status_filter(self, authenticated_client, backup_history):
        """GET /api/history/?status=success filters correctly."""
        response = authenticated_client.get('/api/history/?status=success')
        assert response.status_code == 200
        data = response.get_json()
        for record in data['records']:
            assert record['status'] == 'success'

    def test_list_history_invalid_status_filter(self, authenticated_client):
        """GET /api/history/?status=bogus returns 400."""
        response = authenticated_client.get('/api/history/?status=bogus')
        assert response.status_code == 400

    # --- detail ------------------------------------------------------------

    def test_get_history_detail_returns_200(self, authenticated_client, backup_history):
        """GET /api/history/<id> returns 200 with full record."""
        response = authenticated_client.get(f'/api/history/{backup_history.id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['id'] == backup_history.id

    def test_get_history_detail_includes_logs(self, authenticated_client, backup_history):
        """GET /api/history/<id> response includes a logs field."""
        response = authenticated_client.get(f'/api/history/{backup_history.id}')
        data = response.get_json()
        assert 'logs' in data

    def test_get_history_detail_not_found(self, authenticated_client):
        """GET /api/history/9999 returns 404."""
        response = authenticated_client.get('/api/history/9999')
        assert response.status_code == 404

    # --- logs sub-resource -------------------------------------------------

    def test_get_history_logs_returns_200(self, authenticated_client, backup_history):
        """GET /api/history/<id>/logs returns 200 with logs field."""
        response = authenticated_client.get(f'/api/history/{backup_history.id}/logs')
        assert response.status_code == 200
        data = response.get_json()
        assert 'logs' in data

    # --- summary -----------------------------------------------------------

    def test_history_summary_requires_auth(self, client, admin_user):
        response = client.get('/api/history/summary')
        assert response.status_code in (301, 302, 401)

    def test_history_summary_returns_200(self, authenticated_client):
        """GET /api/history/summary returns 200 with expected keys."""
        response = authenticated_client.get('/api/history/summary')
        assert response.status_code == 200
        data = response.get_json()
        assert 'total_backups' in data
        assert 'success_rate' in data

    def test_history_summary_all_fields(self, authenticated_client):
        """History summary contains the full expected field set."""
        response = authenticated_client.get('/api/history/summary')
        data = response.get_json()
        for key in ('days', 'total_backups', 'running',
                    'successful', 'failed', 'success_rate'):
            assert key in data, f"Missing key: {key}"

    # --- cancel ------------------------------------------------------------

    def test_cancel_non_running_backup_returns_400(self, authenticated_client, backup_history):
        """POST /api/history/<id>/cancel on a non-running record returns 400."""
        # backup_history fixture has status='success', so cancelling it is invalid.
        response = authenticated_client.post(f'/api/history/{backup_history.id}/cancel')
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_cancel_not_found(self, authenticated_client):
        """POST /api/history/9999/cancel returns 404."""
        response = authenticated_client.post('/api/history/9999/cancel')
        assert response.status_code == 404

    # --- cleanup -----------------------------------------------------------

    def test_cleanup_missing_days(self, authenticated_client):
        """POST /api/history/cleanup without days returns 400."""
        response = authenticated_client.post('/api/history/cleanup', json={})
        assert response.status_code == 400

    def test_cleanup_too_few_days(self, authenticated_client):
        """POST /api/history/cleanup with days < 30 returns 400."""
        response = authenticated_client.post(
            '/api/history/cleanup',
            json={'days': 7},
        )
        assert response.status_code == 400

    def test_cleanup_valid_returns_200(self, authenticated_client):
        """POST /api/history/cleanup with days >= 30 returns 200."""
        response = authenticated_client.post(
            '/api/history/cleanup',
            json={'days': 90},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert 'deleted_count' in data
