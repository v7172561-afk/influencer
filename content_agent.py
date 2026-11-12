from __future__ import annotations

import json
import re

from config import get_setting


def _fallback_content(profile: dict, style: str, topic: str) -> dict[str, str]:
    subject = topic.strip() or f"a thoughtful {profile.get('niche', 'lifestyle').lower()} moment"
    name = profile.get("name", "our virtual creator")
    if style == "animated":
        visual = (
            f"Create an original, polished animated illustration of a fictional adult virtual influencer named {name}. "
            f"Scene: {subject}. Expressive character design, coherent anatomy, refined colors, clean composition, "
            "vertical 4:5 social post, no text, no watermark, no logos, no resemblance to a real person."
        )
    else:
        visual = (
            f"Create a photorealistic editorial lifestyle photograph of a fictional adult virtual influencer named {name}. "
            f"Scene: {subject}. Natural lighting, believable details, tasteful styling, vertical 4:5 composition, "
            "no text, no watermark, no logos, and no resemblance to a real person."
        )
    return {
        "caption": f"A little inspiration for today: {subject}. What would you try first?",
        "hashtags": "#VirtualCreator #LifestyleInspiration #CreativeDaily #AIInfluencer",
        "visual_prompt": visual,
        "alt_text": f"A {style} visual of a fictional adult virtual creator illustrating {subject}.",
    }


def generate_content(profile: dict, style: str, topic: str = "") -> dict[str, str]:
    api_key = get_setting("GROQ_API_KEY", "").strip()
    if not api_key:
        return _fallback_content(profile, style, topic)

    from groq import Groq

    model = get_setting("GROQ_MODEL", "openai/gpt-oss-20b")
    client = Groq(api_key=api_key)
    system = (
        "You are the content planner for one fictional adult virtual influencer. "
        "Do not impersonate real people, imply the character is a real human, invent personal experiences, "
        "make deceptive endorsements, or make medical/financial claims. Return only valid JSON with keys "
        "caption, hashtags, visual_prompt, alt_text. Keep the caption natural and platform-appropriate."
    )
    user = f"""Influencer name: {profile.get('name')}
Niche: {profile.get('niche')}
Bio: {profile.get('bio')}
Personality: {profile.get('personality')}
Visual style for this post: {style}
Topic: {topic or 'Choose a fresh, useful topic within the influencer niche.'}

Write one original Instagram image-post draft. The visual prompt must specify a fictional adult character (21+),
match the selected style, vertical 4:5 composition, and exclude text/watermarks/logos/real-person likenesses.
Return JSON only. Hashtags should be a space-separated string."""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.8,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    required = ("caption", "hashtags", "visual_prompt", "alt_text")
    cleaned = {key: str(data.get(key, "")).strip() for key in required}
    if any(not cleaned[key] for key in required):
        raise ValueError("AI returned an incomplete content draft. Please retry.")
    return cleaned
