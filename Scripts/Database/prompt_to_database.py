import time
import atexit
from psycopg2.extras import DictCursor
from psycopg2.pool import PoolError

from Scripts.Database.db_connection_pool import (create_connection_pool, close_connection_pool, get_connection, return_connection, logger as base_logger)

_POOL_READY = False

def _ensure_pool(minconn = 1, maxconn = 10):
    global _POOL_READY
    if not _POOL_READY:
        create_connection_pool(minconn = minconn, maxconn = maxconn)
        _POOL_READY = True

def _safe_close_pool():
    global _POOL_READY
    try:
        if _POOL_READY:
            close_connection_pool()
    except PoolError:
        pass
    finally:
        _POOL_READY = False

atexit.register(_safe_close_pool)

def _to_pgvector_literal(vec):
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def _normalize_params(params):
    p = dict(params or {})
    for k, v in list(p.items()):
        if (
            isinstance(k, str) and "vector" in k
            and isinstance(v, (list, tuple)) and len(v) > 0
            and all(isinstance(x, (int, float)) for x in v)
        ):
            p[k] = _to_pgvector_literal(list(v))
    return p

def run_sql(sql, params = None, fetch = "all", fetch_size = 10000, as_dict = True, statement_timeout_ms = 600000):
    p = _normalize_params(params or {})

    _ensure_pool()

    def _execute_with_conn():
        conn = get_connection()
        try:
            if fetch == "stream":
                def _gen():
                    start = time.time()
                    try:
                        with conn:
                            with conn.cursor(name = "stream_cursor", cursor_factory = DictCursor if as_dict else None) as cur:
                                if statement_timeout_ms is not None:
                                    cur.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
                                cur.itersize = fetch_size
                                cur.execute(sql, p)
                                while True:
                                    batch = cur.fetchmany(fetch_size)
                                    if not batch:
                                        break
                                    for row in batch:
                                        yield dict(row) if as_dict and row is not None else row
                        base_logger.info(f"SQL stream finished in {time.time()-start:.2f}s")
                    finally:
                        return_connection(conn)
                return _gen()

            start = time.time()
            with conn:
                with conn.cursor(cursor_factory = DictCursor if as_dict else None) as cur:
                    if statement_timeout_ms is not None:
                        cur.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
                    cur.execute(sql, p)

                    if fetch == "one":
                        row = cur.fetchone()
                        result = dict(row) if (row is not None and as_dict) else row
                    else:
                        rows = cur.fetchall()
                        result = [dict(r) for r in rows] if as_dict else rows

            base_logger.info(f"SQL ({fetch}) finished in {time.time()-start:.2f}s")
            return result
        finally:
            if fetch != "stream":
                return_connection(conn)

    try:
        return _execute_with_conn()
    except PoolError:
        _safe_close_pool()
        _ensure_pool()
        return _execute_with_conn()
