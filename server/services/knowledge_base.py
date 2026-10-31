import logging

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from config import Settings
from ingestion.chunker import split_documents, split_parent_documents
from ingestion.loaders import SUPPORTED_EXTENSIONS, load_file
from retrieval.parent_store import ParentDocumentStore
from retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        settings.document_directory.mkdir(parents=True, exist_ok=True)
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.vector_store = Chroma(
            collection_name="merchant_policy_rag",
            embedding_function=self.embeddings,
            persist_directory=str(settings.chroma_persist_directory),
            collection_metadata={"hnsw:space": "cosine"},
        )
        self.parent_store = ParentDocumentStore(
            settings.chroma_persist_directory / "parents.sqlite3"
        )
        self.retriever = VectorRetriever(
            self.vector_store,
            settings.retrieval_k,
            reranker_top_k=settings.reranker_top_k,
            reranker_model=settings.reranker_model,
            reranker_device=settings.reranker_device,
            rrf_constant=settings.rrf_constant,
            parent_store=self.parent_store,
        )

    @property
    def chunk_count(self) -> int:
        return self.vector_store._collection.count()

    def index_if_empty(self) -> int:
        if self.chunk_count:
            stored = self.vector_store.get(limit=1, include=["metadatas"])
            metadata = (stored.get("metadatas") or [{}])[0]
            required_fields = {
                "parent_id",
                "policy_type",
                "region",
                "document_version",
                "effective_date",
                "payment_method",
            }
            if required_fields.issubset(metadata) and self.parent_store.count:
                return self.chunk_count
            logger.info("Refreshing indexed documents to add hybrid-search metadata")
        return self.index_directory()

    def index_directory(self) -> int:
        parsed: list[Document] = []
        paths = sorted(
            path for path in self.settings.document_directory.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not paths:
            raise ValueError(
                f"No supported documents found in {self.settings.document_directory}. "
                "Add PDF, DOCX, or HTML files before indexing."
            )
        for path in paths:
            extracted = load_file(path, document_name=path.name)
            if not extracted:
                logger.warning("No readable text or tables found", extra={"document": path.name})
            parsed.extend(extracted)
        parents = split_parent_documents(parsed, self.settings.chunk_size * 4)
        chunks = split_documents(parents, self.settings.chunk_size, self.settings.chunk_overlap)
        chunks = [self._sanitize_metadata(document) for document in chunks]
        if not chunks:
            raise ValueError("No readable text or tables found in the supplied documents.")
        existing_ids = self.vector_store.get(include=[])["ids"]
        ids = [str(document.metadata["chunk_id"]) for document in chunks]
        self.vector_store.add_documents(chunks, ids=ids)
        obsolete_ids = [identifier for identifier in existing_ids if identifier not in set(ids)]
        if obsolete_ids:
            self.vector_store.delete(ids=obsolete_ids)
        self.parent_store.replace(parents)
        logger.info(
            "Policy documents indexed",
            extra={"documents": len(paths), "parents": len(parents), "chunks": len(chunks), "database": str(self.settings.chroma_persist_directory)},
        )
        return len(chunks)

    def document_list(self) -> list[dict]:
        grouped: dict[str, dict] = {}
        stored = self.vector_store.get(include=["metadatas"])
        for metadata in stored["metadatas"] or []:
            name = str(metadata.get("document_name", "Unknown"))
            entry = grouped.setdefault(name, {
                "name": name,
                "source": str(metadata.get("source", "")),
                "chunks": 0,
                "categories": set(),
            })
            entry["chunks"] += 1
            entry["categories"].add(str(metadata.get("policy_category", "general")))
        return [
            {**entry, "categories": sorted(entry["categories"])}
            for entry in sorted(grouped.values(), key=lambda item: item["name"].lower())
        ]

    def document_chunks(self, name: str, offset: int = 0, limit: int = 20) -> dict:
        stored = self.vector_store.get(
            where={"document_name": name},
            include=["documents", "metadatas"],
        )
        records = sorted(
            zip(stored["documents"] or [], stored["metadatas"] or []),
            key=lambda item: (item[1].get("page") or 0, item[1].get("start_index") or 0),
        )
        chunks = [
            {
                "page": metadata.get("page"),
                "content_type": metadata.get("content_type", "text"),
                "content": content,
            }
            for content, metadata in records[offset:offset + limit]
        ]
        return {"document": name, "offset": offset, "total_chunks": len(records), "chunks": chunks}

    @staticmethod
    def _sanitize_metadata(document: Document) -> Document:
        document.metadata = {key: value for key, value in document.metadata.items() if value is not None}
        return document
