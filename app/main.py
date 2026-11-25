"""Orders API with bounded database access and deterministic lab faults."""
import os, time, uuid, logging, hashlib, asyncio, json, re, socket
if os.getenv("FAULT_STARTUP_ALLOC_MB"):
    _fault_memory = bytearray(min(int(os.getenv("FAULT_STARTUP_ALLOC_MB")), 768) * 1024 * 1024)
    for _page in range(0, len(_fault_memory), 4096): _fault_memory[_page] = 1
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from psycopg_pool import ConnectionPool, PoolTimeout
from psycopg import OperationalError

class DatabaseDnsError(Exception): pass

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger("orders-api")
VERSION = os.getenv("APP_VERSION", "v1")
DB_HOST = os.getenv("DB_HOST", "postgres.lab.svc.cluster.local")
DB_NAME, DB_USER, DB_PASSWORD = (os.getenv("DB_NAME", "orders"), os.getenv("DB_USER", "orders_app"), os.getenv("DB_PASSWORD", ""))
MIN_POOL, MAX_POOL = int(os.getenv("DB_POOL_MIN", "1")), int(os.getenv("DB_POOL_MAX", "5"))
REQUESTS = Counter("orders_http_requests_total", "HTTP requests", ["method", "route", "status", "version"])
DURATION = Histogram("orders_http_request_duration_seconds", "Request duration", ["method", "route", "version"])
DB_IN_USE = Gauge("orders_db_pool_in_use", "Connections currently in use")
DB_CAPACITY = Gauge("orders_db_pool_capacity", "Maximum configured pool connections")
DB_WAIT = Histogram("orders_db_pool_wait_seconds", "Time waiting for a connection")
DB_TIMEOUTS = Counter("orders_db_pool_timeouts_total", "Connection pool timeouts")
pool = None

@asynccontextmanager
async def lifespan(app):
    global pool
    DB_CAPACITY.set(MAX_POOL)
    # Lazy pool open permits the DNS exercise to produce request-level errors.
    pool = ConnectionPool(conninfo=f"host={DB_HOST} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}", min_size=MIN_POOL, max_size=MAX_POOL, timeout=float(os.getenv("DB_ACQUIRE_TIMEOUT", "2")), open=False)
    yield
    pool.close()

app = FastAPI(title="Orders API", version=VERSION, lifespan=lifespan)

