"""
Module: semantic_matcher.py
Implements semantic similarity matching using the Sentence-BERT pretrained model
'all-MiniLM-L6-v2' and scikit-learn's cosine_similarity.

Adheres to Section 6 of the AIML Project Proposal:
- Lightweight pretrained model: all-MiniLM-L6-v2
- Loaded once in memory and reused
- Scikit-learn cosine similarity calculation
- Scores normalized to [0, 100] percentage scale
"""

import threading
import numpy as np
from typing import List, Union, Tuple
from sklearn.metrics.pairwise import cosine_similarity


class SemanticMatcher:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2"):
        """
        Thread-safe Singleton implementation to ensure model weights are loaded once into RAM.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SemanticMatcher, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if self._initialized:
            return

        self.model_name = model_name
        self._model = None
        self._load_model()
        self._initialized = True

    def _load_model(self):
        """
        Loads the SentenceTransformer model weights.
        """
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.model_name)

    def encode(self, text_or_texts: Union[str, List[str]]) -> np.ndarray:
        """
        Encodes a single text string or list of text strings into normalized Sentence-BERT dense embeddings.
        """
        if isinstance(text_or_texts, str):
            text_or_texts = [text_or_texts]
        
        # Replace empty strings with a single space to avoid encoding errors
        sanitized = [t.strip() if t and t.strip() else " " for t in text_or_texts]
        embeddings = self._model.encode(sanitized, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings

    def calculate_cosine_similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        """
        Calculates cosine similarity between two embedding vectors using scikit-learn.
        Returns a float in range [-1.0, 1.0].
        """
        if emb_a.ndim == 1:
            emb_a = emb_a.reshape(1, -1)
        if emb_b.ndim == 1:
            emb_b = emb_b.reshape(1, -1)

        sim_matrix = cosine_similarity(emb_a, emb_b)
        sim_val = float(sim_matrix[0][0])
        return sim_val

    def get_semantic_similarity_score(self, text_a: str, text_b: str) -> Tuple[float, float]:
        """
        Computes cosine similarity between two texts and scales it to [0, 100].
        
        Returns:
            Tuple of (raw_cosine_similarity [-1.0, 1.0], scaled_score [0.0, 100.0])
        """
        if not text_a.strip() or not text_b.strip():
            return 0.0, 0.0

        embeddings = self.encode([text_a, text_b])
        raw_sim = self.calculate_cosine_similarity(embeddings[0], embeddings[1])
        
        # Scale to [0.0, 100.0]. Negative similarities are clipped to 0.0
        scaled_score = max(0.0, raw_sim * 100.0)
        return round(raw_sim, 4), round(scaled_score, 2)

