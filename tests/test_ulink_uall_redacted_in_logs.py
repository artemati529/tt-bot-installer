"""ulink/uall carry a real username in callback_data just like udev/uqr/utc/
urot — but were missing from the redaction set, so tapping "Ссылка"/"Всё"
logged the username in cleartext while sibling actions masked it."""


def test_ulink_and_uall_are_in_the_redaction_set(bot_tt):
    assert "ulink" in bot_tt.CALLBACK_ROUTES_WITH_USER_ARGS
    assert "uall" in bot_tt.CALLBACK_ROUTES_WITH_USER_ARGS


def test_safe_callback_route_masks_ulink_and_uall(bot_tt):
    assert bot_tt.safe_callback_route("ulink:ivan") == "ulink:<arg>"
    assert bot_tt.safe_callback_route("uall:ivan") == "uall:<arg>"
