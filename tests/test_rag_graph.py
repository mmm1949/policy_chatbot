import asyncio

from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from config import Settings
from services.rag import NO_ANSWER, RAGService


class FakeModel:
    def __init__(self, *, grounded: bool = True, answer: str | None = None) -> None:
        self.grounded = grounded
        self.answer = answer or "The payout limit is $500 [limits.pdf, page 3]."
        self.calls: list[tuple[str, str]] = []

    async def ainvoke(self, messages: list[tuple[str, str]]) -> AIMessage:
        system_prompt = messages[0][1]
        human_prompt = messages[1][1]
        self.calls.append((system_prompt, human_prompt))

        if "Classify the latest message" in system_prompt:
            question = human_prompt.rsplit("Latest message: ", 1)[-1]
            if question == "what about it?" and "assistant:" in human_prompt:
                return AIMessage(content="follow_up")
            if question == "hello":
                return AIMessage(content="greeting")
            if question == "write me a poem":
                return AIMessage(content="out_of_scope")
            return AIMessage(content="policy")
        if "Rewrite the latest merchant policy question" in system_prompt:
            return AIMessage(content="What is the payout limit?")
        if "Create up to two distinct" in system_prompt:
            return AIMessage(content="account limit details\npayout limit details")
        if "Decide whether the supplied policy excerpts" in system_prompt:
            if "Payout limit policy" in human_prompt:
                return AIMessage(content="SUFFICIENT")
            return AIMessage(content="INSUFFICIENT")
        if "Check whether every factual claim" in system_prompt:
            return AIMessage(content="GROUNDED" if self.grounded else "UNSUPPORTED")
        if "Answer the current question" in system_prompt:
            return AIMessage(content=self.answer)
        return AIMessage(content="Hello! Ask me about merchant policies.")


class FakeRetriever:
    def __init__(self, mode: str = "single") -> None:
        self.mode = mode
        self.queries: list[str] = []

    def search(self, query: str) -> list[tuple[Document, float]]:
        self.queries.append(query)
        if self.mode == "multi_hop" and query == "What is the account limit and payout limit?":
            return [(self._document("Account limit policy"), 0.82)]
        if self.mode == "multi_hop" and query == "payout limit details":
            return [(self._document("Payout limit policy"), 0.79)]
        if self.mode == "empty":
            return []
        return [(self._document("Payout limit policy"), 0.82)]

    @staticmethod
    def _document(text: str) -> Document:
        return Document(
            page_content=text,
            metadata={"document_name": "limits.pdf", "page": 3, "source": "limits.pdf"},
        )


def make_service(
    retriever: FakeRetriever,
    *,
    grounded: bool = True,
    answer: str | None = None,
) -> RAGService:
    service = RAGService(
        Settings(groq_api_key="test-key"),
        retriever,
    )
    service.model = FakeModel(grounded=grounded, answer=answer)
    return service


def test_graph_generates_cited_answer_from_sufficient_evidence() -> None:
    retriever = FakeRetriever()
    service = make_service(retriever)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result["answer"] == "The payout limit is $500 [limits.pdf, page 3]."
    assert result["confidence"] == 0.82
    assert result["sources"] == [{"document": "limits.pdf", "page": 3}]
    assert service.get_history("merchant-a")[-1]["content"] == result["answer"]


def test_graph_refines_once_and_keeps_evidence_from_both_search_passes() -> None:
    retriever = FakeRetriever(mode="multi_hop")
    service = make_service(retriever)

    result = asyncio.run(
        service.answer("What is the account limit and payout limit?", "merchant-a")
    )

    assert result["answer"].startswith("The payout limit")
    assert retriever.queries == [
        "What is the account limit and payout limit?",
        "account limit details",
        "payout limit details",
    ]
    relevance_calls = [
        human for system, human in service.model.calls
        if "Decide whether the supplied policy excerpts" in system
    ]
    assert len(relevance_calls) == 2
    assert "Account limit policy" in relevance_calls[1]
    assert "Payout limit policy" in relevance_calls[1]


def test_unsupported_answer_is_replaced_with_fixed_no_answer() -> None:
    service = make_service(FakeRetriever(), grounded=False)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "confidence": 0.0, "sources": []}


def test_answer_with_citation_not_in_retrieved_sources_is_rejected() -> None:
    service = make_service(
        FakeRetriever(),
        answer="The payout limit is $500 [other-policy.pdf, page 9].",
    )

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "confidence": 0.0, "sources": []}
    assert not any(
        "Check whether every factual claim" in system
        for system, _ in service.model.calls
    )


def test_answer_with_unicode_citation_format_is_accepted() -> None:
    answer = "The payout limit is $500 【limits.pdf, page\u202f3】."
    service = make_service(FakeRetriever(), answer=answer)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result["answer"] == answer
    assert result["confidence"] == 0.82
    assert result["sources"] == [{"document": "limits.pdf", "page": 3}]


def test_follow_up_rewrite_uses_only_its_conversation_history() -> None:
    retriever = FakeRetriever()
    service = make_service(retriever)
    asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    result = asyncio.run(service.answer("what about it?", "merchant-a"))
    other_conversation = asyncio.run(service.answer("What is the payout limit?", "merchant-b"))

    assert result["answer"].startswith("The payout limit")
    assert retriever.queries[1] == "What is the payout limit?"
    assert service.get_history("merchant-a")[0]["content"] == "What is the payout limit?"
    assert service.get_history("merchant-b")[0]["content"] == "What is the payout limit?"
    assert other_conversation["answer"].startswith("The payout limit")
    assert service.get_history("missing-conversation") == []


def test_out_of_scope_message_uses_safe_fallback_without_retrieval() -> None:
    retriever = FakeRetriever()
    service = make_service(retriever)

    result = asyncio.run(service.answer("write me a poem", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "confidence": 0.0, "sources": []}
    assert retriever.queries == []


def test_empty_retrieval_uses_only_one_refinement_pass() -> None:
    retriever = FakeRetriever(mode="empty")
    service = make_service(retriever)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "confidence": 0.0, "sources": []}
    assert retriever.queries == [
        "What is the payout limit?",
        "account limit details",
        "payout limit details",
    ]


def test_greeting_path_does_not_search_policy_documents() -> None:
    retriever = FakeRetriever()
    service = make_service(retriever)

    result = asyncio.run(service.answer("hello", "merchant-a"))

    assert result == {
        "answer": "Hello! Ask me about merchant policies.",
        "confidence": 0.0,
        "sources": [],
    }
    assert retriever.queries == []
