from pathlib import Path

from langchain_core.documents import Document
from pydantic import ValidationError
import pytest

from config import Settings
from ingestion.chunker import split_documents, split_parent_documents
from retrieval.parent_store import ParentDocumentStore
from retrieval.vector import (
    VectorRetriever,
    _metadata_match_ratio,
    infer_metadata_hints,
)
from services.knowledge_base import KnowledgeBase


class FakeCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakeVectorStore:
    def __init__(
        self,
        corpus: list[tuple[str, Document]],
        vector_results: list[tuple[Document, float]],
    ) -> None:
        self.corpus = corpus
        self.vector_results = vector_results
        self._collection = FakeCollection(len(corpus))
        self.where = None

    def similarity_search_with_score(
        self, query: str, k: int, filter: dict | None = None
    ) -> list[tuple[Document, float]]:
        self.where = filter
        return self.vector_results[:k]

    def get(self, include: list[str]) -> dict:
        return {
            "ids": [identifier for identifier, _ in self.corpus],
            "documents": [document.page_content for _, document in self.corpus],
            "metadatas": [document.metadata for _, document in self.corpus],
        }


class FakeReranker:
    def predict(
        self, pairs: list[tuple[str, str]], show_progress_bar: bool = False
    ) -> list[float]:
        scores = []
        for _, content in pairs:
            if "4837" in content:
                scores.append(0.9)
            elif "chargeback" in content:
                scores.append(0.8)
            else:
                scores.append(0.1)
        return scores


class ConstantReranker:
    def predict(
        self, pairs: list[tuple[str, str]], show_progress_bar: bool = False
    ) -> list[float]:
        return [0.5] * len(pairs)


class FakeParentStore:
    def __init__(self, documents: dict[str, Document]) -> None:
        self.documents = documents

    def get_many(self, parent_ids: list[str]) -> dict[str, Document]:
        return {
            parent_id: self.documents[parent_id]
            for parent_id in parent_ids
            if parent_id in self.documents
        }


def _chunk(
    identifier: str,
    parent_id: str,
    content: str,
    region: str,
    policy_type: str,
    payment_method: str,
) -> Document:
    return Document(
        page_content=content,
        metadata={
            "chunk_id": identifier,
            "parent_id": parent_id,
            "region": region,
            "policy_type": policy_type,
            "payment_method": payment_method,
            "document_version": "unspecified",
            "effective_date": "unspecified",
        },
    )


def test_query_infers_region_policy_and_payment_hints() -> None:
    hints = infer_metadata_hints(
        "What is the chargeback reason code for card payments in India?"
    )

    assert hints == {
        "region": "India",
        "policy_type": "disputes",
        "payment_method": "card",
    }
    assert _metadata_match_ratio(
        {"region": "India", "policy_type": "disputes", "payment_method": "card"},
        hints,
    ) == 1
    assert _metadata_match_ratio(
        {"region": "unspecified", "policy_type": "fees"},
        hints,
    ) == 0


def test_metadata_hints_do_not_filter_out_missing_metadata() -> None:
    document = Document(
        page_content="Refunds are processed to the original payment method.",
        metadata={"chunk_id": "old-chunk"},
    )
    vector_store = FakeVectorStore(
        [("old-chunk", document)],
        [(document, 0.1)],
    )
    retriever = VectorRetriever(vector_store, candidate_k=3)
    retriever._reranker = FakeReranker()

    results = retriever.search(
        "What is the refund policy for card payments?",
        {"policy_type": "refunds", "payment_method": "card"},
    )

    assert vector_store.where is None
    assert results == [(document, 0.1)]


def test_misclassified_document_remains_searchable() -> None:
    document = Document(
        page_content="Onboarding requirements mention chargebacks as a risk control.",
        metadata={"chunk_id": "onboarding", "policy_type": "disputes"},
    )
    vector_store = FakeVectorStore(
        [("onboarding", document)],
        [(document, 0.1)],
    )
    retriever = VectorRetriever(vector_store, candidate_k=3)
    retriever._reranker = FakeReranker()

    results = retriever.search(
        "What are the onboarding requirements?",
        {"policy_type": "onboarding"},
    )

    assert results == [(document, 0.8)]


def test_metadata_match_boosts_final_rank_without_excluding_mismatches() -> None:
    mismatched = Document(
        page_content="common onboarding requirements",
        metadata={"chunk_id": "mismatch", "policy_type": "disputes"},
    )
    matched = Document(
        page_content="common onboarding requirements",
        metadata={"chunk_id": "match", "policy_type": "onboarding"},
    )
    vector_store = FakeVectorStore(
        [("mismatch", mismatched), ("match", matched)],
        [(mismatched, 0.1), (matched, 0.1)],
    )
    retriever = VectorRetriever(vector_store, candidate_k=3)
    retriever._reranker = ConstantReranker()

    results = retriever.search(
        "common onboarding",
        {"policy_type": "onboarding"},
    )

    assert [document for document, _ in results] == [matched, mismatched]
    assert vector_store.where is None


