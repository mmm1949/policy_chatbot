from pathlib import Path

from langchain_core.documents import Document

from ingestion.chunker import split_documents, split_parent_documents
from retrieval.parent_store import ParentDocumentStore
from retrieval.vector import (
    VectorRetriever,
    _matches_filters,
    _where_filter,
    infer_metadata_filters,
)


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


def test_query_infers_region_policy_and_payment_filters() -> None:
    filters = infer_metadata_filters(
        "What is the chargeback reason code for card payments in India?"
    )

    assert filters == {
        "region": "India",
        "policy_type": "disputes",
        "payment_method": "card",
    }
    where = _where_filter(filters)
    assert where is not None
    assert _matches_filters(
        {"region": "unspecified", "policy_type": "general", "payment_method": "unspecified"},
        filters,
    )
    assert not _matches_filters(
        {"region": "United States", "policy_type": "disputes", "payment_method": "card"},
        filters,
    )


def test_hybrid_search_fuses_ranks_and_returns_parent_documents() -> None:
    chunks = [
        _chunk("chunk-1", "parent-1", "chargeback reason code 4837 card", "India", "disputes", "card"),
        _chunk("chunk-2", "parent-2", "irrelevant settlement information", "India", "disputes", "card"),
        _chunk("chunk-3", "parent-3", "chargeback details code 4837", "unspecified", "general", "unspecified"),
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
        infer_metadata_filters("chargeback reason code 4837 card payments in India"),
    )

    assert vector_store.where is not None
    assert results == [
        (parent_store.documents["parent-1"], 0.9),
        (parent_store.documents["parent-3"], 0.8),
    ]


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
