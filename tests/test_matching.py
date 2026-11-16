"""
Unit tests for Sentence-BERT embeddings, cosine similarity, hybrid scoring, and ranking.
"""

import pytest
from backend.skill_extractor import SkillExtractor
from backend.semantic_matcher import SemanticMatcher
from backend.hybrid_matcher import HybridMatcher
from backend.baselines import keyword_overlap_matching, tfidf_cosine_matching


@pytest.fixture(scope="module")
def semantic_matcher():
    return SemanticMatcher()


@pytest.fixture(scope="module")
def hybrid_matcher(semantic_matcher):
    extractor = SkillExtractor()
    return HybridMatcher(extractor, semantic_matcher)


def test_semantic_matcher_cosine_similarity(semantic_matcher):
    text_a = "Machine learning engineer building neural networks with PyTorch."
    text_b = "Deep learning specialist developing ML models using PyTorch."
    raw_sim, scaled_score = semantic_matcher.get_semantic_similarity_score(text_a, text_b)

    assert 0.0 <= raw_sim <= 1.0
    assert scaled_score > 60.0  # Semantically similar texts should score high


def test_hybrid_matching_formula(hybrid_matcher):
    resume = "Data Analyst skilled in SQL, Data Analysis, and Statistics."
    jd = "Seeking a Data Analyst to analyze data, run SQL queries, and generate statistical models."
    required_skills = ["SQL", "Data Analysis", "Statistics"]

    res = hybrid_matcher.evaluate_pair(resume, jd, required_skills, "Data Analyst")
    
    # Check hybrid score formula: 0.60 * Skill + 0.40 * Semantic
    expected = round((0.60 * res["skill_match_score"]) + (0.40 * res["semantic_similarity_score"]), 2)
    assert abs(res["final_hybrid_score"] - expected) < 0.05
    assert len(res["skills_not_detected"]) == 0
    assert "explanation" in res["calculation_explanation"].lower() or "hybrid score" in res["calculation_explanation"].lower()


def test_baselines_calculation():
    resume = "Python, machine learning, and data analysis."
    jd = "Data Analyst role with Python and data analysis required."

    score_kw = keyword_overlap_matching(resume, jd)
    score_tfidf = tfidf_cosine_matching(resume, jd)

    assert 0.0 <= score_kw <= 100.0
    assert 0.0 <= score_tfidf <= 100.0

