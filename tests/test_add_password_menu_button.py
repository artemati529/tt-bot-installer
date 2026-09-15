"""Password input accepts plain text after reply-keyboard compatibility removal."""


def test_real_password_text_is_still_accepted(bot_tt, allowed_update, context, run_async):
    context.user_data["pending_add_username"] = "newuser"

    update = allowed_update("hunter2-not-a-menu-button")
    run_async(bot_tt.add_password(update, context))

    assert context.user_data.get("pending_add_password") == "hunter2-not-a-menu-button"
