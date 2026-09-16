"""nav_callback — плоская цепочка if/return без хвостового else: неизвестный
nav:* так и не получает answerCallbackQuery, кнопка крутит спиннер до таймаута."""


def test_nav_callback_answers_unknown_subroute(bot_tt, allowed_callback_update, context, run_async):
    update = allowed_callback_update("nav:doesnotexist")

    run_async(bot_tt.nav_callback(update, context))

    assert update.callback_query.answer.await_count == 1
