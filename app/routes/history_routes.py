"""
Backup history routes - View and manage backup execution history.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from datetime import datetime, timedelta

from app import db
from app.models import BackupHistory, BackupJob


bp = Blueprint('history', __name__, url_prefix='/api/history')


@bp.route('/', methods=['GET'])
@login_required
def list_history():
    """
    Get backup history with filtering and pagination.

    Query params:
        - status: Filter by status (running/success/failed)
        - job_id: Filter by job ID
        - days: Only show backups from last N days
        - limit: Max number of records (default: 50, max: 200)
        - offset: Number of records to skip (default: 0)

    Returns:
        JSON with history records and metadata
    """
    # Parse query parameters
    status_filter = request.args.get('status')
    job_id_filter = request.args.get('job_id', type=int)
    days_filter = request.args.get('days', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Enforce limits
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    # Build query
    query = BackupHistory.query

    # Apply filters
    if status_filter:
        if status_filter not in ['running', 'success', 'failed', 'cancelling', 'cancelled']:
            return jsonify({'error': 'Invalid status filter'}), 400
        query = query.filter(BackupHistory.status == status_filter)

    if job_id_filter:
        query = query.filter(BackupHistory.job_id == job_id_filter)

    if days_filter and days_filter > 0:
        cutoff_date = datetime.utcnow() - timedelta(days=days_filter)
        query = query.filter(BackupHistory.started_at >= cutoff_date)

    # Get total count before pagination
    total_count = query.count()

    # Apply pagination and ordering
    history_records = query.order_by(
        BackupHistory.started_at.desc()
    ).limit(limit).offset(offset).all()

    # Format results
    history_data = []
    for record in history_records:
        history_data.append({
            'id': record.id,
            'job_id': record.job_id,
            'job_name': record.job.name,
            'status': record.status,
            'started_at': record.started_at.astimezone().isoformat(),
            'completed_at': record.completed_at.astimezone().isoformat() if record.completed_at else None,
            'file_size_bytes': record.file_size_bytes,
            'file_size_mb': round(record.file_size_bytes / 1024 / 1024, 2) if record.file_size_bytes else None,
            's3_key': record.s3_key,
            'local_path': record.local_path,
            'error_message': record.error_message,
            'has_logs': bool(record.logs)
        })

    return jsonify({
        'records': history_data,
        'total': total_count,
        'limit': limit,
        'offset': offset
    })


@bp.route('/<int:history_id>', methods=['GET'])
@login_required
def get_history_detail(history_id):
    """
    Get detailed information for a specific backup history record.

    Args:
        history_id: Backup history record ID

    Returns:
        JSON with full history record including logs
    """
    record = BackupHistory.query.get_or_404(history_id)

    # Calculate duration if completed
    duration_seconds = None
    if record.completed_at:
        duration = record.completed_at - record.started_at
        duration_seconds = int(duration.total_seconds())

    return jsonify({
        'id': record.id,
        'job_id': record.job_id,
        'job_name': record.job.name,
        'status': record.status,
        'started_at': record.started_at.astimezone().isoformat(),
        'completed_at': record.completed_at.astimezone().isoformat() if record.completed_at else None,
        'duration_seconds': duration_seconds,
        'file_size_bytes': record.file_size_bytes,
        'file_size_mb': round(record.file_size_bytes / 1024 / 1024, 2) if record.file_size_bytes else None,
        's3_key': record.s3_key,
        'local_path': record.local_path,
        'error_message': record.error_message,
        'logs': record.logs
    })


@bp.route('/<int:history_id>/logs', methods=['GET'])
@login_required
def get_history_logs(history_id):
    """
    Get logs for a specific backup history record.

    Args:
        history_id: Backup history record ID

    Returns:
        JSON with logs
    """
    record = BackupHistory.query.get_or_404(history_id)

    return jsonify({
        'id': record.id,
        'job_name': record.job.name,
        'status': record.status,
        'logs': record.logs or 'No logs available'
    })


@bp.route('/summary', methods=['GET'])
@login_required
def get_history_summary():
    """
    Get summary statistics for backup history.

    Query params:
        - days: Calculate summary for last N days (default: 30)

    Returns:
        JSON with summary statistics
    """
    days = request.args.get('days', 30, type=int)
    if days < 1:
        days = 30
    if days > 365:
        days = 365

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Query for records within time range
    query = BackupHistory.query.filter(BackupHistory.started_at >= cutoff_date)

    total = query.count()
    running = query.filter(BackupHistory.status == 'running').count()
    success = query.filter(BackupHistory.status == 'success').count()
    failed = query.filter(BackupHistory.status == 'failed').count()

    # Calculate success rate
    completed = success + failed
    success_rate = round((success / completed * 100) if completed > 0 else 0, 1)

    # Get most recent backup
    recent = BackupHistory.query.order_by(BackupHistory.started_at.desc()).first()

    recent_info = None
    if recent:
        recent_info = {
            'job_name': recent.job.name,
            'status': recent.status,
            'started_at': recent.started_at.astimezone().isoformat()
        }

    return jsonify({
        'days': days,
        'total_backups': total,
        'running': running,
        'successful': success,
        'failed': failed,
        'success_rate': success_rate,
        'most_recent': recent_info
    })


@bp.route('/<int:history_id>/cancel', methods=['POST'])
@login_required
def cancel_backup(history_id):
    """
    Request cancellation of a running backup.

    Args:
        history_id: Backup history record ID

    Returns:
        JSON with cancellation status message
    """
    record = BackupHistory.query.get_or_404(history_id)

    # Verify job is actually running
    if record.status != 'running':
        return jsonify({
            'error': f'Cannot cancel backup with status: {record.status}'
        }), 400

    # Check if already cancelling
    if record.cancellation_requested:
        return jsonify({
            'message': 'Cancellation already requested',
            'status': 'cancelling'
        })

    # Set cancellation flag and transitional status
    record.cancellation_requested = True
    record.status = 'cancelling'
    db.session.commit()

    return jsonify({
        'message': 'Cancellation requested. The backup will stop at the next safe checkpoint.',
        'status': 'cancelling'
    })


@bp.route('/cleanup', methods=['POST'])
@login_required
def cleanup_old_history():
    """
    Delete old backup history records.

    Request body:
        - days: Delete records older than N days (required)

    Returns:
        JSON with number of records deleted
    """
    data = request.get_json()

    if not data.get('days'):
        return jsonify({'error': 'days parameter is required'}), 400

    days = data['days']
    if days < 30:
        return jsonify({'error': 'Cannot delete records newer than 30 days'}), 400

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Find old records
    old_records = BackupHistory.query.filter(
        BackupHistory.started_at < cutoff_date
    ).all()

    count = len(old_records)

    # Delete records
    for record in old_records:
        db.session.delete(record)

    db.session.commit()

    return jsonify({
        'message': f'Deleted {count} old backup history records',
        'deleted_count': count
    })
