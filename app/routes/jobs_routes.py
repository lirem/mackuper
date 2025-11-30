"""
Backup jobs routes - CRUD operations and job execution.
"""

import json
from flask import Blueprint, jsonify, request
from flask_login import login_required

from app import db
from app.models import BackupJob, BackupHistory
from app.scheduler import sync_backup_jobs, trigger_backup_now


bp = Blueprint('jobs', __name__, url_prefix='/api/jobs')


@bp.route('/', methods=['GET'])
@login_required
def list_jobs():
    """
    Get list of all backup jobs.

    Returns:
        JSON array of backup jobs
    """
    jobs = BackupJob.query.order_by(BackupJob.created_at.desc()).all()

    jobs_data = []
    for job in jobs:
        jobs_data.append({
            'id': job.id,
            'name': job.name,
            'description': job.description,
            'enabled': job.enabled,
            'source_type': job.source_type,
            'compression_format': job.compression_format,
            'schedule_cron': job.schedule_cron,
            'retention_s3_days': job.retention_s3_days,
            'retention_local_days': job.retention_local_days,
            'created_at': job.created_at.isoformat(),
            'updated_at': job.updated_at.isoformat()
        })

    return jsonify(jobs_data)


@bp.route('/<int:job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    """
    Get a single backup job by ID.

    Args:
        job_id: Backup job ID

    Returns:
        JSON with job details including source_config
    """
    job = BackupJob.query.get_or_404(job_id)

    # Parse source config JSON
    source_config = json.loads(job.source_config)

    return jsonify({
        'id': job.id,
        'name': job.name,
        'description': job.description,
        'enabled': job.enabled,
        'source_type': job.source_type,
        'source_config': source_config,
        'compression_format': job.compression_format,
        'schedule_cron': job.schedule_cron,
        'retention_s3_days': job.retention_s3_days,
        'retention_local_days': job.retention_local_days,
        'created_at': job.created_at.isoformat(),
        'updated_at': job.updated_at.isoformat()
    })


@bp.route('/', methods=['POST'])
@login_required
def create_job():
    """
    Create a new backup job.

    Request body:
        - name: Job name (required)
        - description: Job description (optional)
        - enabled: Enable job (default: true)
        - source_type: 'local' or 'ssh' (required)
        - source_config: Source configuration object (required)
        - compression_format: Archive format (required)
        - schedule_cron: Cron expression (optional)
        - retention_s3_days: S3 retention days (optional)
        - retention_local_days: Local retention days (optional)

    Returns:
        JSON with created job details
    """
    data = request.get_json()

    # Validate required fields
    if not data.get('name'):
        return jsonify({'error': 'Job name is required'}), 400

    if not data.get('source_type'):
        return jsonify({'error': 'Source type is required'}), 400

    if data['source_type'] not in ['local', 'ssh']:
        return jsonify({'error': 'Source type must be local or ssh'}), 400

    if not data.get('source_config'):
        return jsonify({'error': 'Source configuration is required'}), 400

    if not data.get('compression_format'):
        return jsonify({'error': 'Compression format is required'}), 400

    valid_formats = ['zip', 'tar.gz', 'tar.bz2', 'tar.xz', 'none']
    if data['compression_format'] not in valid_formats:
        return jsonify({'error': f'Invalid compression format. Valid options: {valid_formats}'}), 400

    # Check if job name already exists
    existing = BackupJob.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': 'Job name already exists'}), 400

    # Create new job
    job = BackupJob(
        name=data['name'],
        description=data.get('description', ''),
        enabled=data.get('enabled', True),
        source_type=data['source_type'],
        source_config=json.dumps(data['source_config']),
        compression_format=data['compression_format'],
        schedule_cron=data.get('schedule_cron'),
        retention_s3_days=data.get('retention_s3_days'),
        retention_local_days=data.get('retention_local_days')
    )

    db.session.add(job)
    db.session.commit()

    # Sync scheduler
    sync_backup_jobs()

    return jsonify({
        'id': job.id,
        'message': 'Backup job created successfully'
    }), 201


@bp.route('/<int:job_id>', methods=['PUT'])
@login_required
def update_job(job_id):
    """
    Update an existing backup job.

    Args:
        job_id: Backup job ID

    Request body: Same as create_job (all fields optional)

    Returns:
        JSON with success message
    """
    job = BackupJob.query.get_or_404(job_id)
    data = request.get_json()

    # Update fields if provided
    if 'name' in data:
        # Check if new name conflicts with another job
        if data['name'] != job.name:
            existing = BackupJob.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'error': 'Job name already exists'}), 400
        job.name = data['name']

    if 'description' in data:
        job.description = data['description']

    if 'enabled' in data:
        job.enabled = data['enabled']

    if 'source_type' in data:
        if data['source_type'] not in ['local', 'ssh']:
            return jsonify({'error': 'Source type must be local or ssh'}), 400
        job.source_type = data['source_type']

    if 'source_config' in data:
        job.source_config = json.dumps(data['source_config'])

    if 'compression_format' in data:
        valid_formats = ['zip', 'tar.gz', 'tar.bz2', 'tar.xz', 'none']
        if data['compression_format'] not in valid_formats:
            return jsonify({'error': f'Invalid compression format. Valid options: {valid_formats}'}), 400
        job.compression_format = data['compression_format']

    if 'schedule_cron' in data:
        job.schedule_cron = data['schedule_cron']

    if 'retention_s3_days' in data:
        job.retention_s3_days = data['retention_s3_days']

    if 'retention_local_days' in data:
        job.retention_local_days = data['retention_local_days']

    db.session.commit()

    # Sync scheduler
    sync_backup_jobs()

    return jsonify({'message': 'Backup job updated successfully'})


@bp.route('/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    """
    Delete a backup job.

    Args:
        job_id: Backup job ID

    Returns:
        JSON with success message
    """
    job = BackupJob.query.get_or_404(job_id)

    # Delete job (cascade will delete history)
    db.session.delete(job)
    db.session.commit()

    # Sync scheduler
    sync_backup_jobs()

    return jsonify({'message': 'Backup job deleted successfully'})


@bp.route('/<int:job_id>/toggle', methods=['POST'])
@login_required
def toggle_job(job_id):
    """
    Toggle a job's enabled status.

    Args:
        job_id: Backup job ID

    Returns:
        JSON with new enabled status
    """
    job = BackupJob.query.get_or_404(job_id)

    job.enabled = not job.enabled
    db.session.commit()

    # Sync scheduler
    sync_backup_jobs()

    return jsonify({
        'enabled': job.enabled,
        'message': f"Job {'enabled' if job.enabled else 'disabled'} successfully"
    })


@bp.route('/<int:job_id>/run', methods=['POST'])
@login_required
def run_job_now(job_id):
    """
    Manually trigger a backup job to run immediately.

    Args:
        job_id: Backup job ID

    Returns:
        JSON with success message
    """
    job = BackupJob.query.get_or_404(job_id)

    try:
        trigger_backup_now(job_id)
        return jsonify({
            'message': f"Backup job '{job.name}' has been queued for immediate execution"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/<int:job_id>/history', methods=['GET'])
@login_required
def get_job_history(job_id):
    """
    Get backup history for a specific job.

    Args:
        job_id: Backup job ID

    Query params:
        - limit: Max number of records (default: 50)

    Returns:
        JSON array of backup history records
    """
    job = BackupJob.query.get_or_404(job_id)

    limit = request.args.get('limit', 50, type=int)
    if limit > 200:
        limit = 200

    history = BackupHistory.query.filter_by(job_id=job_id).order_by(
        BackupHistory.started_at.desc()
    ).limit(limit).all()

    history_data = []
    for record in history:
        history_data.append({
            'id': record.id,
            'status': record.status,
            'started_at': record.started_at.isoformat(),
            'completed_at': record.completed_at.isoformat() if record.completed_at else None,
            'file_size_mb': round(record.file_size_bytes / 1024 / 1024, 2) if record.file_size_bytes else None,
            's3_key': record.s3_key,
            'local_path': record.local_path,
            'error_message': record.error_message
        })

    return jsonify(history_data)
