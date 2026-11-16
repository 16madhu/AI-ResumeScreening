"""
Module: hybrid_matcher.py
Implements the core hybrid matching and job role ranking engine.

Formula per Section 6 of the AIML Project Proposal:
Hybrid Score = 0.60 * Skill-Match Score + 0.40 * Semantic-Similarity Score
Skill-Match Score = (Number of matched recognized required skills / Total recognized required skills) * 100
Semantic-Similarity Score = (Cosine Similarity between Sentence-BERT embeddings) * 100

Provides explainable reports for top-3 recommended job roles per Section 7.
"""

from typing import List, Dict, Any
from backend.skill_extractor import SkillExtractor
from backend.semantic_matcher import SemanticMatcher


class HybridMatcher:
    def __init__(
        self,
        skill_extractor: SkillExtractor = None,
        semantic_matcher: SemanticMatcher = None,
        skill_weight: float = 0.60,
        semantic_weight: float = 0.40
    ):
        """
        Initializes the hybrid matcher with skill extractor and semantic matcher.
        Default weights are 0.60 (skill) and 0.40 (semantic) as specified in proposal.
        """
        self.skill_extractor = skill_extractor or SkillExtractor()
        self.semantic_matcher = semantic_matcher or SemanticMatcher()
        self.skill_weight = skill_weight
        self.semantic_weight = semantic_weight

    def evaluate_pair(
        self,
        resume_text: str,
        jd_text: str,
        required_skills: List[str],
        job_title: str,
        job_id: int = None
    ) -> Dict[str, Any]:
        """
        Evaluates a single resume against a job description.
        Generates full explainability metrics and hybrid match score.
        """
        # 1. Skill Extraction & Normalization on Resume
        resume_skills_data = self.skill_extractor.extract_skills(resume_text)

        # 2. Skill Comparison against required skills
        skill_comp = self.skill_extractor.compare_skills(resume_skills_data, required_skills)
        skill_match_score = skill_comp["skill_match_score"]

        # 3. Sentence-BERT Semantic Similarity
        raw_cosine, semantic_score = self.semantic_matcher.get_semantic_similarity_score(
            resume_text, jd_text
        )

        # 4. Hybrid Matching Score Calculation
        # Fallback handling: If no required skills were recognized, rely 100% on semantic similarity
        if skill_comp["total_required"] == 0:
            final_hybrid_score = semantic_score
            calculation_explanation = (
                f"Fallback rule applied: Job description contains no recognized skills. "
                f"Final score is 100% based on Sentence-BERT semantic similarity ({semantic_score:.1f}%)."
            )
        else:
            final_hybrid_score = (self.skill_weight * skill_match_score) + (self.semantic_weight * semantic_score)
            calculation_explanation = (
                f"Hybrid Score calculated as: 0.60 × Skill-Match Score ({skill_match_score:.1f}%) + "
                f"0.40 × Semantic-Similarity Score ({semantic_score:.1f}%) = {final_hybrid_score:.1f}%. "
                f"Scores are matching indicators, not guarantees of employment or suitability."
            )

        final_hybrid_score = round(final_hybrid_score, 2)

        return {
            "job_id": job_id,
            "job_title": job_title,
            "skill_match_score": skill_match_score,
            "semantic_similarity_score": semantic_score,
            "raw_cosine_similarity": raw_cosine,
            "final_hybrid_score": final_hybrid_score,
            "direct_matched_skills": skill_comp["direct_matched_skills"],
            "synonym_matched_skills": skill_comp["synonym_matched_skills"],
            "skills_not_detected": skill_comp["skills_not_detected"],
            "additional_resume_skills": skill_comp["additional_resume_skills"],
            "matched_skills_count": skill_comp["total_matched"],
            "required_skills_count": skill_comp["total_required"],
            "calculation_explanation": calculation_explanation,
            "undetected_wording": skill_comp["undetected_wording"]
        }

    def rank_jobs(
        self,
        resume_text: str,
        job_catalog: List[Dict[str, Any]],
        top_n: int = 3
    ) -> Dict[str, Any]:
        """
        Ranks all available jobs in the catalog for a given resume and returns top-N recommendations.
        """
        ranked_results = []
        for job in job_catalog:
            res = self.evaluate_pair(
                resume_text=resume_text,
                jd_text=job.get("description", ""),
                required_skills=job.get("required_skills", []),
                job_title=job.get("title", "Untitled Role"),
                job_id=job.get("id")
            )
            # Attach job domain if present
            res["domain"] = job.get("domain", "")
            res["description"] = job.get("description", "")
            ranked_results.append(res)

        # Sort descending by final hybrid score
        ranked_results.sort(key=lambda item: item["final_hybrid_score"], reverse=True)

        top_recommendations = ranked_results[:top_n]

        # Calculate aggregated overall score for the top match
        overall_match = top_recommendations[0]["final_hybrid_score"] if top_recommendations else 0.0

        return {
            "total_jobs_evaluated": len(ranked_results),
            "top_recommendations": top_recommendations,
            "all_rankings": ranked_results,
            "overall_top_match": overall_match,
            "weights_used": {
                "skill_weight": self.skill_weight,
                "semantic_weight": self.semantic_weight
            }
        }

