"""`_cert_days_from_not_after` не должен зависеть от `datetime.strptime`/LC_TIME:
OpenSSL всегда отдаёт английские месяцы независимо от локали сервера,
`%b`-парсинг под русской локалью не распознаёт "Jun" и молча вернёт None."""
import datetime as dt


def test_cert_expiry_parsing_does_not_depend_on_strptime(bot_tt, monkeypatch):
    class _BoomDatetime(dt.datetime):
        @classmethod
        def strptime(cls, *args, **kwargs):
            raise ValueError("simulates strptime failing under a non-English LC_TIME")

    monkeypatch.setattr(bot_tt.dt, "datetime", _BoomDatetime)

    days = bot_tt._cert_days_from_not_after("Jun 13 12:00:00 2099 GMT")

    assert days is not None, "разбор всё ещё завязан на locale-зависимый strptime"


def test_cert_expiry_parses_openssl_enddate_format(bot_tt):
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=30)
    not_after = future.strftime("%b %d %H:%M:%S %Y GMT")

    days = bot_tt._cert_days_from_not_after(not_after)

    assert days in (29, 30)


def test_cert_expiry_handles_empty_and_garbage_input(bot_tt):
    assert bot_tt._cert_days_from_not_after("") is None
    assert bot_tt._cert_days_from_not_after("garbage not a date") is None
