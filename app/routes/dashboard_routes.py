"""
Dashboard routes - Overview and statistics endpoints.
"""

from flask import Blueprint, jsonify
from flask_login import login_required
from datetime import datetime, timedelta
from sqlalchemy import func

from app import db
from app.models import BackupJob, BackupHistory
from app.scheduler import get_scheduled_jobs, is_scheduler_running


bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


@bp.route('/overview', methods=['GET'])
@login_required
def get_overview():
    """
    Get dashboard overview statistics.

    Returns:
        JSON with overview stats:
        - total_jobs: Total number of backup jobs
        - active_jobs: Number of enabled backup jobs
        - last_backup: Most recent backup info
        - scheduler_status: Scheduler running status
    """
    # Count total and active jobs
    total_jobs = BackupJob.query.count()
    active_jobs = BackupJob.query.filter_by(enabled=True).count()

    # Get most recent backup
    last_backup = BackupHistory.query.order_by(
        BackupHistory.completed_at.desc()
    ).first()

    last_backup_info = None
    if last_backup:
        last_backup_info = {
            'job_name': last_backup.job.name,
            'status': last_backup.status,
            'completed_at': last_backup.completed_at.isoformat() if last_backup.completed_at else None,
            'file_size_mb': round(last_backup.file_size_bytes / 1024 / 1024, 2) if last_backup.file_size_bytes else None
        }

    # Get scheduler status
    scheduler_running = is_scheduler_running()

    return jsonify({
        'total_jobs': total_jobs,
        'active_jobs': active_jobs,
        'last_backup': last_backup_info,
        'scheduler_status': 'running' if scheduler_running else 'stopped'
    })


@bp.route('/recent-activity', methods=['GET'])
@login_required
def get_recent_activity():
    """
    Get recent backup activity (last 10 backups).

    Returns:
        JSON array of recent backup history records
    """
    recent_backups = BackupHistory.query.order_by(
        BackupHistory.started_at.desc()
    ).limit(10).all()

    activity = []
    for backup in recent_backups:
        activity.append({
            'id': backup.id,
            'job_id': backup.job_id,
            'job_name': backup.job.name,
            'status': backup.status,
            'started_at': backup.started_at.isoformat(),
            'completed_at': backup.completed_at.isoformat() if backup.completed_at else None,
            'file_size_mb': round(backup.file_size_bytes / 1024 / 1024, 2) if backup.file_size_bytes else None,
            'error_message': backup.error_message
        })

    return jsonify(activity)


@bp.route('/statistics', methods=['GET'])
@login_required
def get_statistics():
    """
    Get backup statistics.

    Returns:
        JSON with statistics:
        - total_backups: Total number of backups executed
        - successful_backups: Number of successful backups
        - failed_backups: Number of failed backups
        - total_size_gb: Total size of all successful backups in GB
        - backups_last_7_days: Number of backups in last 7 days
        - backups_last_30_days: Number of backups in last 30 days
    """
    # Total counts
    total_backups = BackupHistory.query.count()
    successful_backups = BackupHistory.query.filter_by(status='success').count()
    failed_backups = BackupHistory.query.filter_by(status='failed').count()

    # Total size of successful backups
    total_size_bytes = db.session.query(
        func.sum(BackupHistory.file_size_bytes)
    ).filter(
        BackupHistory.status == 'success'
    ).scalar() or 0

    total_size_gb = round(total_size_bytes / 1024 / 1024 / 1024, 2)

    # Backups in time ranges
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    backups_last_7_days = BackupHistory.query.filter(
        BackupHistory.started_at >= seven_days_ago
    ).count()

    backups_last_30_days = BackupHistory.query.filter(
        BackupHistory.started_at >= thirty_days_ago
    ).count()

    return jsonify({
        'total_backups': total_backups,
        'successful_backups': successful_backups,
        'failed_backups': failed_backups,
        'total_size_gb': total_size_gb,
        'backups_last_7_days': backups_last_7_days,
        'backups_last_30_days': backups_last_30_days
    })


@bp.route('/scheduled-jobs', methods=['GET'])
@login_required
def get_scheduled_jobs_info():
    """
    Get information about currently scheduled jobs.

    Returns:
        JSON array of scheduled jobs with next run times
    """
    scheduled = get_scheduled_jobs()
    return jsonify(scheduled)


@bp.route('/scheduler-diagnostics', methods=['GET'])
@login_required
def get_scheduler_diagnostics_endpoint():
    """
    Get detailed scheduler diagnostics.

    Returns:
        JSON with scheduler state, jobs, and health information
    """
    from app.scheduler import get_scheduler_diagnostics
    diagnostics = get_scheduler_diagnostics()
    return jsonify(diagnostics)
