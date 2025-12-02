"""
Unit tests for scheduler (app/scheduler.py).

Tests APScheduler configuration and job scheduling.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from app import scheduler as scheduler_module
from app.models import BackupJob


class TestSchedulerInitialization:
    """Test scheduler initialization."""

    def teardown_method(self):
        """Clean up after each test."""
        # Reset global scheduler
        scheduler_module.scheduler = None
        scheduler_module.flask_app = None

    @patch('app.scheduler.BackgroundScheduler')
    def test_init_scheduler(self, mock_scheduler_class, app):
        """Test scheduler initialization."""
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = scheduler_module.init_scheduler(app)

        assert result == mock_scheduler
        assert scheduler_module.scheduler == mock_scheduler
        assert scheduler_module.flask_app == app

        # Verify scheduler was configured correctly
        mock_scheduler_class.assert_called_once()
        call_kwargs = mock_scheduler_class.call_args[1]
        assert 'jobstores' in call_kwargs
        assert 'executors' in call_kwargs
        assert 'job_defaults' in call_kwargs
        assert call_kwargs['timezone'] == 'UTC'

        # Verify retention job was added
        mock_scheduler.add_job.assert_called()

    @patch('app.scheduler.BackgroundScheduler')
    def test_init_scheduler_only_once(self, mock_scheduler_class, app):
        """Test scheduler is only initialized once."""
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        # Initialize twice
        result1 = scheduler_module.init_scheduler(app)
        result2 = scheduler_module.init_scheduler(app)

        # Should return same instance
        assert result1 == result2
        # Should only create scheduler once
        mock_scheduler_class.assert_called_once()


class TestSchedulerLifecycle:
    """Test scheduler start/stop operations."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_scheduler = MagicMock()
        self.mock_scheduler.running = False
        self.mock_scheduler.state = 0
        scheduler_module.scheduler = self.mock_scheduler

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None
        scheduler_module.flask_app = None

    def test_start_scheduler(self):
        """Test starting the scheduler."""
        self.mock_scheduler.get_jobs.return_value = []

        scheduler_module.start_scheduler()

        self.mock_scheduler.start.assert_called_once()

    def test_start_scheduler_not_initialized(self):
        """Test starting scheduler before initialization raises error."""
        scheduler_module.scheduler = None

        with pytest.raises(RuntimeError, match="not initialized"):
            scheduler_module.start_scheduler()

    def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running."""
        self.mock_scheduler.running = True

        scheduler_module.start_scheduler()

        # Should not call start again
        self.mock_scheduler.start.assert_not_called()

    def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        self.mock_scheduler.running = True

        scheduler_module.stop_scheduler()

        self.mock_scheduler.shutdown.assert_called_once()

    def test_stop_scheduler_not_running(self):
        """Test stopping scheduler when not running."""
        self.mock_scheduler.running = False

        scheduler_module.stop_scheduler()

        # Should not call shutdown
        self.mock_scheduler.shutdown.assert_not_called()


class TestSyncBackupJobs:
    """Test syncing backup jobs with scheduler."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_scheduler = MagicMock()
        scheduler_module.scheduler = self.mock_scheduler

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None
        scheduler_module.flask_app = None

    def test_sync_backup_jobs_not_initialized(self):
        """Test syncing when scheduler not initialized raises error."""
        scheduler_module.scheduler = None

        with pytest.raises(RuntimeError, match="not initialized"):
            scheduler_module.sync_backup_jobs()

    @patch('app.scheduler._add_scheduled_job')
    def test_sync_backup_jobs_adds_enabled_job(self, mock_add, db, local_backup_job):
        """Test syncing adds enabled job with schedule."""
        # Set up job with schedule
        local_backup_job.enabled = True
        local_backup_job.schedule_cron = '0 2 * * *'
        db.session.commit()

        # No existing jobs
        self.mock_scheduler.get_jobs.return_value = []

        scheduler_module.sync_backup_jobs()

        # Should add the job
        mock_add.assert_called_once_with(local_backup_job)

    @patch('app.scheduler._update_scheduled_job')
    def test_sync_backup_jobs_updates_existing_job(self, mock_update, db, local_backup_job):
        """Test syncing updates existing scheduled job."""
        local_backup_job.enabled = True
        local_backup_job.schedule_cron = '0 2 * * *'
        db.session.commit()

        # Mock existing job
        mock_job = MagicMock()
        mock_job.id = f'backup_{local_backup_job.id}'
        self.mock_scheduler.get_jobs.return_value = [mock_job]

        scheduler_module.sync_backup_jobs()

        # Should update the job
        mock_update.assert_called_once_with(local_backup_job)

    @patch('app.scheduler._remove_scheduled_job')
    def test_sync_backup_jobs_removes_disabled_job(self, mock_remove, db, local_backup_job):
        """Test syncing removes disabled job."""
        local_backup_job.enabled = False
        db.session.commit()

        # Mock existing scheduled job
        mock_job = MagicMock()
        mock_job.id = f'backup_{local_backup_job.id}'
        self.mock_scheduler.get_jobs.return_value = [mock_job]

        scheduler_module.sync_backup_jobs()

        # Should remove the job
        mock_remove.assert_called_once_with(local_backup_job.id)

    def test_sync_backup_jobs_cleans_old_manual_jobs(self, db):
        """Test syncing removes old manual trigger jobs."""
        # Mock manual job
        mock_manual_job = MagicMock()
        mock_manual_job.id = 'manual_123_1234567890'
        self.mock_scheduler.get_jobs.return_value = [mock_manual_job]

        scheduler_module.sync_backup_jobs()

        # Should remove manual job
        self.mock_scheduler.remove_job.assert_called_with('manual_123_1234567890')


