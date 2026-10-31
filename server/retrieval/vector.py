import re
from threading import Lock
from typing import Mapping

from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from retrieval.parent_store import ParentDocumentStore


def cosine_distance_to_similarity(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance))


def infer_metadata_filters(query: str) -> dict[str, str]:
    filters: dict[str, str] = {}
    region_patterns = {
        "India": r"\bIndia\b",
        "United States": r"\b(?:United States|USA|U\.S\.)\b",
        "United Kingdom": r"\b(?:United Kingdom|UK|U\.K\.)\b",
        "European Union": r"\b(?:European Union|EU)\b",
        "Canada": r"\bCanada\b",
        "Australia": r"\bAustralia\b",
    }
    regions = [
        region for region, pattern in region_patterns.items()
        if re.search(pattern, query, re.IGNORECASE)
    ]
    if len(regions) == 1:
        filters["region"] = regions[0]

    sample = query.casefold()
    policy_terms = (
        ("prohibited_businesses", ("prohibited business", "restricted business")),
        ("disputes", ("dispute", "chargeback")),
        ("onboarding", ("onboard", "merchant terms")),
        ("refunds", ("refund", "return policy")),
        ("fees", ("fee", "pricing")),
        ("offboarding", ("offboard", "termination")),
    )
    matching_types = [
        policy_type for policy_type, terms in policy_terms
        if any(term in sample for term in terms)
    ]
    if len(matching_types) == 1:
        filters["policy_type"] = matching_types[0]

    if re.search(r"\b(?:card|cards|credit card|debit card|card payment)\b", query, re.I):
        filters["payment_method"] = "card"
    elif re.search(r"\bUPI\b", query, re.I):
        filters["payment_method"] = "UPI"
    elif re.search(r"\b(?:bank transfer|ACH|wire transfer)\b", query, re.I):
        filters["payment_method"] = "bank_transfer"

    version = re.search(r"\bversion\s*[:#]?\s*([0-9]+(?:\.[0-9]+)*)\b", query, re.I)
    if version:
        filters["document_version"] = version.group(1)
    effective_date = re.search(
        r"\beffective\s+(?:date|from|on|as of)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})\b",
        query,
        re.I,
    )
    if effective_date:
        filters["effective_date"] = effective_date.group(1)
    return filters


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[.+/-][\w]+)*", text.casefold())


def _where_filter(filters: Mapping[str, str]) -> dict | None:
    fallbacks = {
        "region": ("global", "unspecified"),
        "policy_type": ("general", "unspecified"),
        "payment_method": ("unspecified",),
        "document_version": ("unspecified",),
        "effective_date": ("unspecified",),
    }
    conditions = []
    for field, value in filters.items():
        choices = (value, *fallbacks.get(field, ("unspecified",)))
        conditions.append(
            {"$or": [{field: choice} for choice in dict.fromkeys(choices)]}
        )
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _matches_filters(metadata: Mapping[str, object], filters: Mapping[str, str]) -> bool:
    fallbacks = {
        "region": {"global", "unspecified"},
        "policy_type": {"general", "unspecified"},
        "payment_method": {"unspecified"},
        "document_version": {"unspecified"},
        "effective_date": {"unspecified"},
    }
    return all(
        str(metadata.get(field, "unspecified")) in {value, *fallbacks.get(field, {"unspecified"})}
        for field, value in filters.items()
    )


