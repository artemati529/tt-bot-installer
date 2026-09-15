"""build_logs_view не должен резать текст по LOG_CHUNK_CHARS символов —
граница чанка могла прийтись на середину строки журнала, разрывая её пополам
между "Часть N/M" и "Часть N+1/M". Чанки собираются из целых строк, ни одна
строка не режется (кроме патологического случая одной строки длиннее лимита
самой по себе)."""


def test_chunk_boundary_never_splits_a_log_line_in_half(bot_tt, monkeypatch):
    # Строка A такой длины, что строка B не влезет целиком в первый чанк
    # при character-based резке где-то посередине неё (раньше именно так
    # и происходило: первый чанк обрывался на "AAA...BBB" ровно на границе).
    line_a = "A" * 3190
    line_b = "B" * 100
    raw = f"{line_a}\n{line_b}"
    monkeypatch.setattr(bot_tt, "_fetch_logs_raw", lambda *a, **k: (0, raw, ""))

    text_p1, _, total_chunks = bot_tt.build_logs_view(level="all", lines=50, chunk=0)
    assert total_chunks == 2
    text_p2, _, _ = bot_tt.build_logs_view(level="all", lines=50, chunk=1)

    assert line_b in text_p2
    assert line_b not in text_p1
    assert line_a not in text_p2


def test_short_log_fits_in_a_single_chunk(bot_tt, monkeypatch):
    monkeypatch.setattr(bot_tt, "_fetch_logs_raw", lambda *a, **k: (0, "line one\nline two", ""))

    text, _, total_chunks = bot_tt.build_logs_view(level="all", lines=50, chunk=0)

    assert total_chunks == 1
    assert "line one" in text
    assert "line two" in text
