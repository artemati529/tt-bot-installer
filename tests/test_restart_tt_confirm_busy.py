"""restart_tt_confirm_callback runs apply_tt_config_change (a systemctl
restart, ~10-40s) without ever calling busy_set — unlike the OS/TT upgrade
confirm flows. A backup/upgrade tapped while the restart is still in
flight isn't rejected by _reject_if_busy, and could race with it (both
touching config files / restarting services around the same time)."""


def test_restart_tt_confirm_sets_busy_during_restart(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    seen = {}

    def fake_apply(**kwargs):
        seen["label"] = bot_tt.busy_label()

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", fake_apply)
    update = allowed_callback_update("ttrst_yes")

    run_async(bot_tt.restart_tt_confirm_callback(update, context))

    assert seen.get("label") is not None, "busy_set was not active while apply_tt_config_change ran"
    assert bot_tt.busy_label() is None, "busy state was not cleared after the restart finished"


def test_restart_tt_confirm_clears_busy_on_failure(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    def fake_apply(**kwargs):
        raise bot_tt.CommandError("boom")

    monkeypatch.setattr(bot_tt, "apply_tt_config_change", fake_apply)
    update = allowed_callback_update("ttrst_yes")

    run_async(bot_tt.restart_tt_confirm_callback(update, context))

    assert bot_tt.busy_label() is None, "busy state must be cleared even when the restart fails"
