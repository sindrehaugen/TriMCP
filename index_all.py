import asyncio
import logging
import os

from trimcp.orchestrator import TriStackEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("index_all")


def get_files_to_index(root_dir="."):
    """
    Finds all Python files to index while excluding non-source directories.
    """
    ignore_dirs = {
        ".venv",
        "__pycache__",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "env",
        "venv",
    }
    files = []
    for root, dirs, filenames in os.walk(root_dir):
        # Modify dirs in-place to prevent os.walk from descending into ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in filenames:
            if f.endswith(".py"):
                # Normalize path for indexing
                files.append(os.path.normpath(os.path.join(root, f)))
    return files


async def index_repo(namespace_id: str = "default"):
    files_to_index = get_files_to_index()
    log.info("Found %s Python files to index (namespace=%s).", len(files_to_index), namespace_id)

    engine = TriStackEngine()
    await engine.connect()

    try:
        # Use a semaphore to avoid overwhelming the database/Redis with too many concurrent enqueue requests
        sem = asyncio.Semaphore(10)

        async def process_file(filepath):
            async with sem:
                try:
                    with open(filepath, encoding='utf-8') as f:
                        raw_code = f.read()

                    res = await engine.index_code_file(
                        filepath, raw_code, "python", namespace_id=namespace_id
                    )
                    return res
                except Exception as e:
                    log.error("Error submitting %s: %s", filepath, e)
                    return {"status": "error", "filepath": filepath, "error": str(e)}

        log.info("Submitting files for indexing...")
        tasks = [process_file(f) for f in files_to_index]
        results = await asyncio.gather(*tasks)

        enqueued_jobs = [r["job_id"] for r in results if r and r.get("status") == "enqueued"]
        skipped = [r for r in results if r and r.get("status") == "skipped"]
        errors = [r for r in results if r and r.get("status") == "error"]

        log.info(
            "Submission complete. Enqueued: %s, Skipped: %s, Errors: %s.",
            len(enqueued_jobs),
            len(skipped),
            len(errors),
        )

        # Handle the async job_id responses gracefully without blocking the event loop or creating lock-waits.
        pending_jobs = set(enqueued_jobs)
        while pending_jobs:
            log.info("Waiting for %s jobs to complete...", len(pending_jobs))
            await asyncio.sleep(2)  # Graceful non-blocking wait

            async def check_status(j_id):
                async with sem:
                    return await engine.get_job_status(j_id)

            status_results = await asyncio.gather(*(check_status(j_id) for j_id in pending_jobs))

            done_jobs = set()
            for status_res in status_results:
                job_id = status_res.get("job_id")
                status = status_res.get("status")

                # Check for terminal states
                if status in ("finished", "failed", "canceled", "not_found"):
                    if status == "failed":
                        log.error("Job %s failed: %s", job_id, status_res.get("error"))
                    elif status == "finished":
                        log.debug("Job %s finished successfully.", job_id)
                    else:
                        log.warning("Job %s completed with status: %s", job_id, status)
                    done_jobs.add(job_id)

            pending_jobs -= done_jobs

        log.info("All indexing jobs have completed.")

    finally:
        await engine.disconnect()


if __name__ == '__main__':
    import sys

    ns = os.environ.get("TRIMCP_NAMESPACE_ID", "default")
    if len(sys.argv) > 1:
        ns = sys.argv[1]
    asyncio.run(index_repo(ns))
