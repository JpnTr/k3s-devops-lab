# Orders API

| Method and route | Contract |
| --- | --- |
| GET /orders | 200 with stable ordered JSON items and a bounded page size; optional exact `sku` filter for a bounded 1–64 character SKU |
| POST /orders | 201 with a generated ID, SKU, quantity and an ISO-8601 UTC creation timestamp ending in `Z` |
| GET /livez | 200 when the process is alive, with a bounded execution time |
| GET /readyz | 200 when the application can accept traffic after startup |
| GET /metrics | Prometheus exposition scraped internally |

Validate bounded SKU length and positive bounded quantity. Return clear validation errors and stable dependency error codes. Return or generate a validated X-Request-ID on requests. Never log raw payloads or credentials. Liveness remains independent of transient database connectivity. Startup must tolerate a missing database hostname without crashing repeatedly, so DNS faults can surface as diagnosable request failures. Keep explicit timeouts on DB acquisition and SQL, and distinguish DNS, connection and pool-timeout errors.

Normalize PostgreSQL timestamps to UTC when serializing both order responses; the API representation must not depend on the database session timezone.

Include version labels on replicas and application signals. Use environment-driven, deterministic fault behavior via scenario patches, with no HTTP fault-control endpoints. Bound fault memory, duration, and worker concurrency. The healthy synthetic load should include a large share of reads with bounded writes and a fixed test seed. Keep baseline and burst settings versioned.
