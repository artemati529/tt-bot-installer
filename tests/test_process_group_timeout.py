"""Command timeout must terminate the whole process group."""
import os
import time

import pytest


def test_timeout_kills_whole_process_group(bot_tt, tmp_path):
    pidfile = tmp_path / "child.pid"
    # Spawn a long-lived grandchild behind the shell.
    cmd = ["bash", "-c", f"sleep 30 & echo $! > {pidfile}; wait"]

    with pytest.raises(bot_tt.CommandError):
        bot_tt.run_process(cmd, timeout=1, retries=0, check=False)

    # Give the OS a brief moment to reap the killed process.
    deadline = time.monotonic() + 2
    pid = int(pidfile.read_text().strip())
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.1)

    assert not alive, "grandchild process survived as an orphan after the timeout"


def test_run_process_capture_limit_does_not_wait_on_grandchild_pipe(bot_tt):
    """A backgrounded grandchild that inherits stdout/stderr (common with
    daemonizing postinst scripts during apt upgrades) keeps the pipe's write
    end open long after the direct child exits — proc.wait() returns
    immediately, but the reader threads' pipe.read() only unblocks on EOF,
    i.e. when every holder of the write end is gone. Without a bound on
    t.join(), run_process would hang for however long the grandchild lives."""
    start = time.monotonic()
    p = bot_tt.run_process(["bash", "-c", "( sleep 20 ) & exec true"], timeout=10, capture_limit=1000)
    elapsed = time.monotonic() - start

    assert p.returncode == 0
    assert elapsed < 8, f"run_process blocked {elapsed:.2f}s waiting on a grandchild-held pipe"


def test_run_process_capture_limit_keeps_only_output_tail(bot_tt):
    p = bot_tt.run_process(
        ["bash", "-lc", "printf BEGIN; head -c 5000 /dev/zero | tr '\\0' x; printf END"],
        timeout=5,
        capture_limit=128,
    )

    assert len(p.stdout) <= 128
    assert p.stdout.endswith("END")
    assert "BEGIN" not in p.stdout
