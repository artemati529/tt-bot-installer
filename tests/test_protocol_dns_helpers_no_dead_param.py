"""_protocol_dns_values/_protocol_dns_label never used their protocol
argument (DoQ needs both upstreams regardless of tunnel protocol) — the
parameter was dead, not just unused-for-API-symmetry."""
import inspect


def test_protocol_dns_values_takes_no_arguments(bot_tt):
    assert list(inspect.signature(bot_tt._protocol_dns_values).parameters) == []


def test_protocol_dns_label_takes_no_arguments(bot_tt):
    assert list(inspect.signature(bot_tt._protocol_dns_label).parameters) == []
