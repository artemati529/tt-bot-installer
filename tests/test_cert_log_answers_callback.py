"""cert_log_callback — единственный маршрут в файле, который не отвечал на
callback-query (не звал cb_answer): кнопка "20"/"50" вечно крутила спиннер."""


def test_cert_log_callback_answers_the_callback(bot_tt, allowed_callback_update, context, run_async, monkeypatch):
    monkeypatch.setattr(bot_tt, "get_certbot_log_tail", lambda lines: "log tail")
    update = allowed_callback_update("certlog:20")

    run_async(bot_tt.cert_log_callback(update, context))

    assert update.callback_query.answer.await_count == 1
