"""Add-user callback entry must clear stale rotate-password state."""
from unittest.mock import MagicMock


def test_add_entry_cb_clears_stale_rotate_wait(
    bot_tt, allowed_update, allowed_callback_update, context, run_async, monkeypatch
):
    apply_mock = MagicMock(return_value=(None, None))
    monkeypatch.setattr(bot_tt, "_apply_rotate_password_sync", apply_mock)

    context.user_data["pending_rotate_username"] = "alice"
    run_async(bot_tt.add_entry_cb(allowed_callback_update("vpn:add"), context))
    run_async(bot_tt.rotate_password_input(allowed_update("bobphone"), context))

    apply_mock.assert_not_called()
