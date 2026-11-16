"""
Module: skill_extractor.py
Implements maintainable skill extraction, synonym normalization,
and direct vs. synonym match categorization using phrase-based boundary matching.

Adheres strictly to Section 6 of the AIML Project Proposal:
- Skill dictionary + curated synonym mappings (e.g., ML -> Machine Learning)
- Word-boundary / phrase-based matching to prevent false positives
- Explicit distinction between direct matches, synonym matches, and undetected skills
- Disclaimer: "Skill not detected in resume"
"""

import os
import re
import json
from typing import Dict, List, Set, Any, Tuple


class SkillExtractor:
    def __init__(self, dictionary_path: str = None):
        """
        Initializes the skill dictionary and compiles regex matchers for synonyms.
        """
        if dictionary_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dictionary_path = os.path.join(base_dir, "data", "skills_dictionary.json")

        self.dictionary_path = dictionary_path
        self.canonical_skills: Set[str] = set()
        self.synonym_to_canonical: Dict[str, str] = {}
        self.compiled_patterns: List[Tuple[str, str, re.Pattern]] = []

        self._load_dictionary()

    def _load_dictionary(self):
        """
        Loads the JSON dictionary and compiles regex patterns sorted by pattern length descending
        so that longer phrases (e.g. 'SQL database queries') are prioritized over shorter tokens ('SQL').
        """
        if not os.path.exists(self.dictionary_path):
            raise FileNotFoundError(f"Skills dictionary not found at {self.dictionary_path}")

        with open(self.dictionary_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.canonical_skills = set(data.get("skills", []))
        self.synonym_to_canonical = {k.lower(): v for k, v in data.get("synonyms", {}).items()}

        # Also ensure canonical skills map to themselves
        for skill in self.canonical_skills:
            lower_skill = skill.lower()
            if lower_skill not in self.synonym_to_canonical:
                self.synonym_to_canonical[lower_skill] = skill

        # Sort patterns by phrase length descending to match multi-word phrases first
        sorted_synonyms = sorted(self.synonym_to_canonical.keys(), key=lambda s: len(s), reverse=True)

        self.compiled_patterns = []
        for syn in sorted_synonyms:
            canonical = self.synonym_to_canonical[syn]
            # Use safe boundary matching that accommodates punctuation, whitespace, and start/end of line
            escaped_syn = re.escape(syn)
            pattern = re.compile(rf'(?<![A-Za-z0-9_]){escaped_syn}(?![A-Za-z0-9_])', re.IGNORECASE)
            self.compiled_patterns.append((syn, canonical, pattern))

    def extract_skills(self, text: str) -> Dict[str, Any]:
        """
        Extracts skills from text, categorizing them into:
        - normalized_skills: set of canonical skills recognized
        - direct_matches: skills where the exact canonical name was mentioned
        - synonym_matches: skills matched via synonym/alias
        """
        if not text:
            return {
                "normalized_skills": [],
                "direct_matches": [],
                "synonym_matches": [],
                "raw_mentions": []
            }

        detected_canonical: Set[str] = set()
        direct_matches: Set[str] = set()
        synonym_matches: List[Dict[str, str]] = []
        raw_mentions: List[Dict[str, str]] = []

        # Track matched spans in text to avoid duplicate sub-matching
        matched_spans = []

        for syn, canonical, pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                start, end = match.span()
                # Check if this span was already covered by an earlier (longer) phrase match
                if any(existing_start <= start and end <= existing_end for existing_start, existing_end in matched_spans):
                    continue

                matched_spans.append((start, end))
                detected_canonical.add(canonical)
                matched_text = match.group()

                # Determine if it was an exact canonical match or an alias match
                is_direct = (matched_text.strip().lower() == canonical.lower())
                if is_direct:
                    direct_matches.add(canonical)
                else:
                    synonym_matches.append({
                        "raw": matched_text,
                        "normalized": canonical
                    })

                raw_mentions.append({
                    "raw": matched_text,
                    "normalized": canonical,
                    "span": [start, end]
                })

        return {
            "normalized_skills": sorted(list(detected_canonical)),
            "direct_matches": sorted(list(direct_matches)),
            "synonym_matches": synonym_matches,
            "raw_mentions": raw_mentions
        }

    def compare_skills(
        self,
        resume_skills_data: Dict[str, Any],
        required_skills: List[str]
    ) -> Dict[str, Any]:
        """
        Compares extracted resume skills against a list of required skills.
        
        Calculates:
        - Matched skills
        - Direct matches
        - Synonym matches
        - Skills not detected in resume (with proposal-mandated neutral wording)
        - Additional skills present in resume
        - Skill-Match Score: (matched / total_required) * 100
        """
        resume_normalized = set(resume_skills_data.get("normalized_skills", []))
        resume_direct = set(resume_skills_data.get("direct_matches", []))
        resume_synonym_list = resume_skills_data.get("synonym_matches", [])

        # Normalize required skills using dictionary canonical names
        req_canonical_list = []
        for req in required_skills:
            req_clean = req.strip()
            canonical = self.synonym_to_canonical.get(req_clean.lower(), req_clean)
            req_canonical_list.append(canonical)

        required_set = set(req_canonical_list)

        # 1. Matched recognized required skills
        matched = required_set.intersection(resume_normalized)

        # 2. Direct vs Synonym breakdown among matched skills
        direct_matched = sorted(list(matched.intersection(resume_direct)))
        
        # Synonym matched are matched skills that were not directly mentioned as canonical
        synonym_matched_skills = []
        for item in resume_synonym_list:
            if item["normalized"] in matched and item["normalized"] not in direct_matched:
                synonym_matched_skills.append(item)

        # 3. Skills not detected in resume
        undetected = sorted(list(required_set - resume_normalized))

        # 4. Additional skills detected in resume (not in required skills)
        additional = sorted(list(resume_normalized - required_set))

        # 5. Skill-Match Score calculation
        # Skill-Match Score = (Number of matched recognized required skills / Total recognized required skills) * 100
        if len(required_set) > 0:
            skill_match_score = (len(matched) / len(required_set)) * 100.0
        else:
            # Documented fallback rule when no required skills are specified:
            # Skill-match component defaults to 100.0 to avoid division by zero.
            skill_match_score = 100.0

        return {
            "total_required": len(required_set),
            "total_matched": len(matched),
            "matched_skills": sorted(list(matched)),
            "direct_matched_skills": direct_matched,
            "synonym_matched_skills": synonym_matched_skills,
            "skills_not_detected": undetected,
            "additional_resume_skills": additional,
            "skill_match_score": round(skill_match_score, 2),
            "undetected_wording": "Skill not detected in resume"
        }

