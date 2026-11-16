"""
Module: fairness.py
Implements the Fairness Sensitivity Check mandated by Section 10 of the proposal:

"A limited test will compare rankings before and after adding irrelevant contact details,
such as an email address or phone number, to otherwise identical resume text. This check
will report whether rankings or scores change. It is a limited sensitivity check,
not proof of complete fairness."
"""

from typing import Dict, List, Any
from backend.hybrid_matcher import HybridMatcher
from backend.pii_masker import mask_pii

FAIRNESS_DISCLAIMER = (
    "Fairness Sensitivity Disclaimer: This check verifies that rankings and scores do not "
    "shift significantly when irrelevant contact information (such as an email address or phone number) "
    "is injected into otherwise identical resume text. It is a limited sensitivity check, not proof "
    "of complete algorithmic fairness. Sensitive attributes (gender, age, ethnicity, photographs) "
    "are not processed or used for candidate ranking."
)


class FairnessSensitivityChecker:
    def __init__(self, hybrid_matcher: HybridMatcher = None):
        self.hybrid_matcher = hybrid_matcher or HybridMatcher()

    def run_sensitivity_test(
        self,
        resume_text: str,
        job_catalog: List[Dict[str, Any]],
        irrelevant_contact_details: str = (
            "\nContact Info: candidate.testing@example.com | +1 (555) 234-5678 | https://linkedin.com/in/testcandidate"
        )
    ) -> Dict[str, Any]:
        """
        Compares job role rankings before and after injecting irrelevant contact details into resume text.
        """
        if not resume_text.strip():
            return {
                "status": "error",
                "message": "Resume text is empty, cannot perform fairness check.",
                "disclaimer": FAIRNESS_DISCLAIMER
            }

        # 1. Baseline Run: Mask original text and rank
        masked_orig, meta_orig = mask_pii(resume_text)
        orig_ranking = self.hybrid_matcher.rank_jobs(masked_orig, job_catalog, top_n=3)

        # 2. Perturbed Run: Append irrelevant contact info, mask, and rank
        perturbed_raw = resume_text + "\n" + irrelevant_contact_details
        masked_perturbed, meta_pert = mask_pii(perturbed_raw)
        pert_ranking = self.hybrid_matcher.rank_jobs(masked_perturbed, job_catalog, top_n=3)

        # 3. Analyze differences
        orig_top_roles = [j["job_title"] for j in orig_ranking["top_recommendations"]]
        pert_top_roles = [j["job_title"] for j in pert_ranking["top_recommendations"]]

        orig_top_score = orig_ranking["top_recommendations"][0]["final_hybrid_score"] if orig_top_roles else 0.0
        pert_top_score = pert_ranking["top_recommendations"][0]["final_hybrid_score"] if pert_top_roles else 0.0

        score_diff = abs(orig_top_score - pert_top_score)
        rank_order_identical = (orig_top_roles == pert_top_roles)

        # Robustness check per proposal Section 10:
        # Check whether rankings change and report score drift
        rank_order_identical = (orig_top_roles == pert_top_roles)
        passed_test = rank_order_identical and (score_diff < 5.0)

        if rank_order_identical and score_diff < 1.0:
            status_desc = "Highly Robust (Rankings and scores remained invariant)"
        elif rank_order_identical:
            status_desc = f"Rankings Preserved (Minor semantic score delta of {score_diff:.2f}%)"
        else:
            status_desc = "Rank Shift Detected upon contact detail perturbation"

        return {
            "test_status": "Passed" if passed_test else "Sensitivity Detected",
            "rank_order_identical": rank_order_identical,
            "original_top_3": orig_top_roles,
            "perturbed_top_3": pert_top_roles,
            "original_top_score": orig_top_score,
            "perturbed_top_score": pert_top_score,
            "score_delta": round(score_diff, 2),
            "pii_masked_in_original": meta_orig["total_masked"],
            "pii_masked_in_perturbed": meta_pert["total_masked"],
            "summary": status_desc,
            "disclaimer": FAIRNESS_DISCLAIMER
        }