class TestScheduledJobManagement:
    """Test adding/updating/removing scheduled jobs."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_scheduler = MagicMock()
        scheduler_module.scheduler = self.mock_scheduler

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None

    def test_add_scheduled_job(self, local_backup_job):
        """Test adding a scheduled job."""
        local_backup_job.schedule_cron = '0 2 * * *'

        scheduler_module._add_scheduled_job(local_backup_job)

        # Should add job to scheduler
        self.mock_scheduler.add_job.assert_called_once()
        call_args = self.mock_scheduler.add_job.call_args
        assert call_args[1]['id'] == f'backup_{local_backup_job.id}'
        assert call_args[1]['name'] == f'Backup: {local_backup_job.name}'

    def test_update_scheduled_job(self, local_backup_job):
        """Test updating a scheduled job."""
        local_backup_job.schedule_cron = '0 3 * * *'

        # Mock existing job
        mock_job = MagicMock()
        self.mock_scheduler.get_job.return_value = mock_job

        scheduler_module._update_scheduled_job(local_backup_job)

        # Should reschedule job
        mock_job.reschedule.assert_called_once()
        assert mock_job.name == f'Backup: {local_backup_job.name}'

    def test_remove_scheduled_job(self):
        """Test removing a scheduled job."""
        job_id = 123

        scheduler_module._remove_scheduled_job(job_id)

        # Should remove job from scheduler
        self.mock_scheduler.remove_job.assert_called_once_with('backup_123')


class TestManualTrigger:
    """Test manual backup job triggering."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_scheduler = MagicMock()
        scheduler_module.scheduler = self.mock_scheduler

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None
        scheduler_module.flask_app = None

    def test_trigger_backup_now(self, db, local_backup_job):
        """Test manually triggering a backup job."""
        scheduler_module.trigger_backup_now(local_backup_job.id)

        # Should add one-time job
        self.mock_scheduler.add_job.assert_called_once()
        call_args = self.mock_scheduler.add_job.call_args
        assert call_args[1]['args'] == [local_backup_job.id, True]
        assert 'manual_' in call_args[1]['id']

    def test_trigger_backup_now_not_initialized(self, db, local_backup_job):
        """Test triggering backup when scheduler not initialized."""
        scheduler_module.scheduler = None

        with pytest.raises(RuntimeError, match="not initialized"):
            scheduler_module.trigger_backup_now(local_backup_job.id)

    def test_trigger_backup_now_job_not_found(self, db):
        """Test triggering non-existent backup job."""
        with pytest.raises(ValueError, match="not found"):
            scheduler_module.trigger_backup_now(99999)


