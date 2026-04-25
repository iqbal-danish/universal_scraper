import queue, threading
from .jobs import execute_job

job_queue = queue.Queue()

def worker():
    while True:
        job = job_queue.get()
        if job is None:
            break
        execute_job(job)
        job_queue.task_done()

threading.Thread(target=worker, daemon=True).start()
