"""
TriMCP RQ Worker Launcher
Starts an RQ worker to handle background indexing tasks.
"""
import logging
from redis import from_url
from rq import Worker, Queue
from trimcp.config import cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Worker] %(levelname)s %(message)s")

def start_worker():
    redis_conn = from_url(cfg.REDIS_URL)
    worker = Worker(['default'], connection=redis_conn)
    worker.work()

if __name__ == "__main__":
    start_worker()
