"""Evaluation metrics for RAG quality assessment."""

from __future__ import annotations

from quantumrag.core.utils.text import split_sentences, tokenize_filtered


class RetrievalRecall:
    """Recall@K metric - does retrieved set contain the answer chunk?"""

    def compute(self, retrieved_ids: list[str], relevant_ids: list[str], k: int = 5) -> float:
        """Compute recall@k: fraction of relevant items found in top-k retrieved."""
        if not relevant_ids:
            return 1.0  # No relevant items expected, trivially satisfied

        top_k = set(retrieved_ids[:k])
        relevant = set(relevant_ids)
        found = top_k & relevant
        return len(found) / len(relevant)


class Faithfulness:
    """Check if answer claims are supported by context."""

    def compute(self, answer: str, context: str) -> float:
        """Sentence-level overlap scoring (embedding-free for MVP).

        Checks what fraction of answer sentences have token overlap with the context.
        """
        answer_sentences = split_sentences(answer)
        if not answer_sentences:
            return 1.0

        context_tokens = tokenize_filtered(context)
        if not context_tokens:
            return 0.0

        supported = 0
        for sent in answer_sentences:
            sent_tokens = tokenize_filtered(sent)
            if not sent_tokens:
                supported += 1  # Empty sentences are trivially supported
                continue
            overlap = len(sent_tokens & context_tokens) / len(sent_tokens)
            if overlap >= 0.3:
                supported += 1

        return supported / len(answer_sentences)


class AnswerRelevancy:
    """Check if answer is relevant to the question."""

    def compute(self, question: str, answer: str) -> float:
        """Keyword overlap + structure scoring.

        Combines token overlap between question and answer with a bonus for
        answers that appear to directly address the question.
        """
        q_tokens = tokenize_filtered(question)
        a_tokens = tokenize_filtered(answer)

        if not q_tokens or not a_tokens:
            return 0.0

        # Token overlap score
        overlap = len(q_tokens & a_tokens) / len(q_tokens)

        # Structure bonus: answers that are reasonably long and not just echoing the question
        length_ratio = min(len(a_tokens) / max(len(q_tokens), 1), 3.0) / 3.0
        structure_bonus = 0.2 if length_ratio > 0.3 else 0.0

        # Penalize very short answers
        if len(a_tokens) < 3:
            structure_bonus = 0.0

        score = min(overlap + structure_bonus, 1.0)
        return round(score, 4)


class Completeness:
    """Measures if the answer covers all aspects of the question.

    For enumeration queries (containing keywords like "모두", "all", "list", etc.),
    counts how many of the context's distinct items appear in the answer.
    For non-enumeration queries, falls back to sentence-level coverage.
    """

    _ENUM_KEYWORDS: frozenset[str] = frozenset({"모두", "모든", "전부", "나열", "list", "all"})

    def compute(self, question: str, answer: str, context: str) -> float:
        """Compute completeness score.

        For enumeration queries, measures item coverage from the context.
        For other queries, measures sentence-level coverage.
        """
        if not answer or not context:
            return 0.0

        if self._is_enumeration_query(question):
            return self._enumeration_completeness(answer, context)
        return self._sentence_completeness(answer, context)

    def _is_enumeration_query(self, question: str) -> bool:
        """Check if the question is asking for an enumeration/listing."""
        q_lower = question.lower()
        return any(kw in q_lower for kw in self._ENUM_KEYWORDS)

    def _enumeration_completeness(self, answer: str, context: str) -> float:
        """Count how many distinct context items appear in the answer."""
        context_sentences = split_sentences(context)
        if not context_sentences:
            return 1.0

        # Extract distinct items from context sentences
        context_items: list[set[str]] = []
        for sent in context_sentences:
            tokens = tokenize_filtered(sent)
            if tokens:
                context_items.append(tokens)

        if not context_items:
            return 1.0

        answer_tokens = tokenize_filtered(answer)
        covered = 0
        for item_tokens in context_items:
            overlap = len(item_tokens & answer_tokens) / len(item_tokens)
            if overlap >= 0.3:
                covered += 1

        return round(covered / len(context_items), 4)

    def _sentence_completeness(self, answer: str, context: str) -> float:
        """Fallback: fraction of context sentences reflected in the answer."""
        context_sentences = split_sentences(context)
        if not context_sentences:
            return 1.0

        answer_tokens = tokenize_filtered(answer)
        if not answer_tokens:
            return 0.0

        covered = 0
        for sent in context_sentences:
            sent_tokens = tokenize_filtered(sent)
            if not sent_tokens:
                covered += 1
                continue
            overlap = len(sent_tokens & answer_tokens) / len(sent_tokens)
            if overlap >= 0.3:
                covered += 1

        return round(covered / len(context_sentences), 4)


class ContextPrecision:
    """What fraction of the retrieved context was actually used in the answer.

    High precision means no wasted retrieval — every retrieved chunk contributed
    to the final answer.
    """

    def compute(self, answer: str, contexts: list[str]) -> float:
        """Compute context precision: fraction of contexts used in the answer.

        Args:
            answer: The generated answer text.
            contexts: List of retrieved context strings (one per chunk).

        Returns:
            Fraction of contexts that have meaningful overlap with the answer.
        """
        if not contexts:
            return 1.0  # No contexts retrieved, trivially precise

        if not answer:
            return 0.0

        answer_tokens = tokenize_filtered(answer)
        if not answer_tokens:
            return 0.0

        used = 0
        for ctx in contexts:
            ctx_tokens = tokenize_filtered(ctx)
            if not ctx_tokens:
                continue
            overlap = len(ctx_tokens & answer_tokens) / len(ctx_tokens)
            if overlap >= 0.2:
                used += 1

        return round(used / len(contexts), 4)


class LatencyMetric:
    """Track latency percentiles."""

    def compute(self, latencies: list[float]) -> dict[str, float]:
        """Compute p50, p95, p99 from a list of latency values."""
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_latencies = sorted(latencies)
        return {
            "p50": round(_percentile(sorted_latencies, 50), 4),
            "p95": round(_percentile(sorted_latencies, 95), 4),
            "p99": round(_percentile(sorted_latencies, 99), 4),
        }


def _percentile(sorted_data: list[float], p: float) -> float:
    """Compute the p-th percentile from sorted data."""
    if len(sorted_data) == 1:
        return sorted_data[0]
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


def compute_token_f1(prediction: str, reference: str) -> float:
    """Compute token-level F1 score between prediction and reference."""
    pred_tokens = tokenize_filtered(prediction)
    ref_tokens = tokenize_filtered(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = pred_tokens & ref_tokens
    if not common:
        return 0.0
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    return round(2 * precision * recall / (precision + recall), 4)
