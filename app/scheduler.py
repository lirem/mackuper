"""
APScheduler configuration and job scheduling for Mackuper.

Manages:
- Scheduled backup jobs (based on cron expressions)
- Daily retention policy enforcement
- Manual job triggers
"""

from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app import db
from app.models import BackupJob
from app.backup.executor import execute_backup_job
from app.backup.retention import enforce_retention_policies


# Global scheduler instance
scheduler = None


def init_scheduler(app):
    """
    Initialize and configure APScheduler.

    Args:
        app: Flask app instance
    """
    global scheduler

    if scheduler is not None:
        return scheduler

    # Configure job stores and executors
    jobstores = {
        'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
    }

    executors = {
        'default': ThreadPoolExecutor(max_workers=3)
    }

    job_defaults = {
        'coalesce': True,  # Combine multiple pending instances into one
        'max_instances': 1,  # Only one instance of a job at a time
        'misfire_grace_time': 300  # 5 minutes grace period for misfires
    }

    # Create scheduler
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone='UTC'
    )

    # Add retention policy job (runs daily at 2 AM UTC)
    scheduler.add_job(
        func=enforce_retention_policies,
        trigger=CronTrigger(hour=2, minute=0),
        id='retention_cleanup',
        name='Daily Retention Cleanup',
        replace_existing=True
    )

    return scheduler


def start_scheduler():
    """
    Start the APScheduler.

    Should be called after Flask app is initialized.
    """
    global scheduler

    if scheduler is None:
        raise RuntimeError("Scheduler not initialized. Call init_scheduler() first.")

    if not scheduler.running:
        scheduler.start()
        print("APScheduler started")


def stop_scheduler():
    """Stop the APScheduler."""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("APScheduler stopped")


def sync_backup_jobs():
    """
    Synchronize backup jobs from database to scheduler.

    This function should be called:
    - After app startup
    - After creating/updating/deleting backup jobs
    """
    global scheduler

    if scheduler is None:
        raise RuntimeError("Scheduler not initialized")

    # Get all jobs from database
    backup_jobs = BackupJob.query.all()

    # Get current scheduled job IDs
    scheduled_job_ids = {job.id for job in scheduler.get_jobs() if job.id.startswith('backup_')}

    # Process each backup job
    for backup_job in backup_jobs:
        job_id = f"backup_{backup_job.id}"

        if backup_job.enabled and backup_job.schedule_cron:
            # Job should be scheduled
            if job_id in scheduled_job_ids:
                # Update existing job
                _update_scheduled_job(backup_job)
                scheduled_job_ids.remove(job_id)
            else:
                # Add new job
                _add_scheduled_job(backup_job)
        else:
            # Job should not be scheduled (disabled or no schedule)
            if job_id in scheduled_job_ids:
                # Remove from scheduler
                _remove_scheduled_job(backup_job.id)
                scheduled_job_ids.remove(job_id)

    # Remove any leftover scheduled jobs that don't exist in database
    for leftover_id in scheduled_job_ids:
        try:
            scheduler.remove_job(leftover_id)
            print(f"Removed orphaned scheduled job: {leftover_id}")
        except:
            pass


def _add_scheduled_job(backup_job: BackupJob):
    """
    Add a backup job to the scheduler.

    Args:
        backup_job: BackupJob instance
    """
    global scheduler

    job_id = f"backup_{backup_job.id}"

    try:
        # Parse cron expression
        trigger = CronTrigger.from_crontab(backup_job.schedule_cron, timezone='UTC')

        # Add job
        scheduler.add_job(
            func=_execute_backup_wrapper,
            args=[backup_job.id],
            trigger=trigger,
            id=job_id,
            name=f"Backup: {backup_job.name}",
            replace_existing=True
        )

        print(f"Scheduled backup job: {backup_job.name} ({backup_job.schedule_cron})")

    except Exception as e:
        print(f"Failed to schedule backup job {backup_job.name}: {e}")


def _update_scheduled_job(backup_job: BackupJob):
    """
    Update a scheduled backup job.

    Args:
        backup_job: BackupJob instance
    """
    global scheduler

    job_id = f"backup_{backup_job.id}"

    try:
        # Get existing job
        job = scheduler.get_job(job_id)

        if job:
            # Parse new cron expression
            new_trigger = CronTrigger.from_crontab(backup_job.schedule_cron, timezone='UTC')

            # Reschedule job
            job.reschedule(trigger=new_trigger)
            job.name = f"Backup: {backup_job.name}"

            print(f"Updated scheduled backup job: {backup_job.name}")

    except Exception as e:
        print(f"Failed to update backup job {backup_job.name}: {e}")


def _remove_scheduled_job(backup_job_id: int):
    """
    Remove a backup job from the scheduler.

    Args:
        backup_job_id: BackupJob ID
    """
    global scheduler

    job_id = f"backup_{backup_job_id}"

    try:
        scheduler.remove_job(job_id)
        print(f"Removed scheduled backup job ID: {backup_job_id}")
    except Exception as e:
        print(f"Failed to remove backup job {backup_job_id}: {e}")


def _execute_backup_wrapper(job_id: int):
    """
    Wrapper function for executing backup jobs in scheduler context.

    This function ensures the database session is properly managed when
    jobs are executed by APScheduler.

    Args:
        job_id: BackupJob ID to execute
    """
    from flask import current_app

    # Execute within app context
    with current_app.app_context():
        try:
            print(f"Scheduler executing backup job ID: {job_id}")
            history = execute_backup_job(job_id)
            print(f"Backup job {job_id} completed with status: {history.status}")
        except Exception as e:
            print(f"Scheduler backup job {job_id} failed: {e}")


def trigger_backup_now(job_id: int):
    """
    Manually trigger a backup job immediately.

    Args:
        job_id: BackupJob ID to execute

    Raises:
        ValueError: If job not found
    """
    global scheduler

    if scheduler is None:
        raise RuntimeError("Scheduler not initialized")

    # Verify job exists
    backup_job = BackupJob.query.get(job_id)
    if not backup_job:
        raise ValueError(f"Backup job not found: {job_id}")

    # Add one-time job
    scheduler.add_job(
        func=_execute_backup_wrapper,
        args=[job_id],
        id=f"manual_{job_id}_{int(datetime.utcnow().timestamp())}",
        name=f"Manual: {backup_job.name}",
        replace_existing=False
    )

    print(f"Manually triggered backup job: {backup_job.name}")


def get_scheduled_jobs() -> list:
    """
    Get list of all scheduled jobs.

    Returns:
        List of dicts with job information
    """
    global scheduler

    if scheduler is None:
        return []

    jobs = []

    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })

    return jobs


def is_scheduler_running() -> bool:
    """
    Check if scheduler is running.

    Returns:
        True if scheduler is running, False otherwise
    """
    global scheduler
    return scheduler is not None and scheduler.running
