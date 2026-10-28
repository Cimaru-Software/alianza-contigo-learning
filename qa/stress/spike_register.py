"""Spike test: N registrations released at the same instant (scrypt is the costliest operation).

    QA_BASE_URL=http://127.0.0.1:5055 python qa/stress/spike_register.py 100 200
"""
import os
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "blackbox"))
from conftest import cedula, unique_email  # noqa: E402

API = os.getenv("QA_BASE_URL", "http://127.0.0.1:5055").rstrip("/") + "/api/v1"


def spike(count):
    gate = threading.Barrier(count)

    def register(_index):
        body = {"firstName": "Pico", "lastName": "QA", "email": unique_email("spike"), "password": "Seguro2026", "nationalId": cedula()}
        gate.wait()
        started = time.perf_counter()
        try:
            status = requests.post(f"{API}/auth/register", json=body, timeout=60).status_code
        except requests.RequestException as exc:
            status = type(exc).__name__
        return status, (time.perf_counter() - started) * 1000

    began = time.perf_counter()
    with ThreadPoolExecutor(count) as pool:
        results = list(pool.map(register, range(count)))
    elapsed = time.perf_counter() - began
    latencies = sorted(latency for _status, latency in results)
    statuses = Counter(status for status, _latency in results)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    print(
        f"{count:4} simultáneos | {elapsed:5.1f} s | {count / elapsed:5.1f} registros/s | "
        f"p50 {statistics.median(latencies):6.0f} ms | p95 {p95:6.0f} ms | max {latencies[-1]:6.0f} ms | {dict(statuses)}"
    )


if __name__ == "__main__":
    for size in map(int, sys.argv[1:] or ["50", "100", "200"]):
        spike(size)
        time.sleep(2)
