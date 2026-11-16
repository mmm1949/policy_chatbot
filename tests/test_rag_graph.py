import asyncio
from pathlib import Path

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
        if "Check whether every factual claim" in system_prompt:
            has_complete_evidence = (
                "Payout limit policy" in human_prompt
                or "Account limit policy" not in human_prompt
            )
            return AIMessage(
                content="GROUNDED"
                if self.grounded and has_complete_evidence
                else "UNSUPPORTED"
            )
        if "Answer the current question" in system_prompt:
            return AIMessage(content=self.answer)
        return AIMessage(content="Hello! Ask me about merchant policies.")


class FakeRetriever:
    def __init__(self, mode: str = "single") -> None:
        self.mode = mode
        self.queries: list[str] = []

    def search(
        self, query: str, _metadata_hints: dict[str, str] | None = None
    ) -> list[tuple[Document, float]]:
        self.queries.append(query)
        if self.mode == "multi_hop" and query == "What is the account limit and payout limit?":
            return [(self._document("Account limit policy"), 0.82)]
        if self.mode == "multi_hop" and query == "payout limit details":
            return [(self._document("Payout limit policy"), 0.79)]
        if self.mode == "empty":
            return []
        if self.mode == "two_sources":
            return [
                (self._document("Payout limit policy"), 0.82),
                (
                    Document(
                        page_content="Uncited unrelated policy",
                        metadata={
                            "document_name": "other-policy.pdf",
                            "page": 9,
                            "source": "other-policy.pdf",
                        },
                    ),
                    0.81,
                ),
            ]
        return [(self._document("Payout limit policy"), 0.82)]

    @staticmethod
    def _document(text: str) -> Document:
        return Document(
            page_content=text,
            metadata={"document_name": "limits.pdf", "page": 3, "source": "limits.pdf"},
        )


def make_service(
    retriever: FakeRetriever,
    memory_database_path: Path,
    *,
    grounded: bool = True,
    answer: str | None = None,
) -> RAGService:
    service = RAGService(
        Settings(
            groq_api_key="test-key",
            memory_database_path=memory_database_path,
        ),
        retriever,
    )
    service.model = FakeModel(grounded=grounded, answer=answer)
    return service


def test_graph_generates_cited_answer_from_sufficient_evidence(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result["answer"] == "The payout limit is $500 [limits.pdf, page 3]."
    assert result["reranker_score"] == 0.82
    assert result["sources"] == [{"document": "limits.pdf", "page": 3}]
    assert service.get_history("merchant-a")[-1]["content"] == result["answer"]


def test_graph_refines_once_and_keeps_evidence_from_both_search_passes(tmp_path: Path) -> None:
    retriever = FakeRetriever(mode="multi_hop")
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    result = asyncio.run(
        service.answer("What is the account limit and payout limit?", "merchant-a")
    )

    assert result["answer"].startswith("The payout limit")
    assert retriever.queries == [
        "What is the account limit and payout limit?",
        "account limit details",
        "payout limit details",
    ]
    grounding_calls = [
        human for system, human in service.model.calls
        if "Check whether every factual claim" in system
    ]
    assert len(grounding_calls) == 2
    assert "Account limit policy" in grounding_calls[0]
    assert "Account limit policy" in grounding_calls[1]
    assert "Payout limit policy" in grounding_calls[1]


def test_unsupported_answer_is_replaced_with_fixed_no_answer(tmp_path: Path) -> None:
    service = make_service(FakeRetriever(), tmp_path / "memory.sqlite3", grounded=False)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "reranker_score": 0.0, "sources": []}


def test_answer_with_citation_not_in_retrieved_sources_is_rejected(tmp_path: Path) -> None:
    service = make_service(
        FakeRetriever(),
        tmp_path / "memory.sqlite3",
        answer="The payout limit is $500 [other-policy.pdf, page 9].",
    )

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "reranker_score": 0.0, "sources": []}
    assert not any(
        "Check whether every factual claim" in system
        for system, _ in service.model.calls
    )


def test_answer_with_unicode_citation_format_is_accepted(tmp_path: Path) -> None:
    answer = "The payout limit is $500 【limits.pdf, page\u202f3】."
    service = make_service(FakeRetriever(), tmp_path / "memory.sqlite3", answer=answer)

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result["answer"] == answer
    assert result["reranker_score"] == 0.82
    assert result["sources"] == [{"document": "limits.pdf", "page": 3}]


