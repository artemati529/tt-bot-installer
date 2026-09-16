"""_send_user_qr called _export_context_for_username (JSON+TOML disk reads)
directly on the event loop, unlike _export_bundle_sync two lines below it."""
import inspect


def test_export_context_lookup_is_off_thread(bot_tt):
    src = inspect.getsource(bot_tt._send_user_qr)
    assert "asyncio.to_thread(_export_context_for_username" in src
