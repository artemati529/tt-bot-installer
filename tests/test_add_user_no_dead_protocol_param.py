"""add_user_and_make_link/_add_user_bundle_sync never used their protocol
param — generate_deeplink dropped it earlier this session, this call
chain was missed."""
import inspect


def test_add_user_and_make_link_has_no_protocol_param(bot_tt):
    assert "protocol" not in inspect.signature(bot_tt.add_user_and_make_link).parameters


def test_add_user_bundle_sync_has_no_protocol_param(bot_tt):
    assert "protocol" not in inspect.signature(bot_tt._add_user_bundle_sync).parameters
