"""
TriMCP RQ Worker Launcher
Starts an RQ worker to handle background indexing tasks.

Priority lanes (§5.4): the worker dequeues ``high_priority`` before
``batch_processing`` so that user-facing API extractions never wait behind
large batch uploads.  The ``default`` queue is retained for backward
compatibility with any older enqueue sites that haven't been migrated.
"""

import logging

from redis import from_url
from rq import Queue, Worker

from trimcp.config import cfg
from trimcp.extractors.dispatch import BATCH_QUEUE, HIGH_PRIORITY_QUEUE

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [Worker] %(levelname)s %(message)s"
)


def start_worker():
    redis_conn = from_url(cfg.REDIS_URL)
    queues = [
        Queue(HIGH_PRIORITY_QUEUE, connection=redis_conn),
        Queue(BATCH_QUEUE, connection=redis_conn),
        Queue("default", connection=redis_conn),  # backward compat
    ]
    worker = Worker(queues, connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    start_worker()
