"""Rule-block parsing must preserve trailing non-tag comments."""

CUSTOM_TAIL_COMMENT = "# my hand-written note, do not remove\n"
REAL_SHAPE = (
    '# user: iphone7\n'
    '[[rule]]\n'
    'client_random_prefix = "8340c144/c7c3e167"\n'
    'action = "allow"\n'
    + CUSTOM_TAIL_COMMENT
)


def test_block_end_stops_before_trailing_non_tag_comment(bot_tt):
    lines = REAL_SHAPE.splitlines(keepends=True)

    found = bot_tt._next_rule_block(lines, 0)

    assert found is not None
    block_start, rule_start, block_end = found
    assert block_start == 0
    assert rule_start == 1
    assert lines[block_end] == CUSTOM_TAIL_COMMENT, (
        f"block swallowed trailing comment: block_end line was {lines[block_end]!r}"
    )


def test_removing_the_rule_preserves_trailing_comment(bot_tt, tt_paths):
    tt_paths["RULES_FILE"].write_text(REAL_SHAPE, encoding="utf-8")

    removed = bot_tt._remove_prefix_rules_for_user([], "iphone7")

    assert removed == 1
    remaining = tt_paths["RULES_FILE"].read_text(encoding="utf-8")
    assert CUSTOM_TAIL_COMMENT.strip() in remaining
