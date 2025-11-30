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

    # Initialize database
    with app.app_context():
        from app import models
        db.create_all()

    # Initialize and start scheduler
    from app.scheduler import init_scheduler, start_scheduler, sync_backup_jobs
    init_scheduler(app)
    start_scheduler()

    # Sync backup jobs from database to scheduler
    with app.app_context():
        sync_backup_jobs()

    # Register cleanup function to stop scheduler on app shutdown
    import atexit
    from app.scheduler import stop_scheduler
    atexit.register(stop_scheduler)

    return app
