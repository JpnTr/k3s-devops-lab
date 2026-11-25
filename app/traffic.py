"""Deterministic bounded synthetic HTTP traffic; never targets a remote host."""
import argparse, json, random, time, urllib.request, urllib.error
from urllib.parse import urlsplit
from uuid import uuid4

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://traefik.kube-system.svc.cluster.local")
    p.add_argument("--requests", type=int, default=60)
    p.add_argument("--seed", type=int, default=202501)
    p.add_argument("--interval", type=float, default=0.2)
    a = p.parse_args()
    parsed = urlsplit(a.base_url)
    if parsed.scheme != "http" or parsed.hostname != "traefik.kube-system.svc.cluster.local" or parsed.port not in (None, 80) or parsed.path or parsed.query or parsed.fragment:
        p.error("traffic may only target the in-cluster lab Traefik service")
    if not 1 <= a.requests <= 10000 or not 0 <= a.interval <= 5:
        p.error("requests must be 1..10000 and interval 0..5 seconds")
    rng = random.Random(a.seed)
    for i in range(a.requests):
        if rng.random() < .85:
            path, data = "/orders", None
        else:
            path, data = "/orders", json.dumps({"sku": f"LAB-{i:05d}", "quantity": rng.randint(1, 5)}).encode()
        req = urllib.request.Request(a.base_url + path, data=data, headers={"Host": "orders.lab.test", "X-Request-ID": str(uuid4()), **({"Content-Type": "application/json"} if data else {})}, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=4) as r: print(f"{r.status} {req.get_method()} {path}")
        except urllib.error.HTTPError as e: print(f"{e.code} {req.get_method()} {path}")
        except Exception as e: print(f"request failed: {type(e).__name__}")
        if i + 1 < a.requests: time.sleep(a.interval)

if __name__ == "__main__": main()
