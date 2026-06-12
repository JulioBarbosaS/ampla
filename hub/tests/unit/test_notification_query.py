"""Filter-qualifier parser examples (the property-based invariants live in
test_properties.py)."""

from app.core.notification_query import parse_filter_query


def test_is_qualifier_is_overloaded_across_fields():
    assert parse_filter_query("is:unread").unread is True
    assert parse_filter_query("is:read").unread is False
    assert parse_filter_query("is:saved").status == "saved"
    assert parse_filter_query("is:dm").subject_type == "dm"
    assert parse_filter_query("is:mention").subject_type == "mention"


def test_reason_agent_and_from_qualifiers():
    parsed = parse_filter_query("reason:approval_requested agent:backend-julio from:mobile-eduardo")
    assert parsed.reason == "approval_requested"
    assert parsed.agent_slug == "backend-julio"
    assert parsed.actor == "mobile-eduardo"


def test_unknown_and_bare_tokens_are_ignored():
    parsed = parse_filter_query("  bananas is:bogus reason:not-a-reason label:x plain words  ")
    assert parsed == parse_filter_query(None)  # nothing recognized → empty filter


def test_empty_and_none_are_empty_filters():
    assert parse_filter_query("") == parse_filter_query(None)
    assert parse_filter_query("   ").status is None


def test_last_write_wins_for_repeated_qualifier():
    assert parse_filter_query("is:inbox is:done").status == "done"
