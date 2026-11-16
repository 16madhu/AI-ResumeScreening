"""
Unit tests for skill extraction, synonym normalization, and gap analysis.
"""

import pytest
from backend.skill_extractor import SkillExtractor


@pytest.fixture
def extractor():
    return SkillExtractor()


def test_synonym_normalization(extractor):
    # From Table 2 in proposal:
    # ML -> Machine Learning
    # NLP -> Natural Language Processing
    # JS -> JavaScript
    # Python programming -> Python
    # SQL database queries -> SQL
    sample_text = (
        "Experienced in ML and NLP techniques. Proficient with JS, "
        "Python programming, and executing SQL database queries."
    )
    result = extractor.extract_skills(sample_text)
    normalized = result["normalized_skills"]

    assert "Machine Learning" in normalized
    assert "Natural Language Processing" in normalized
    assert "JavaScript" in normalized
    assert "Python" in normalized
    assert "SQL" in normalized


def test_direct_vs_synonym_matches(extractor):
    sample_text = "Proficient in Python and ML."
    result = extractor.extract_skills(sample_text)

    assert "Python" in result["direct_matches"]
    
    # ML should be mapped as synonym match for Machine Learning
    synonym_normalized = [s["normalized"] for s in result["synonym_matches"]]
    assert "Machine Learning" in synonym_normalized


def test_skill_comparison_and_scoring(extractor):
    sample_text = "Skills: Python, SQL, and Data Analysis."
    skills_data = extractor.extract_skills(sample_text)

    required_skills = ["Python", "SQL", "Data Analysis", "Deep Learning"]
    comp = extractor.compare_skills(skills_data, required_skills)

    # 3 out of 4 matched = 75.0%
    assert comp["total_required"] == 4
    assert comp["total_matched"] == 3
    assert comp["skill_match_score"] == 75.0
    assert "Deep Learning" in comp["skills_not_detected"]
    assert comp["undetected_wording"] == "Skill not detected in resume"

