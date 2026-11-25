import socket
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app, db_query, dependency_code, utc_timestamp, DatabaseDnsError, PoolTimeout
from psycopg import OperationalError


class ApiContractTests(unittest.TestCase):
    def test_database_timestamps_are_normalized_to_utc(self):
        local = datetime(2026, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(utc_timestamp(local), "2026-01-01T00:00:00Z")
        naive = datetime(2026, 1, 1, 0, 0)
        self.assertEqual(utc_timestamp(naive), "2026-01-01T00:00:00Z")

    def test_liveness_is_independent_of_database(self):
        with TestClient(app) as client:
            response = client.get("/livez")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertTrue(response.headers.get("x-request-id"))

    def test_request_id_is_returned_and_logged_as_structured_data(self):
        with self.assertLogs("orders-api", level="INFO") as captured:
            with TestClient(app) as client:
                response = client.get("/livez", headers={"X-Request-ID": "lab:probe-01"})
        self.assertEqual(response.headers["X-Request-ID"], "lab:probe-01")
        self.assertTrue(any('"http.request.id":"lab:probe-01"' in line for line in captured.output))

    def test_invalid_order_is_rejected_before_database_access(self):
        with TestClient(app) as client:
            response = client.post("/orders", json={"sku": "", "quantity": 1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_order_sku_filter_is_parameterized_and_bounded(self):
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patch("app.main.db_query", return_value=[(7, "SUITE-SENTINEL", 1, timestamp)]) as query:
            with TestClient(app) as client:
                response = client.get("/orders", params={"sku": "SUITE-SENTINEL"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["sku"], "SUITE-SENTINEL")
        query.assert_called_once_with(
            "SELECT id, sku, quantity, created_at FROM orders WHERE sku = %s ORDER BY id LIMIT %s",
            ("SUITE-SENTINEL", 50),
        )

    def test_invalid_order_sku_filter_is_rejected_before_database_access(self):
        with patch("app.main.db_query") as query:
            with TestClient(app) as client:
                response = client.get("/orders", params={"sku": ""})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        query.assert_not_called()

    def test_malformed_and_oversized_bodies_have_stable_errors(self):
        with TestClient(app) as client:
            malformed = client.post("/orders", content=b"{")
            oversized = client.post("/orders", content=b" " * 4097)
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"]["code"], "invalid_json")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"]["code"], "request_too_large")

    def test_untrusted_request_id_is_replaced(self):
        with TestClient(app) as client:
            response = client.get("/livez", headers={"X-Request-ID": "private value"})
        self.assertNotEqual(response.headers["X-Request-ID"], "private value")
        self.assertRegex(response.headers["X-Request-ID"], r"^[0-9a-f-]{36}$")

    def test_synthetic_failure_is_bounded_and_does_not_need_database(self):
        with patch.dict("os.environ", {"FAULT_FAIL_PERCENT": "100"}):
            with TestClient(app) as client:
                response = client.get("/orders", headers={"X-Request-ID": "deterministic-probe"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "synthetic_failure")
        self.assertEqual(response.headers["X-Request-ID"], "deterministic-probe")

    def test_metrics_endpoint_is_available_without_database(self):
        with TestClient(app) as client:
            response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("orders_http_requests_total", response.text)

    def test_database_pool_opens_lazily_after_dns_succeeds(self):
        class Pool:
            opened = False
            def open(self, wait=False): self.opened = True
            def getconn(self, timeout=None):
                if not self.opened: raise AssertionError("pool used before open")
                raise PoolTimeout("test timeout")
            def get_stats(self): return {"pool_size": 0, "pool_available": 0}

        fake = Pool()
        with patch("app.main.socket.getaddrinfo", return_value=[]), patch("app.main.pool", fake):
            with self.assertRaises(PoolTimeout): db_query("SELECT 1")
        self.assertTrue(fake.opened)

    def test_database_dns_failure_does_not_open_pool(self):
        class Pool:
            opened = False
            def open(self, wait=False): self.opened = True
            def get_stats(self): return {"pool_size": 0, "pool_available": 0}

        fake = Pool()
        with patch("app.main.socket.getaddrinfo", side_effect=socket.gaierror("dns")), patch("app.main.pool", fake):
            with self.assertRaises(DatabaseDnsError): db_query("SELECT 1")
        self.assertFalse(fake.opened)

    def test_database_failures_keep_distinct_error_codes(self):
        self.assertEqual(dependency_code(DatabaseDnsError("postgres")), "db_dns_error")
        self.assertEqual(dependency_code(OperationalError("connection refused")), "db_connection_error")
        self.assertEqual(dependency_code(PoolTimeout("pool full")), "db_pool_timeout")
