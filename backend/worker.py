from backend.config import settings


def run_worker() -> None:
    try:
        import redis
        from rq import Connection, Worker
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("redis and rq must be installed to run the worker") from exc

    redis_conn = redis.from_url(settings.redis_url)
    with Connection(redis_conn):
        worker = Worker([settings.redis_queue_name])
        worker.work(with_scheduler=True)


if __name__ == "__main__":
    run_worker()
