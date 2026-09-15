"""Malformed TOML export callback data must no-op."""


def test_malformed_tp_callback_data_does_not_raise(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("tp:onlyoneparthere")

    run_async(bot_tt.toml_export_callback(update, context))


def test_stale_routing_step_callback_data_is_a_silent_noop(bot_tt, allowed_callback_update, context, run_async):
    """Stale routing callbacks must be ignored."""
    for stale in ("tr:h2:missingusername", "ts:h2:1:std:alice"):
        update = allowed_callback_update(stale)
        run_async(bot_tt.toml_export_callback(update, context))
