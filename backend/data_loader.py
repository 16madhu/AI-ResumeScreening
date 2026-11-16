"""
Module: data_loader.py
Loads job descriptions catalog and benchmark evaluation dataset for baseline comparisons.
"""

import os
import json
from typing import List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def get_sample_job_descriptions() -> List[Dict[str, Any]]:
    """
    Loads standard job descriptions covering the 5 required domains:
    Data Analyst, Python Developer, Machine Learning Engineer, Web Developer, Data Scientist.
    """
    file_path = os.path.join(DATA_DIR, "job_descriptions.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_benchmark_test_dataset() -> List[Dict[str, Any]]:
    """
    Returns labelled synthetic evaluation test samples with target job roles and expected skills
    per Sections 5 & 9 of the proposal.
    """
    return [
        {
            "id": "sample-1",
            "candidate_name": "Synthetic ML Candidate",
            "resume_text": (
                "Experienced Machine Learning Engineer with 3 years building deep neural networks. "
                "Skilled in Python, PyTorch, Scikit-Learn, Deep Learning, and NLP models. "
                "Designed recommendation engines and deployed predictive algorithms."
            ),
            "target_roles": ["Machine Learning Engineer", "Data Scientist"],
            "expected_skills": ["Python", "Machine Learning", "Deep Learning", "PyTorch", "Scikit-Learn", "Natural Language Processing"]
        },
        {
            "id": "sample-2",
            "candidate_name": "Synthetic Data Analyst",
            "resume_text": (
                "Data Analyst with 2 years analyzing relational data, writing complex SQL queries, "
                "and building interactive Power BI dashboards. Strong knowledge of Statistics, "
                "Data Analysis, and business reporting."
            ),
            "target_roles": ["Data Analyst", "Data Scientist"],
            "expected_skills": ["SQL", "Data Analysis", "Statistics", "Power BI"]
        },
        {
            "id": "sample-3",
            "candidate_name": "Synthetic Python Backend Dev",
            "resume_text": (
                "Backend developer specializing in Python, Flask, and Django REST APIs. "
                "Proficient with SQL database queries, Docker containerization, and Git version control. "
                "Built microservices and scalable web applications."
            ),
            "target_roles": ["Python Developer", "Web Developer"],
            "expected_skills": ["Python", "Flask", "Django", "SQL", "Docker", "Git"]
        },
        {
            "id": "sample-4",
            "candidate_name": "Synthetic Web Developer",
            "resume_text": (
                "Frontend web engineer proficient in JavaScript, React, HTML, and CSS. "
                "Experience building responsive single-page applications with Node.js and Git."
            ),
            "target_roles": ["Web Developer"],
            "expected_skills": ["JavaScript", "React", "HTML", "CSS", "Node.js", "Git"]
        },
        {
            "id": "sample-5",
            "candidate_name": "Synthetic Data Scientist",
            "resume_text": (
                "Data Scientist experienced with statistical modeling, predictive analytics, "
                "and machine learning. Expert in Python, SQL, Statistics, Pandas, and Data Analysis."
            ),
            "target_roles": ["Data Scientist", "Machine Learning Engineer", "Data Analyst"],
            "expected_skills": ["Python", "SQL", "Statistics", "Data Analysis", "Machine Learning", "Pandas"]
        },
        {
            "id": "sample-6",
            "candidate_name": "Synthetic DevOps Engineer",
            "resume_text": (
                "DevOps engineer experienced in Docker containerization, Kubernetes cluster management, "
                "CI/CD automation, AWS cloud services, and Linux infrastructure administration."
            ),
            "target_roles": ["DevOps Engineer", "Cloud Architect"],
            "expected_skills": ["Docker", "Kubernetes", "CI/CD", "AWS", "Cloud Computing", "Linux"]
        },
        {
            "id": "sample-7",
            "candidate_name": "Synthetic Cybersecurity Specialist",
            "resume_text": (
                "Cybersecurity analyst skilled in network security monitoring, penetration testing, "
                "vulnerability assessments, Linux security hardening, and cloud security compliance."
            ),
            "target_roles": ["Cybersecurity Analyst"],
            "expected_skills": ["Cyber Security", "Network Security", "Penetration Testing", "Linux", "Cloud Computing"]
        }
    ]

