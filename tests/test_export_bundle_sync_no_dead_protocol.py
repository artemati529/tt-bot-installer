"""_export_bundle_sync's protocol override stopped affecting anything once
generate_deeplink dropped its own dead protocol param — the computed
proto/prof_proto value went nowhere. Removed rather than left inert."""
import inspect


def test_export_bundle_sync_has_no_protocol_parameter(bot_tt):
    assert "protocol" not in inspect.signature(bot_tt._export_bundle_sync).parameters