@app.middleware("http")
async def telemetry(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", rid): rid = str(uuid.uuid4())
    route = request.url.path if request.url.path in ("/orders", "/livez", "/readyz") else "/other"
    start = time.monotonic()
    try:
        if os.getenv("FAULT_DELAY_GET", "0") not in ("", "0") and request.method == "GET" and route == "/orders":
            await asyncio.sleep(min(float(os.getenv("FAULT_DELAY_GET", "0")), 3.0))
        fail_percent = max(0, min(100, int(os.getenv("FAULT_FAIL_PERCENT", "0"))))
        if fail_percent and route == "/orders" and int(hashlib.sha256(rid.encode()).hexdigest()[:8], 16) % 100 < fail_percent:
            error_type = "synthetic_failure"
            response = JSONResponse({"error": {"code": "synthetic_failure"}}, status_code=503)
        else:
            error_type = None
            response = await call_next(request)
    except Exception as e:
        error_type = dependency_code(e)
        response = JSONResponse({"error": {"code": error_type}}, status_code=503)
    elapsed = time.monotonic() - start
    response.headers["X-Request-ID"] = rid
    if request.url.path not in ("/livez", "/readyz", "/metrics"):
        REQUESTS.labels(request.method, route, str(response.status_code), VERSION).inc()
        DURATION.labels(request.method, route, VERSION).observe(elapsed)
    event = {"@timestamp": datetime.now(timezone.utc).isoformat(), "service.name": "orders-api", "service.version": VERSION,
             "log.level": "ERROR" if response.status_code >= 500 else "INFO", "http.response.status_code": response.status_code,
             "url.path": route, "event.duration": int(elapsed * 1e9), "http.request.id": rid,
             "message": "request complete"}
    if error_type: event["error.type"] = error_type
    log.info(json.dumps(event, separators=(",", ":")))
    return response

def dependency_code(exc):
    if isinstance(exc, PoolTimeout): DB_TIMEOUTS.inc(); return "db_pool_timeout"
    if isinstance(exc, DatabaseDnsError): return "db_dns_error"
    if isinstance(exc, OperationalError):
        msg = str(exc).lower()
        return "db_dns_error" if "resolve" in msg or "name or service" in msg else "db_connection_error"
    return "internal_error"

def utc_timestamp(value):
    """Render database timestamps in UTC regardless of the DB session zone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def db_query(sql, params=()):
    start = time.monotonic()
    conn = None
    try:
        try: socket.getaddrinfo(DB_HOST, 5432, type=socket.SOCK_STREAM)
        except socket.gaierror as e: raise DatabaseDnsError(DB_HOST) from e
        pool.open(wait=False)
        conn = pool.getconn(timeout=float(os.getenv("DB_ACQUIRE_TIMEOUT", "2")))
        DB_WAIT.observe(time.monotonic() - start)
        with conn.transaction():
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (os.getenv("DB_STATEMENT_TIMEOUT_MS", "3000"),))
            hold = min(float(os.getenv("DB_HOLD_SECONDS", "0")), 3.0)
            if hold: time.sleep(hold)
            with conn.cursor() as cur:
                cur.execute(sql, params)
                try: return cur.fetchall()
                except Exception: return None
    finally:
        if conn is not None: pool.putconn(conn)
        else: DB_WAIT.observe(time.monotonic() - start)
        stats = pool.get_stats()
        DB_IN_USE.set(stats.get("pool_size", 0) - stats.get("pool_available", 0))

def insert_order(sku, quantity):
    conn = None
    start = time.monotonic()
    try:
        try: socket.getaddrinfo(DB_HOST, 5432, type=socket.SOCK_STREAM)
        except socket.gaierror as e: raise DatabaseDnsError(DB_HOST) from e
        pool.open(wait=False)
        conn = pool.getconn(timeout=float(os.getenv("DB_ACQUIRE_TIMEOUT", "2")))
        DB_WAIT.observe(time.monotonic() - start)
        with conn.transaction():
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (os.getenv("DB_STATEMENT_TIMEOUT_MS", "3000"),))
            hold = min(float(os.getenv("DB_HOLD_SECONDS", "0")), 3.0)
            if hold: time.sleep(hold)
            with conn.cursor() as cur:
                cur.execute("INSERT INTO orders (sku, quantity) VALUES (%s,%s) RETURNING id, sku, quantity, created_at", (sku, quantity))
                row = cur.fetchone()
                cur.execute("DELETE FROM orders WHERE id IN (SELECT id FROM orders WHERE fixture_key IS NULL ORDER BY created_at DESC OFFSET 1000)")
        return row
    finally:
        if conn is not None: pool.putconn(conn)
        else: DB_WAIT.observe(time.monotonic() - start)
        stats = pool.get_stats()
        DB_IN_USE.set(stats.get("pool_size", 0) - stats.get("pool_available", 0))

@app.get("/livez")
def livez(): return {"status": "ok"}

@app.get("/readyz")
def readyz():
    return {"status": "ok"}

@app.get("/orders")
def list_orders(limit: int = 50, sku: str | None = None):
    if sku is not None and not 1 <= len(sku) <= 64:
        return JSONResponse({"error": {"code": "validation_error"}}, status_code=422)
    bounded_limit = max(1, min(limit, 100))
    if sku is None:
        rows = db_query("SELECT id, sku, quantity, created_at FROM orders ORDER BY id LIMIT %s", (bounded_limit,))
    else:
        rows = db_query("SELECT id, sku, quantity, created_at FROM orders WHERE sku = %s ORDER BY id LIMIT %s", (sku, bounded_limit))
    return {"items": [{"id": str(r[0]), "sku": r[1], "quantity": r[2], "created_at": utc_timestamp(r[3])} for r in rows or []]}

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    chunks, size = [], 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > 4096: return JSONResponse({"error": {"code": "request_too_large"}}, status_code=413)
            chunks.append(chunk)
        body = json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError): return JSONResponse({"error": {"code": "invalid_json"}}, status_code=400)
    if not isinstance(body, dict): return JSONResponse({"error": {"code": "validation_error"}}, status_code=422)
    sku, qty = body.get("sku"), body.get("quantity")
    if not isinstance(sku, str) or not 1 <= len(sku) <= 64 or type(qty) is not int or not 1 <= qty <= 10000:
        return JSONResponse({"error": {"code": "validation_error"}}, status_code=422)
    row = await run_in_threadpool(insert_order, sku, qty)
    return {"id": str(row[0]), "sku": row[1], "quantity": row[2], "created_at": utc_timestamp(row[3])}

@app.get("/metrics")
def metrics(): return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