def test_sources_only_include_passages_cited_in_the_answer(tmp_path: Path) -> None:
    service = make_service(
        FakeRetriever(mode="two_sources"),
        tmp_path / "memory.sqlite3",
    )

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result["sources"] == [{"document": "limits.pdf", "page": 3}]


def test_follow_up_rewrite_uses_only_its_conversation_history(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")
    asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    result = asyncio.run(service.answer("what about it?", "merchant-a"))
    other_conversation = asyncio.run(service.answer("What is the payout limit?", "merchant-b"))

    assert result["answer"].startswith("The payout limit")
    assert retriever.queries[1] == "What is the payout limit?"
    assert service.get_history("merchant-a")[0]["content"] == "What is the payout limit?"
    assert service.get_history("merchant-b")[0]["content"] == "What is the payout limit?"
    assert other_conversation["answer"].startswith("The payout limit")
    assert service.get_history("missing-conversation") == []


def test_out_of_scope_message_uses_safe_fallback_without_retrieval(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    result = asyncio.run(service.answer("write me a poem", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "reranker_score": 0.0, "sources": []}
    assert retriever.queries == []


def test_empty_retrieval_uses_only_one_refinement_pass(tmp_path: Path) -> None:
    retriever = FakeRetriever(mode="empty")
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    result = asyncio.run(service.answer("What is the payout limit?", "merchant-a"))

    assert result == {"answer": NO_ANSWER, "reranker_score": 0.0, "sources": []}
    assert retriever.queries == [
        "What is the payout limit?",
        "account limit details",
        "payout limit details",
    ]


def test_greeting_path_does_not_search_policy_documents(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    result = asyncio.run(service.answer("hello", "merchant-a"))

    assert result == {
        "answer": "Hello! Ask me about merchant policies.",
        "reranker_score": 0.0,
        "sources": [],
    }
    assert retriever.queries == []


def test_standalone_greeting_variants_skip_classifier_and_retrieval(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    for index, greeting in enumerate(("Hi there!", "How are you?", "Thanks so much.")):
        result = asyncio.run(service.answer(greeting, f"greeting-{index}"))
        assert result["reranker_score"] == 0.0
        assert result["sources"] == []

    assert retriever.queries == []
    assert service.model.calls == []


def test_direct_policy_question_is_not_reclassified_as_follow_up(tmp_path: Path) -> None:
    service = make_service(FakeRetriever(), tmp_path / "memory.sqlite3")
    state = {
        "question": "A card was declined with code 59. Is that serious?",
        "history": [
            {"role": "user", "content": "A card was declined with code 59. Is that serious?"},
            {"role": "assistant", "content": NO_ANSWER},
        ],
        "memories": [],
    }

    result = asyncio.run(service._classify(state))

    assert result == {"category": "policy"}
    assert service.model.calls == []


def test_repeated_policy_question_does_not_prompt_with_previous_no_answer(tmp_path: Path) -> None:
    service = make_service(FakeRetriever(), tmp_path / "memory.sqlite3")

    asyncio.run(
        service.answer(
            "A card was declined with code 59. Is that serious?",
            "repeat-policy",
        )
    )

    answer_prompts = [
        human for system, human in service.model.calls
        if "Answer the current question" in system
    ]
    assert answer_prompts
    assert NO_ANSWER not in answer_prompts[0]
    assert "No earlier messages." in answer_prompts[0]


def test_contextual_follow_up_still_uses_conversation_history(tmp_path: Path) -> None:
    service = make_service(FakeRetriever(), tmp_path / "memory.sqlite3")
    state = {
        "question": "What about that?",
        "history": [
            {"role": "user", "content": "What is the payout limit?"},
            {"role": "assistant", "content": "$500"},
        ],
        "memories": [],
    }

    result = asyncio.run(service._classify(state))

    assert result == {"category": "follow_up"}
    assert service.model.calls == []


def test_greeting_with_policy_question_is_still_retrieved(tmp_path: Path) -> None:
    retriever = FakeRetriever()
    service = make_service(retriever, tmp_path / "memory.sqlite3")

    asyncio.run(
        service.answer("Hi, what is the payout limit?", "greeting-policy")
    )

    assert retriever.queries[0] == "Hi, what is the payout limit?"
