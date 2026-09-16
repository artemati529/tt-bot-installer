"""build_rules_sync_report's list sections (orphan rules, missing rules,
orphan map entries, stale profiles) can get long — wrap each in a
collapsible <blockquote expandable> instead of a flat <pre> block."""


def test_orphan_rule_prefixes_section_is_expandable(bot_tt, monkeypatch):
    monkeypatch.setattr(
        bot_tt,
        "audit_rules_sync",
        lambda: {
            "users": ["alice"],
            "orphan_rule_prefixes": ["pfx-orphan"],
            "missing_rules": {},
            "orphan_map_entries": {},
            "stale_profiles": [],
        },
    )

    report = bot_tt.build_rules_sync_report()

    assert "<blockquote expandable><pre>" in report
    assert "pfx-orphan" in report


def test_no_discrepancies_stays_short_non_expandable(bot_tt, monkeypatch):
    monkeypatch.setattr(
        bot_tt,
        "audit_rules_sync",
        lambda: {
            "users": ["alice"],
            "orphan_rule_prefixes": [],
            "missing_rules": {},
            "orphan_map_entries": {},
            "stale_profiles": [],
        },
    )

    report = bot_tt.build_rules_sync_report()

    assert "Расхождений не найдено" in report
    assert "<blockquote expandable>" not in report
