"""
Answer generator service using Ollama LLM.
Generates grounded answers from retrieved passages with source citations.
"""

from typing import Dict, List, Any, Optional
import requests
import json
from datetime import datetime, timezone

from backend.app.config import Config


class AnswerGenerator:
    """Generates answers grounded in retrieved documents using Ollama."""

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ):
        """
        Initialize answer generator.

        Args:
            base_url: Ollama API base URL (default: from config)
            model: LLM model name (default: qwen3:4b-instruct from config)
            max_tokens: Maximum tokens for answer generation (default: 500)
            temperature: Temperature for LLM sampling (default: 0.3 for determinism)
        """
        self.base_url = base_url or Config.OLLAMA_BASE_URL
        self.model = model or "qwen3:4b-instruct"
        self.generate_url = f"{self.base_url}/api/generate"
        self.max_tokens = max_tokens
        self.temperature = temperature

    def generate(
        self,
        query: str,
        retriever_results: Dict[str, Any],
        max_sources: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate answer from retrieved passages.

        Args:
            query: User question
            retriever_results: Output from HybridRetriever.retrieve()
                Can have either nested structure:
                {
                    "ids": [...],
                    "documents": [...],
                    "metadatas": [...],
                    "scores": {"bm25": [...], "semantic": [...], "rrf": [...]}
                }
                OR flat structure (actual output from HybridRetriever):
                {
                    "ids": [...],
                    "documents": [...],
                    "metadatas": [...],
                    "distances": [...],
                    "bm25_scores": [...],
                    "rrf_scores": [...]
                }
            max_sources: Maximum number of source passages to include (default: 5)

        Returns:
            {
                "answer": "Generated answer text",
                "sources": [
                    {
                        "page": 1,
                        "file": "document.pdf",
                        "excerpt": "Relevant passage from document",
                        "score": 0.85
                    },
                    ...
                ],
                "confidence": 0.85,
                "tokens_used": 150,
                "model": "qwen3:4b-instruct",
                "timestamp": "2026-10-13T09:06:33Z"
            }

        Raises:
            ValueError: If retriever_results is empty or malformed
            requests.RequestException: If Ollama API call fails
        """
        # Validate retriever results
        if not retriever_results or not retriever_results.get("documents"):
            return self._insufficient_context_response(query)

        # Limit to max_sources
        num_sources = min(len(retriever_results["documents"]), max_sources)
        documents = retriever_results["documents"][:num_sources]
        metadatas = retriever_results["metadatas"][:num_sources]

        # Handle both nested and flat score structures
        rrf_scores = self._extract_rrf_scores(retriever_results, num_sources)

        # Build context from passages
        context = self._format_context(documents, metadatas)

        # Generate answer
        prompt = self._build_prompt(query, context)
        answer_text, tokens_used = self._call_ollama(prompt)

        # Extract sources from passages
        sources = self._extract_sources(
            documents, metadatas, rrf_scores, answer_text
        )

        # Calculate confidence from RRF scores
        confidence = self._calculate_confidence(rrf_scores)

        return {
            "answer": answer_text,
            "sources": sources,
            "confidence": confidence,
            "tokens_used": tokens_used,
            "model": self.model,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _extract_rrf_scores(
        self, retriever_results: Dict[str, Any], num_sources: int
    ) -> List[float]:
        """
        Extract RRF scores from retriever results.
        Handles both nested ('scores': {'rrf': [...]}) and flat ('rrf_scores': [...]) formats.
        """
        # Try nested format first
        scores_dict = retriever_results.get("scores", {})
        if isinstance(scores_dict, dict) and "rrf" in scores_dict:
            return scores_dict["rrf"][:num_sources]

        # Fall back to flat format
        if "rrf_scores" in retriever_results:
            return retriever_results["rrf_scores"][:num_sources]

        # No RRF scores found, return empty
        return []

    def _insufficient_context_response(self, query: str) -> Dict[str, Any]:
        """Return structured response when no passages retrieved."""
        return {
            "answer": (
                "I don't have enough context to answer this question. "
                "Please upload relevant documents or rephrase your question."
            ),
            "sources": [],
            "confidence": 0.0,
            "tokens_used": 0,
            "model": self.model,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _format_context(
        self, documents: List[str], metadatas: List[Dict[str, Any]]
    ) -> str:
        """
        Format retrieved passages as context for LLM.

        Args:
            documents: List of passage texts
            metadatas: List of metadata dictionaries

        Returns:
            Formatted context string with source attribution
        """
        context_parts = []
        for i, (doc, metadata) in enumerate(zip(documents, metadatas), 1):
            page = metadata.get("page", "?")
            file_name = metadata.get("file_name", "unknown")
            context_parts.append(f"Source {i} (Page {page}, {file_name}):\n{doc}")

        return "\n\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        """
        Build prompt for LLM.

        Uses system role to enforce grounding in passages.

        Args:
            query: User question
            context: Formatted passage context

        Returns:
            Complete prompt string
        """
        system_prompt = (
            "You are a helpful AI assistant that answers questions based on provided documents. "
            "Answer only using information from the provided sources. "
            "If the answer is not in the sources, say you don't have enough information. "
            "Be concise and accurate. Do not make up or infer information not explicitly stated."
        )

        user_message = f"""Based on the following documents:

{context}

Please answer this question: {query}

Provide a clear, concise answer based only on the provided sources."""

        # Format for Ollama
        prompt = f"{system_prompt}\n\nUser: {user_message}\n\nAssistant:"

        return prompt

    def _call_ollama(self, prompt: str) -> tuple[str, int]:
        """
        Call Ollama API to generate answer.

        Args:
            prompt: Complete prompt string

        Returns:
            (generated_answer, tokens_used)

        Raises:
            requests.RequestException: If API call fails
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": self.temperature,
        }

        try:
            response = requests.post(self.generate_url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()

            answer = result.get("response", "").strip()
            tokens = result.get("eval_count", 0) + result.get("prompt_eval_count", 0)

            return answer, tokens

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API error: {str(e)}") from e

    def _extract_sources(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        scores: List[float],
        answer_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract source citations from retrieved passages.

        Args:
            documents: List of passage texts
            metadatas: List of metadata dictionaries
            scores: List of RRF scores
            answer_text: Generated answer (for relevance checking)

        Returns:
            List of source dictionaries with page, file, excerpt, score
        """
        sources = []
        for doc, metadata, score in zip(documents, metadatas, scores):
            # Limit excerpt to first 150 characters
            excerpt = doc[:150] + "..." if len(doc) > 150 else doc

            source = {
                "page": metadata.get("page", 1),
                "file": metadata.get("file_name", "unknown"),
                "excerpt": excerpt,
                "score": float(score) if score else 0.0,
            }
            sources.append(source)

        return sources

    def _calculate_confidence(self, scores: List[float]) -> float:
        """
        Calculate confidence score from retriever RRF scores.

        Confidence is the average of the RRF scores from top passages.
        Higher RRF scores = more confident in the answer.

        Args:
            scores: List of RRF scores from retriever

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not scores:
            return 0.0

        # RRF scores are typically 0.0-0.1, scale them to 0.0-1.0
        avg_score = sum(scores) / len(scores)
        confidence = min(avg_score * 20, 1.0)  # Scale by 20x and cap at 1.0

        return float(confidence)
