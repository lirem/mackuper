import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect


# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def configure_logging(app):
    """Configure application logging"""

    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # Set log level based on environment
    log_level = logging.DEBUG if app.config.get('DEBUG', False) else logging.INFO

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    # File handler
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'mackuper.log'),
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
    )
    file_handler.setFormatter(file_formatter)

    # Configure root logger
    logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])

    # Configure Flask app logger
    app.logger.setLevel(log_level)
    app.logger.addHandler(console_handler)
    app.logger.addHandler(file_handler)

    app.logger.info(f"Logging configured (level: {logging.getLevelName(log_level)})")


def create_app(config_name=None):
    """Flask application factory"""

    # Get the parent directory (project root) to find templates and static files
    import os
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates'))
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'production')

    from app.config import config
    app.config.from_object(config[config_name])

    # Configure logging
    configure_logging(app)

    # Ensure required directories exist
    os.makedirs(app.config['TEMP_DIR'], exist_ok=True)
    os.makedirs(app.config['LOCAL_BACKUP_DIR'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    # User loader callback
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        from app.auth import UserModel
        user = User.query.get(int(user_id))
        if user:
            return UserModel(user)
        return None

    # Register blueprints FIRST (before CSRF exemption)
    from app.routes import auth_routes, dashboard_routes, jobs_routes, settings_routes, history_routes
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(jobs_routes.bp)
    app.register_blueprint(settings_routes.bp)
    app.register_blueprint(history_routes.bp)

    # THEN exempt API routes from CSRF protection (using blueprint instances)
    csrf.exempt(settings_routes.bp)
    csrf.exempt(jobs_routes.bp)
    csrf.exempt(dashboard_routes.bp)
    csrf.exempt(history_routes.bp)

    # Health check endpoint
    @app.route('/health')
    def health():
        return {'status': 'healthy'}, 200

    # Initialize database schema and run migrations
    from app import models
    from app.migrations import init_database_schema

    # This handles both fresh installations and existing databases with migrations
    init_database_schema(app)

    # Auto-initialize crypto manager from stored password
    with app.app_context():
        from app.models import EncryptionKey
        from app.utils.crypto import crypto_manager
        from app.utils.master_key import get_master_key_manager

        app.logger.info("Checking for stored encryption password...")

        encryption_key_record = EncryptionKey.query.first()

        if encryption_key_record and encryption_key_record.password_encrypted:
            try:
                # Decrypt the stored password
                master_key_manager = get_master_key_manager(app)
                user_password = master_key_manager.decrypt_password(
                    encryption_key_record.password_encrypted
                )

                # Initialize crypto manager with decrypted password
                crypto_manager.initialize(user_password, encryption_key_record.key_encrypted)

                app.logger.info("Crypto manager auto-initialized successfully from stored password")

            except Exception as e:
                app.logger.error(f"Failed to auto-initialize crypto manager: {e}")
                app.logger.warning("Scheduled backups will fail until user logs in")
        else:
            app.logger.info("No stored password found - crypto manager will initialize on first login")

    # Initialize and start scheduler (only in designated worker or development child process)
    from app.scheduler import init_scheduler, start_scheduler, sync_backup_jobs, stop_scheduler
    import atexit

    # Determine if this process should initialize the scheduler
    is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    is_development = app.config.get('DEBUG', False)
    is_scheduler_worker = os.environ.get('SCHEDULER_WORKER', 'true').lower() == 'true'

    # Scheduler initialization logic:
    # - Development mode: Only in Flask reloader child process (not parent)
    # - Production mode: Only in designated scheduler worker (SCHEDULER_WORKER=true)
    should_init_scheduler = False

    if is_development:
        # Development: Use Flask reloader detection
        should_init_scheduler = is_reloader_child
        app.logger.info(f"Development mode: is_reloader_child={is_reloader_child}")
    else:
        # Production: Use Gunicorn worker designation
        should_init_scheduler = is_scheduler_worker
        app.logger.info(f"Production mode: is_scheduler_worker={is_scheduler_worker}")

    if should_init_scheduler:
        app.logger.info("Initializing scheduler in this process...")
        init_scheduler(app)
        start_scheduler()

        # Sync backup jobs from database to scheduler
        with app.app_context():
            sync_backup_jobs()

        # Register cleanup function to stop scheduler on app shutdown
        atexit.register(stop_scheduler)
        app.logger.info("Scheduler initialized and started successfully")
    else:
        app.logger.info("Scheduler initialization skipped in this process (not designated scheduler worker)")

    return app
