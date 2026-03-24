# Gunicorn configuration for Mackuper
# Handles scheduler initialization across multiple workers

import os
import logging

logger = logging.getLogger('gunicorn.error')

# Track worker count to designate scheduler owner
_worker_count = 0

def pre_fork(server, worker):
    """
    Called just before a worker is forked.

    This runs in the master process right before the fork, allowing us to
    set the environment variable that will be inherited by the child worker.

    Args:
        server: Gunicorn server instance
        worker: Worker that is about to be forked
    """
    global _worker_count
    _worker_count += 1

    # First worker gets to be the scheduler owner
    if _worker_count == 1:
        os.environ['SCHEDULER_WORKER'] = 'true'
        logger.info(f"Worker #{_worker_count} will be designated as SCHEDULER OWNER")
    else:
        os.environ['SCHEDULER_WORKER'] = 'false'
        logger.info(f"Worker #{_worker_count} will be a standard HTTP worker (scheduler disabled)")

def post_worker_init(worker):
    """
    Called after a worker is initialized.

    Logs the final scheduler designation for this worker.

    Args:
        worker: Gunicorn worker instance
    """
    is_scheduler = os.environ.get('SCHEDULER_WORKER', 'false') == 'true'
    if is_scheduler:
        logger.info(f"Worker PID {worker.pid}: SCHEDULER OWNER confirmed")
    else:
        logger.info(f"Worker PID {worker.pid}: HTTP worker only")