def test_hybrid_search_fuses_ranks_and_returns_parent_documents() -> None:
    chunks = [
        _chunk("chunk-1", "parent-1", "chargeback reason code 4837 card", "India", "disputes", "card"),
        _chunk("chunk-2", "parent-2", "irrelevant settlement information", "India", "disputes", "card"),
        _chunk("chunk-3", "parent-3", "chargeback details", "unspecified", "general", "unspecified"),
    ]
    corpus = list(zip(("chunk-1", "chunk-2", "chunk-3"), chunks))
    vector_store = FakeVectorStore(corpus, [(chunks[1], 0.1), (chunks[0], 0.2)])
    parent_store = FakeParentStore({
        "parent-1": Document(
            page_content="Full dispute section including the reason-code table.",
            metadata={"parent_id": "parent-1", "document_name": "disputes.pdf", "page": 2},
        ),
        "parent-2": Document(
            page_content="Full settlement section.",
            metadata={"parent_id": "parent-2", "document_name": "settlement.pdf", "page": 1},
        ),
        "parent-3": Document(
            page_content="Full chargeback table.",
            metadata={"parent_id": "parent-3", "document_name": "chargebacks.pdf", "page": 3},
        ),
    })
    retriever = VectorRetriever(
        vector_store, candidate_k=3, reranker_top_k=2, parent_store=parent_store
    )
    retriever._reranker = FakeReranker()

    results = retriever.search(
        "chargeback reason code 4837 card payments in India",
        infer_metadata_hints("chargeback reason code 4837 card payments in India"),
    )

    assert vector_store.where is None
    assert results == [
        (parent_store.documents["parent-1"], 0.9),
        (parent_store.documents["parent-3"], 0.8),
    ]


def test_relevance_threshold_filters_reranker_results() -> None:
    document = _chunk(
        "chunk-1",
        "parent-1",
        "chargeback reason code 4837",
        "India",
        "disputes",
        "card",
    )
    vector_store = FakeVectorStore(
        [("chunk-1", document)],
        [(document, 0.1)],
    )
    retriever = VectorRetriever(
        vector_store,
        candidate_k=3,
        relevance_threshold=0.95,
    )
    retriever._reranker = FakeReranker()

    assert retriever.search("chargeback reason code 4837") == []


def test_relevance_threshold_is_optional_and_must_be_finite() -> None:
    assert Settings(_env_file=None, relevance_threshold=0.72).relevance_threshold == 0.72
    assert Settings(_env_file=None).relevance_threshold is None

    with pytest.raises(ValidationError):
        Settings(_env_file=None, relevance_threshold=float("nan"))


def test_nonempty_index_with_missing_metadata_is_rebuilt() -> None:
    old_document = Document(
        page_content="legacy chunk",
        metadata={"chunk_id": "legacy"},
    )
    knowledge_base = object.__new__(KnowledgeBase)
    knowledge_base.vector_store = FakeVectorStore(
        [("legacy", old_document)],
        [],
    )
    knowledge_base.parent_store = FakeParentStore({})
    reindexed: list[bool] = []
    knowledge_base.index_directory = lambda: reindexed.append(True) or 54

    assert knowledge_base.ensure_index_current() == 54
    assert reindexed == [True]


def test_current_index_is_reused_without_reindexing() -> None:
    document = _chunk(
        "chunk-1",
        "parent-1",
        "Current indexed chunk",
        "unspecified",
        "general",
        "unspecified",
    )
    knowledge_base = object.__new__(KnowledgeBase)
    knowledge_base.vector_store = FakeVectorStore(
        [("chunk-1", document)],
        [],
    )
    knowledge_base.parent_store = FakeParentStore({
        "parent-1": Document(
            page_content="Current parent",
            metadata={"parent_id": "parent-1"},
        ),
    })
    knowledge_base.index_directory = lambda: (_ for _ in ()).throw(
        AssertionError("A current index should not be rebuilt.")
    )

    assert knowledge_base.ensure_index_current() == 1


def test_parent_splitting_keeps_table_intact_and_links_child_chunks() -> None:
    table_content = "Extracted policy table:\n" + ("fee | amount\n" * 250)
    documents = [
        Document(
            page_content=("Section heading\n\n" + "Policy details. " * 500),
            metadata={"source": "fees.pdf", "page": 1, "content_type": "text"},
        ),
        Document(
            page_content=table_content,
            metadata={"source": "fees.pdf", "page": 1, "content_type": "table"},
        ),
    ]

    parents = split_parent_documents(documents, parent_size=400)
    children = split_documents(parents, chunk_size=100, chunk_overlap=10)

    assert table_content in [parent.page_content for parent in parents]
    assert len({parent.metadata["parent_id"] for parent in parents}) == len(parents)
    assert all(child.metadata["parent_id"] for child in children)
    assert len(children) > len(parents)


def test_parent_store_persists_sections(tmp_path: Path) -> None:
    store = ParentDocumentStore(tmp_path / "parents.sqlite3")
    document = Document(
        page_content="Complete section",
        metadata={"parent_id": "parent-1", "document_name": "policy.pdf"},
    )

    store.replace([document])

    assert store.get_many(["parent-1"]) == {"parent-1": document}
