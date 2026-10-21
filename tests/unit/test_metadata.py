from videoflow.application.metadata import generate_metadata


def test_metadata_is_platform_aware_and_bounded() -> None:
    result = generate_metadata(
        "This cooking pasta recipe uses fresh basil. It is quick and simple.",
        title="Fresh basil pasta",
        platform="youtube",
        tone="educational",
    )
    assert result.platform == "youtube"
    assert result.title == "Fresh basil pasta"
    assert "#Shorts" in result.hashtags
    assert result.hashtags[0].startswith("#")
    assert len(result.title) <= 100
    assert len(result.description) <= 5000
    assert result.description.endswith(result.hashtags[-1])


def test_metadata_uses_first_sentence_and_tone_cta() -> None:
    result = generate_metadata(
        "The finance market crashed after the bank decision. Here is why.",
        platform="linkedin",
        tone="professional",
    )
    assert result.title.startswith("The finance market crashed")
    assert "practical takeaway" in result.description
    assert "#Insights" in result.hashtags


def test_unknown_platform_or_tone_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        generate_metadata("text", platform="myspace")
    with pytest.raises(ValueError):
        generate_metadata("text", tone="unknown")
