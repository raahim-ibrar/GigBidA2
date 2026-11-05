from arq import create_pool
from arq.connections import RedisSettings
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError


async def enqueue_portfolio(settings, tenant, document, revision):
    pool = None
    try:
        config = RedisSettings.from_dsn(settings.redis_url)
        config.conn_timeout, config.conn_retries, config.conn_retry_delay = 1, 1, 0.2
        pool = await create_pool(config, default_queue_name="arq:queue")
        await pool.enqueue_job(
            "index_portfolio", tenant, document, _job_id=f"portfolio:{document}:{revision}"
        )
        return True  # A duplicate ID means the same revision is already queued/running.
    except (OSError, RedisConnectionError, RedisTimeoutError):
        return False
    finally:
        if pool is not None:
            await pool.aclose()
