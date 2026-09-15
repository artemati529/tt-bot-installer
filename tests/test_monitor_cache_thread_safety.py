"""MONITOR_CACHE читается/пишется из разных потоков (asyncio.to_thread).
Промах кэша по одному ключу не должен запускать producer N раз (thundering
herd): только один поток считает, остальные ждут и получают готовое значение."""
import threading
import time


def test_cached_compute_single_flight_per_key(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "MONITOR_CACHE", {})

    calls = 0
    calls_lock = threading.Lock()

    def producer():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)  # имитируем медленный subprocess
        return "value"

    n = 8
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        barrier.wait()
        results[i] = bot_tt.cached_compute("hotkey", 60, producer)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r == "value" for r in results), results
    assert calls == 1, f"producer вызван {calls} раз при одном промахе кэша (thundering herd)"


def test_cached_compute_serves_fresh_hit_after_first_compute(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "MONITOR_CACHE", {})
    calls = []

    def producer():
        calls.append(1)
        return "v"

    first = bot_tt.cached_compute("k2", 60, producer)
    second = bot_tt.cached_compute("k2", 60, producer)
    assert first == second == "v"
    assert len(calls) == 1, "второе чтение должно прийти из кэша"
