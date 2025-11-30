import os
from datetime import timedelta


class Config:
    """Base configuration"""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:////data/mackuper.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Upload/Temp
    TEMP_DIR = os.environ.get('TEMP_DIR') or '/data/temp'
    LOCAL_BACKUP_DIR = os.environ.get('LOCAL_BACKUP_DIR') or '/data/local_backups'

    # Scheduler
    SCHEDULER_API_ENABLED = False
    SCHEDULER_TIMEZONE = 'UTC'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True

    # Use local data directory for development
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DATA_DIR, "mackuper.db")}'
    TEMP_DIR = os.path.join(DATA_DIR, 'temp')
    LOCAL_BACKUP_DIR = os.path.join(DATA_DIR, 'local_backups')


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False

    # Production security
    SESSION_COOKIE_SECURE = os.environ.get('HTTPS_ENABLED', 'false').lower() == 'true'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}
