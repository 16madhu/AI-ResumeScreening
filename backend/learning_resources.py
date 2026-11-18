"""Build learning links for skills not detected in a resume."""

from typing import Dict, List
from urllib.parse import urlencode


def get_learning_resources(skills: List[object]) -> List[Dict[str, object]]:
    """Return free-learning and paid-course search links for each unique skill."""
    resources = []
    seen = set()

    for skill in skills:
        if not isinstance(skill, str) or not skill.strip():
            continue

        skill_name = skill.strip()
        normalized_name = skill_name.casefold()
        if normalized_name in seen:
            continue
        seen.add(normalized_name)

        free_query = urlencode({"search_query": f"{skill_name} free full course"})
        paid_query = urlencode({"q": skill_name, "price": "price-paid"})
        resources.append({
            "skill": skill_name,
            "courses": [
                {
                    "label": "Free video courses",
                    "provider": "YouTube",
                    "price_type": "Free",
                    "url": f"https://www.youtube.com/results?{free_query}"
                },
                {
                    "label": "Paid course options",
                    "provider": "Udemy",
                    "price_type": "Paid",
                    "url": f"https://www.udemy.com/courses/search/?{paid_query}"
                }
            ]
        })

    return resources
