from videoflow.domain.redact import redact


def test_secret_is_replaced() -> None:
    assert redact("key=abc123", ["abc123"]) == "key=[REDACTED]"


def test_multiple_secrets_and_missing_ones() -> None:
    text = "one alpha two beta"
    assert redact(text, ["alpha", "beta"]) == "one [REDACTED] two [REDACTED]"
    assert redact(text, ["gamma"]) == text


def test_empty_secret_is_ignored() -> None:
    assert redact("unchanged", [""]) == "unchanged"
