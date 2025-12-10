# Gunicorn configuration for Mackuper
# Handles scheduler initialization across multiple workers

import os
import logging

logger = logging.getLogger('gunicorn.error')

def post_worker_init(worker):
    """
    Called after a worker is initialized.

    Designates the first worker (worker.age == 0) as the scheduler owner.
    Only this worker will initialize and run APScheduler to prevent
    duplicate job executions.

    Args:
        worker: Gunicorn worker instance (uses 'age' attribute: 0, 1, 2, ...)
    """
    # Worker age starts at 0 for the first worker
    if worker.age == 0:
        os.environ['SCHEDULER_WORKER'] = 'true'
        logger.info(f"Worker PID {worker.pid} (age={worker.age}): Designated as SCHEDULER OWNER")
    else:
        os.environ['SCHEDULER_WORKER'] = 'false'
        logger.info(f"Worker PID {worker.pid} (age={worker.age}): Standard HTTP worker (scheduler disabled)")
