from langchain_core.documents import Document
from langchain_chroma import Chroma


def cosine_distance_to_similarity(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance))


class VectorRetriever:
    def __init__(self, vector_store: Chroma, k: int) -> None:
        self.vector_store = vector_store
        self.k = k

    def search(self, query: str) -> list[tuple[Document, float]]:
        if self.vector_store._collection.count() == 0:
            return []
        results = self.vector_store.similarity_search_with_score(query, k=self.k)
        return [
            (document, cosine_distance_to_similarity(distance))
            for document, distance in results
        ]
