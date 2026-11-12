from agents.content_agent import _fallback_content


def test_fallback_has_required_fields():
    result = _fallback_content(
        {"name": "Nova", "niche": "Fashion"}, "realistic", "casual summer look"
    )
    assert set(result) == {"caption", "hashtags", "visual_prompt", "alt_text"}
    assert "fictional adult" in result["visual_prompt"]
    assert "casual summer look" in result["caption"]
