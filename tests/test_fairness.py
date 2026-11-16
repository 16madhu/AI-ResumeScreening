"""
Unit tests for Fairness Sensitivity Check.
"""

import pytest
from backend.fairness import FairnessSensitivityChecker
from backend.hybrid_matcher import HybridMatcher
from backend.data_loader import get_sample_job_descriptions


def test_fairness_sensitivity():
    checker = FairnessSensitivityChecker()
    resume_text = (
        "Experienced Machine Learning Engineer with 3 years developing predictive models. "
        "Proficient in Python, Machine Learning, Deep Learning, PyTorch, and Scikit-Learn."
    )
    jobs = [
        {
            "id": 1,
            "title": "Machine Learning Engineer",
            "domain": "Machine Learning",
            "description": "Build ML models using Python, Deep Learning, and PyTorch.",
            "required_skills": ["Python", "Machine Learning", "Deep Learning", "PyTorch"]
        },
        {
            "id": 2,
            "title": "Web Developer",
            "domain": "Web Development",
            "description": "Frontend development with JavaScript, React, HTML, and CSS.",
            "required_skills": ["JavaScript", "HTML", "CSS", "React"]
        }
    ]

    report = checker.run_sensitivity_test(resume_text, jobs)

    assert report["test_status"] == "Passed"
    assert report["rank_order_identical"] is True
    assert report["score_delta"] < 2.0
    assert "disclaimer" in report

