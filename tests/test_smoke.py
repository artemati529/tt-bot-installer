def test_module_loads(bot_tt):
    assert bot_tt.ALLOWED_USER_ID == 111111
    assert bot_tt.SERVER_NAME == "testserver"


def test_tt_paths_fixture_redirects_files(bot_tt, tt_paths):
    assert bot_tt.CRED_FILE == tt_paths["CRED_FILE"]
    assert not bot_tt.CRED_FILE.exists()
