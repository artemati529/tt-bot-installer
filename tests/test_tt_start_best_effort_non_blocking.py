"""_tt_start_best_effort() calls run_process() (blocking subprocess.Popen +
proc.wait(timeout=40)) — bot.py:733 documents that systemctl calls must run
off the event loop, or a hung call freezes the whole bot for the full
timeout. _tt_start_best_effort was called directly (not via
asyncio.to_thread) from _tt_upgrade_task's rollback paths, so a slow
systemctl call there blocks every other coroutine in the process."""
import asyncio
import time
from unittest.mock import AsyncMock


def test_rollback_path_does_not_block_the_event_loop(bot_tt, run_async, monkeypatch, tt_paths):
    binary = tt_paths["TT_DIR"] / "trusttunnel_endpoint"
    binary.write_bytes(b"old-good-binary")

    monkeypatch.setattr(bot_tt, "_tt_stop_sync", lambda: None)

    def fail_install(version):
        return 1, "", "install failed"

    monkeypatch.setattr(bot_tt, "_tt_install_sync", fail_install)

    def slow_run_process(cmd, **kw):
        time.sleep(0.05)

    monkeypatch.setattr(bot_tt, "run_process", slow_run_process)

    gaps = []

    async def ticker():
        prev = time.monotonic()
        for _ in range(40):
            await asyncio.sleep(0.002)
            now = time.monotonic()
            gaps.append(now - prev)
            prev = now

    async def scenario():
        ticker_task = asyncio.ensure_future(ticker())
        bot = AsyncMock()
        await bot_tt._tt_upgrade_task(bot, 111111, 77, {"current": "1.0.0", "latest": "v1.2.3"})
        await asyncio.sleep(0.01)
        ticker_task.cancel()

    run_async(scenario())

    # A ticker awakened every ~2ms should never see a gap anywhere near the
    # ~50ms sync sleep inside run_process — if it does, the event loop was
    # stalled by a call that should have gone through asyncio.to_thread.
    assert max(gaps) < 0.03, f"event loop stalled for {max(gaps):.3f}s — a blocking call ran on the loop"
