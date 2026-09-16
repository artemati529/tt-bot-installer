"""generate_deeplink's protocol parameter was never used — the endpoint's
deeplink format has no protocol field (unlike TOML export, which does
honor it via upstream_protocol). Removed instead of documenting it away."""
import inspect


def test_generate_deeplink_has_no_protocol_parameter(bot_tt):
    assert "protocol" not in inspect.signature(bot_tt.generate_deeplink).parameters