class VectorRetriever:
    def __init__(
        self,
        vector_store: Chroma,
        candidate_k: int,
        reranker_top_k: int = 5,
        reranker_model: str = "BAAI/bge-reranker-base",
        reranker_device: str = "auto",
        rrf_constant: int = 60,
        parent_store: ParentDocumentStore | None = None,
    ) -> None:
        if candidate_k < 1 or reranker_top_k < 1 or rrf_constant < 1:
            raise ValueError("Retrieval candidate, result, and RRF limits must be positive.")
        self.vector_store = vector_store
        self.candidate_k = candidate_k
        self.reranker_top_k = reranker_top_k
        self.reranker_model = reranker_model
        self.reranker_device = reranker_device
        self.rrf_constant = rrf_constant
        self.parent_store = parent_store
        self._corpus: list[tuple[str, Document]] | None = None
        self._corpus_tokens: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._reranker = None
        self._bm25_lock = Lock()
        self._reranker_lock = Lock()

    def search(
        self, query: str, filters: Mapping[str, str] | None = None
    ) -> list[tuple[Document, float]]:
        filters = filters or {}
        if self.vector_store._collection.count() == 0:
            return []

        where = _where_filter(filters)
        vector_results = self.vector_store.similarity_search_with_score(
            query,
            k=self.candidate_k,
            filter=where,
        )
        candidates: dict[str, tuple[Document, float]] = {}
        fused_scores: dict[str, float] = {}
        for rank, (document, distance) in enumerate(vector_results, start=1):
            key = self._key(document)
            candidates[key] = (document, cosine_distance_to_similarity(distance))
            fused_scores[key] = fused_scores.get(key, 0.0) + 1 / (
                self.rrf_constant + rank
            )

        bm25_scores = self._bm25_scores(query, filters)
        for rank, (key, document, _) in enumerate(bm25_scores, start=1):
            candidates[key] = (document, 0.0)
            fused_scores[key] = fused_scores.get(key, 0.0) + 1 / (
                self.rrf_constant + rank
            )

        fused = sorted(
            fused_scores,
            key=lambda key: fused_scores[key],
            reverse=True,
        )[:self.candidate_k]
        if not fused:
            return []

        pairs = [(query, candidates[key][0].page_content) for key in fused]
        reranker = self._get_reranker()
        with self._reranker_lock:
            scores = reranker.predict(pairs, show_progress_bar=False)
        ranked: dict[str, tuple[Document, float]] = {}
        for key, score in zip(fused, scores):
            document = candidates[key][0]
            parent_id = document.metadata.get("parent_id")
            result_id = str(parent_id or key)
            score_value = float(score)
            if result_id not in ranked or score_value > ranked[result_id][1]:
                ranked[result_id] = (document, score_value)

        if self.parent_store:
            parent_ids = [
                str(document.metadata["parent_id"])
                for document, _ in ranked.values()
                if document.metadata.get("parent_id")
            ]
            parents = self.parent_store.get_many(list(dict.fromkeys(parent_ids)))
            for result_id, (document, score) in list(ranked.items()):
                parent = parents.get(result_id)
                if parent:
                    ranked[result_id] = (parent, score)

        return sorted(
            ranked.values(),
            key=lambda item: item[1],
            reverse=True,
        )[:self.reranker_top_k]

    def _bm25_scores(
        self, query: str, filters: Mapping[str, str]
    ) -> list[tuple[str, Document, float]]:
        self._load_bm25()
        if not self._corpus or not self._bm25:
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        matching = [
            (self._corpus[index][0], self._corpus[index][1], float(score))
            for index, score in enumerate(scores)
            if any(token in self._corpus_tokens[index] for token in query_tokens)
            and _matches_filters(self._corpus[index][1].metadata, filters)
        ]
        return sorted(matching, key=lambda item: item[2], reverse=True)[
            :self.candidate_k
        ]

    def _load_bm25(self) -> None:
        with self._bm25_lock:
            if self._corpus is not None:
                return
            stored = self.vector_store.get(include=["documents", "metadatas"])
            self._corpus = []
            tokenized = []
            for identifier, content, metadata in zip(
                stored["ids"],
                stored["documents"] or [],
                stored["metadatas"] or [],
            ):
                document = Document(page_content=content, metadata=metadata or {})
                tokens = _tokenize(content)
                if tokens:
                    self._corpus.append((identifier, document))
                    self._corpus_tokens.append(tokens)
                    tokenized.append(tokens)
            self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def _get_reranker(self):
        with self._reranker_lock:
            if self._reranker is None:
                from sentence_transformers import CrossEncoder

                device = self.reranker_device
                if device == "auto":
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                self._reranker = CrossEncoder(self.reranker_model, device=device)
        return self._reranker

    @staticmethod
    def _key(document: Document) -> str:
        return str(
            document.metadata.get("chunk_id")
            or document.metadata.get("parent_id")
            or f"{document.metadata.get('source', '')}:"
            f"{document.metadata.get('page', '')}:"
            f"{document.metadata.get('start_index', '')}:"
            f"{document.page_content}"
        )