class TestSchedulerQueries:
    """Test scheduler query functions."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_scheduler = MagicMock()
        scheduler_module.scheduler = self.mock_scheduler

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None

    def test_get_scheduled_jobs(self):
        """Test getting list of scheduled jobs."""
        # Mock jobs
        mock_job1 = MagicMock()
        mock_job1.id = 'backup_1'
        mock_job1.name = 'Test Job 1'
        mock_job1.next_run_time = datetime(2024, 1, 1, 2, 0, 0)
        mock_job1.trigger = 'cron'

        mock_job2 = MagicMock()
        mock_job2.id = 'backup_2'
        mock_job2.name = 'Test Job 2'
        mock_job2.next_run_time = None
        mock_job2.trigger = 'date'

        self.mock_scheduler.get_jobs.return_value = [mock_job1, mock_job2]

        result = scheduler_module.get_scheduled_jobs()

        assert len(result) == 2
        assert result[0]['id'] == 'backup_1'
        assert result[0]['name'] == 'Test Job 1'
        assert result[1]['next_run'] is None

    def test_get_scheduled_jobs_not_initialized(self):
        """Test getting jobs when scheduler not initialized."""
        scheduler_module.scheduler = None

        result = scheduler_module.get_scheduled_jobs()

        assert result == []

    def test_is_scheduler_running_true(self):
        """Test scheduler running check returns True."""
        self.mock_scheduler.running = True

        assert scheduler_module.is_scheduler_running() is True

    def test_is_scheduler_running_false(self):
        """Test scheduler running check returns False."""
        self.mock_scheduler.running = False

        assert scheduler_module.is_scheduler_running() is False

    def test_is_scheduler_running_not_initialized(self):
        """Test scheduler running check when not initialized."""
        scheduler_module.scheduler = None

        assert scheduler_module.is_scheduler_running() is False

    def test_get_scheduler_diagnostics(self):
        """Test getting scheduler diagnostics."""
        mock_job = MagicMock()
        mock_job.id = 'backup_1'
        mock_job.name = 'Test Job'
        mock_job.next_run_time = datetime(2024, 1, 1, 2, 0, 0)
        mock_job.trigger = 'cron'
        mock_job.pending = False

        self.mock_scheduler.running = True
        self.mock_scheduler.state = 1
        self.mock_scheduler.get_jobs.return_value = [mock_job]

        result = scheduler_module.get_scheduler_diagnostics()

        assert result['initialized'] is True
        assert result['running'] is True
        assert result['job_count'] == 1
        assert len(result['jobs']) == 1
        assert result['jobs'][0]['id'] == 'backup_1'

    def test_get_scheduler_diagnostics_not_initialized(self):
        """Test diagnostics when scheduler not initialized."""
        scheduler_module.scheduler = None

        result = scheduler_module.get_scheduler_diagnostics()

        assert result['initialized'] is False
        assert result['running'] is False
        assert result['state'] == 'NOT_INITIALIZED'


class TestExecuteBackupWrapper:
    """Test backup execution wrapper."""

    def setup_method(self):
        """Set up before each test."""
        self.mock_app = MagicMock()
        scheduler_module.flask_app = self.mock_app

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.flask_app = None

    @patch('app.scheduler.execute_backup_job')
    def test_execute_backup_wrapper_success(self, mock_execute):
        """Test wrapper executes backup successfully."""
        mock_history = MagicMock()
        mock_history.status = 'success'
        mock_execute.return_value = mock_history

        scheduler_module._execute_backup_wrapper(123)

        # Should execute with app context
        self.mock_app.app_context.assert_called_once()
        mock_execute.assert_called_once_with(123, allow_disabled=False)

    @patch('app.scheduler.execute_backup_job')
    def test_execute_backup_wrapper_with_allow_disabled(self, mock_execute):
        """Test wrapper with allow_disabled parameter."""
        mock_history = MagicMock()
        mock_execute.return_value = mock_history

        scheduler_module._execute_backup_wrapper(123, allow_disabled=True)

        mock_execute.assert_called_once_with(123, allow_disabled=True)

    @patch('app.scheduler.execute_backup_job')
    def test_execute_backup_wrapper_handles_exception(self, mock_execute):
        """Test wrapper handles execution exceptions."""
        mock_execute.side_effect = Exception("Test error")

        # Should not raise exception
        scheduler_module._execute_backup_wrapper(123)


class TestSchedulerStatusDatabaseFallback:
    """Test scheduler status detection with database fallback."""

    def teardown_method(self):
        """Clean up after each test."""
        scheduler_module.scheduler = None

    @patch('app.scheduler._count_jobs_in_database')
    def test_is_running_with_in_memory_scheduler(self, mock_count):
        """Test status detection when in-memory scheduler is running."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        scheduler_module.scheduler = mock_scheduler
        mock_count.return_value = 2

        result = scheduler_module.is_scheduler_running()

        # Should use in-memory check first, no database query needed
        assert result is True
        mock_count.assert_not_called()

    @patch('app.scheduler._count_jobs_in_database')
    def test_is_running_with_jobs_in_database(self, mock_count):
        """Test status detection when scheduler is None but jobs exist in DB."""
        scheduler_module.scheduler = None
        mock_count.return_value = 2

        result = scheduler_module.is_scheduler_running()

        assert result is True
        mock_count.assert_called_once()

    @patch('app.scheduler._count_jobs_in_database')
    def test_is_running_no_jobs_in_database(self, mock_count):
        """Test status detection when scheduler is None and no jobs in DB."""
        scheduler_module.scheduler = None
        mock_count.return_value = 0

        result = scheduler_module.is_scheduler_running()

        assert result is False
        mock_count.assert_called_once()

    @patch('app.scheduler._count_jobs_in_database')
    def test_is_running_scheduler_not_running_but_jobs_in_db(self, mock_count):
        """Test status detection when in-memory scheduler not running but DB has jobs."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        scheduler_module.scheduler = mock_scheduler
        mock_count.return_value = 3

        result = scheduler_module.is_scheduler_running()

        # Should fall back to database check
        assert result is True
        mock_count.assert_called_once()

    @patch('app.scheduler._count_jobs_in_database')
    def test_diagnostics_with_database_fallback(self, mock_count):
        """Test diagnostics include database state when scheduler is None."""
        scheduler_module.scheduler = None
        mock_count.return_value = 3

        result = scheduler_module.get_scheduler_diagnostics()

        assert result['initialized'] is False
        assert result['running'] is True  # Based on DB fallback
        assert result['jobs_in_database'] == 3
        assert 'reloader' in result['note'].lower()
        mock_count.assert_called_once()

    @patch('app.scheduler._count_jobs_in_database')
    def test_diagnostics_includes_db_count_when_initialized(self, mock_count):
        """Test diagnostics include database count alongside in-memory state."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.state = 1
        mock_scheduler.get_jobs.return_value = []
        scheduler_module.scheduler = mock_scheduler
        mock_count.return_value = 2

        result = scheduler_module.get_scheduler_diagnostics()

        assert result['initialized'] is True
        assert result['running'] is True
        assert result['job_count'] == 0  # In-memory count
        assert result['jobs_in_database'] == 2  # DB count
        mock_count.assert_called_once()

    @patch('app.scheduler._count_jobs_in_database')
    def test_diagnostics_fallback_on_error(self, mock_count):
        """Test diagnostics use DB fallback when scheduler.get_jobs() fails."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.get_jobs.side_effect = Exception("Test error")
        scheduler_module.scheduler = mock_scheduler
        mock_count.return_value = 2

        result = scheduler_module.get_scheduler_diagnostics()

        assert result['initialized'] is True
        assert result['running'] is True  # Based on DB fallback
        assert result['state'] == 'ERROR'
        assert result['jobs_in_database'] == 2
        assert 'error' in result
        mock_count.assert_called_once()
