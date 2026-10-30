import asyncio
import logging
import re
import uuid
from typing import Literal, TypedDict

from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph

from config import Settings
from retrieval.vector import VectorRetriever
from services.memory import ConversationMemory
from services.prompts import PromptManager

logger = logging.getLogger(__name__)

NO_ANSWER = (
    "I could not find a verified answer in the policy knowledge base. "
    "Please ask a question related to the available merchant policy documents."
)


class SourceReference(TypedDict):
    document: str
    page: int | None


class RAGState(TypedDict, total=False):
    question: str
    conversation_id: str
    history: list[dict[str, str]]
    memories: list[dict[str, str]]
    category: Literal["policy", "follow_up", "greeting", "out_of_scope"]
    search_query: str
    queries: list[str]
    retrieval_pass: int
    results: list[tuple[Document, float]]
    confidence: float
    sufficient: bool
    grounded: bool
    answer: str
    sources: list[SourceReference]


class RAGResult(TypedDict):
    answer: str
    confidence: float
    sources: list[SourceReference]


class RAGService:
    def __init__(self, settings: Settings, retriever: VectorRetriever) -> None:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured. Set it in the project-root .env file.")
        self.retriever = retriever
        self.threshold = settings.relevance_threshold
        self.memory = ConversationMemory(settings.memory_database_path)
        self.prompts = PromptManager(settings.prompt_version)
        self.model = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0,
            max_retries=2,
        )
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(RAGState)
        workflow.add_node("recall_memory", self._recall_memory)
        workflow.add_node("classify", self._classify)
        workflow.add_node("rewrite", self._rewrite_query)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("evaluate_and_generate", self._evaluate_and_generate)
        workflow.add_node("refine_queries", self._refine_queries)
        workflow.add_node("verify_grounding", self._verify_grounding)
        workflow.add_node("no_answer", self._set_no_answer)
        workflow.add_node("social_response", self._social_response)
        workflow.add_node("remember", self._remember)

        workflow.add_edge(START, "recall_memory")
        workflow.add_edge("recall_memory", "classify")
        workflow.add_conditional_edges(
            "classify",
            self._route_classification,
            {
                "greeting": "social_response",
                "out_of_scope": "no_answer",
                "policy": "retrieve",
                "follow_up": "rewrite",
            },
        )
        workflow.add_edge("rewrite", "retrieve")
        workflow.add_edge("retrieve", "evaluate_and_generate")
        workflow.add_conditional_edges(
            "evaluate_and_generate",
            self._route_relevance,
            {
                "verify": "verify_grounding",
                "refine": "refine_queries",
                "no_answer": "no_answer",
            },
        )
        workflow.add_edge("refine_queries", "retrieve")
        workflow.add_conditional_edges(
            "verify_grounding",
            self._route_grounding,
            {"remember": "remember", "no_answer": "no_answer"},
        )
        workflow.add_edge("no_answer", "remember")
        workflow.add_edge("social_response", "remember")
        workflow.add_edge("remember", END)
        return workflow.compile()

    async def answer(self, question: str, conversation_id: str) -> RAGResult:
        state = await self.graph.ainvoke({
            "question": question,
            "conversation_id": conversation_id,
            "search_query": question,
            "queries": [question],
            "retrieval_pass": 0,
            "results": [],
            "confidence": 0.0,
            "sources": [],
        })
        return {
            "answer": state["answer"],
            "confidence": state["confidence"],
            "sources": state["sources"],
        }

    async def _recall_memory(self, state: RAGState) -> dict:
        return {
            "history": self.memory.get(state["conversation_id"]),
            "memories": self.memory.recall(
                state["conversation_id"],
                state["question"],
            ),
        }

    async def _classify(self, state: RAGState) -> dict:
        if self._is_common_pleasantry(state["question"]):
            return {"category": "greeting"}
        response = await self.model.ainvoke([
            ("system", self.prompts.render("classifier")),
            (
                "human",
                f"Recent conversation:\n{self._format_history(state['history']) or 'No earlier messages.'}"
                f"\n\nRelevant earlier conversation (context only):\n"
                f"{self._format_history(state['memories']) or 'No relevant earlier messages.'}"
                f"\n\nLatest message: {state['question']}",
            ),
        ])
        label = self._content(response).strip().lower().replace("-", "_").replace(" ", "_")
        valid_labels = {"policy", "follow_up", "greeting", "out_of_scope"}
        if label not in valid_labels:
            logger.warning("Query classifier returned an invalid label; treating as a policy question")
            label = "policy"
        if label == "follow_up" and not state["history"]:
            label = "policy"
        return {"category": label}

    @staticmethod
    def _route_classification(state: RAGState) -> str:
        category = state["category"]
        if category == "greeting":
            return "greeting"
        if category == "out_of_scope":
            return "out_of_scope"
        if category == "follow_up":
            return "follow_up"
        return "policy"

    async def _rewrite_query(self, state: RAGState) -> dict:
        response = await self.model.ainvoke([
            ("system", self.prompts.render("follow_up_rewrite")),
            (
                "human",
                f"Recent conversation:\n{self._format_history(state['history'])}"
                f"\n\nRelevant earlier conversation:\n"
                f"{self._format_history(state['memories']) or 'No relevant earlier messages.'}"
                f"\n\nLatest question: {state['question']}",
            ),
        ])
        rewritten = self._content(response).strip()
        return {"search_query": rewritten or state["question"], "queries": [rewritten or state["question"]]}

    async def _retrieve(self, state: RAGState) -> dict:
        queries = state["queries"]
        batches = await asyncio.gather(*(
            asyncio.to_thread(self.retriever.search, query)
            for query in queries
        ))
        merged: dict[tuple[str, str, str], tuple[Document, float]] = {}
        for document, score in state["results"]:
            source = str(document.metadata.get("source") or document.metadata.get("document_name") or "")
            page = str(document.metadata.get("page") or "")
            merged[(source, page, document.page_content)] = (document, score)
        for batch in batches:
            for document, score in batch:
                source = str(document.metadata.get("source") or document.metadata.get("document_name") or "")
                page = str(document.metadata.get("page") or "")
                key = (source, page, document.page_content)
                if key not in merged or score > merged[key][1]:
                    merged[key] = (document, score)
        results = sorted(merged.values(), key=lambda item: item[1], reverse=True)
        return {
            "results": results,
            "confidence": max((score for _, score in results), default=0.0),
        }

    async def _check_relevance(self, state: RAGState) -> dict:
        relevant = [
            (document, score)
            for document, score in state["results"]
            if score >= self.threshold
        ]
        if not relevant:
            return {"sufficient": False}

        response = await self.model.ainvoke([
            ("system", self.prompts.render("evidence_relevance")),
            (
                "human",
                f"Question: {state['question']}\n\nPolicy excerpts:\n{self._format_context(relevant)}",
            ),
        ])
        sufficient = self._content(response).strip().upper() == "SUFFICIENT"
        return {"sufficient": sufficient}

    async def _evaluate_and_generate(self, state: RAGState) -> dict:
        relevance, answer = await asyncio.gather(
            self._check_relevance(state),
            self._generate_answer(state),
        )
        return {**relevance, **answer}

    @staticmethod
    def _route_relevance(state: RAGState) -> str:
        if state["sufficient"]:
            return "verify"
        if state["retrieval_pass"] < 1:
            return "refine"
        return "no_answer"

    async def _refine_queries(self, state: RAGState) -> dict:
        response = await self.model.ainvoke([
            ("system", self.prompts.render("query_refinement")),
            (
                "human",
                f"Question: {state['question']}\n\nAlready searched: {state['search_query']}"
                f"\n\nEvidence found so far:\n{self._format_context(state['results']) or 'No matching excerpts.'}"
                f"\n\nRecent conversation for reference resolution only:\n"
                f"{self._format_history(state['history']) or 'No earlier messages.'}"
                f"\n\nRelevant earlier conversation for reference resolution only:\n"
                f"{self._format_history(state['memories']) or 'No relevant earlier messages.'}",
            ),
        ])
        queries = []
        for line in self._content(response).splitlines():
            query = line.strip().lstrip("-*0123456789. ").strip()
            if query and query.casefold() not in {item.casefold() for item in queries}:
                queries.append(query)
            if len(queries) == 2:
                break
        return {"queries": queries, "retrieval_pass": state["retrieval_pass"] + 1}

    async def _generate_answer(self, state: RAGState) -> dict:
        relevant = [
            (document, score)
            for document, score in state["results"]
            if score >= self.threshold
        ]
        if not relevant:
            return {"answer": "", "sources": []}
        response = await self.model.ainvoke([
            ("system", self.prompts.render("answer")),
            (
                "human",
                f"Recent conversation (context only; not policy evidence):\n"
                f"{self._format_history(state['history']) or 'No earlier messages.'}"
                f"\n\nRelevant earlier conversation (context only; not policy evidence):\n"
                f"{self._format_history(state['memories']) or 'No relevant earlier messages.'}"
                f"\n\nRetrieved policy excerpts:\n\n{self._format_context(relevant)}"
                f"\n\nCurrent question: {state['question']}",
            ),
        ])
        sources = []
        seen_sources = set()
        for document, _ in relevant:
            name = str(document.metadata.get("document_name") or document.metadata.get("source") or "Unknown")
            page = document.metadata.get("page")
            key = (name, page)
            if key not in seen_sources:
                sources.append({"document": name, "page": page})
                seen_sources.add(key)
        return {
            "answer": self._content(response),
            "sources": sources,
        }

    async def _verify_grounding(self, state: RAGState) -> dict:
        relevant = [
            (document, score)
            for document, score in state["results"]
            if score >= self.threshold
        ]
        if not self._citations_match_sources(state["answer"], state["sources"]):
            return {"grounded": False}
        response = await self.model.ainvoke([
            ("system", self.prompts.render("grounding")),
            (
                "human",
                f"Policy excerpts:\n{self._format_context(relevant)}"
                f"\n\nProposed answer:\n{state['answer']}",
            ),
        ])
        return {"grounded": self._content(response).strip().upper() == "GROUNDED"}

    @staticmethod
    def _citations_match_sources(
        answer: str,
        sources: list[SourceReference],
    ) -> bool:
        normalized_answer = answer.translate(str.maketrans({
            "【": "[",
            "】": "]",
            "［": "[",
            "］": "]",
        }))
        normalized_answer = re.sub(r"\s+", " ", normalized_answer)
        citations = re.findall(r"\[([^\[\]]+)\]", normalized_answer)
        if not citations:
            return False
        available = {
            (str(source["document"]), str(source["page"]) if source["page"] is not None else None)
            for source in sources
        }
        for citation in citations:
            name, separator, page_text = citation.strip().rpartition(", page ")
            if separator:
                if not page_text.isdigit() or (name, page_text) not in available:
                    return False
            elif (citation, None) not in available:
                return False
        return True

    @staticmethod
    def _route_grounding(state: RAGState) -> str:
        return "remember" if state["grounded"] else "no_answer"

    async def _set_no_answer(self, state: RAGState) -> dict:
        return {"answer": NO_ANSWER, "confidence": 0.0, "sources": []}

    async def _social_response(self, state: RAGState) -> dict:
        if self._is_common_pleasantry(state["question"]):
            return {
                "answer": "Hello! Ask me about merchant policies.",
                "confidence": 0.0,
                "sources": [],
            }
        response = await self.model.ainvoke([
            ("system", self.prompts.render("social_response", no_answer=NO_ANSWER)),
            (
                "human",
                f"Recent conversation:\n{self._format_history(state['history']) or 'No earlier messages.'}"
                f"\n\nLatest message: {state['question']}",
            ),
        ])
        return {
            "answer": self._content(response),
            "confidence": 0.0,
            "sources": [],
        }

    async def _remember(self, state: RAGState) -> dict:
        self.memory.add_exchange(state["conversation_id"], state["question"], state["answer"])
        return {"answer": state["answer"]}

    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        return self.memory.get(conversation_id)

    def clear_history(self, conversation_id: str) -> None:
        self.memory.clear(conversation_id)

    @staticmethod
    def _is_common_pleasantry(question: str) -> bool:
        normalized = " ".join(question.casefold().strip().rstrip("!.,?").split())
        return normalized in {
            "hi",
            "hello",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "thanks",
            "thank you",
            "bye",
            "goodbye",
        }

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        return "\n".join(
            f"{message['role']}: {message['content']}"
            for message in history
        )

    @staticmethod
    def _format_context(results: list[tuple[Document, float]]) -> str:
        context_parts = []
        for document, _ in results:
            name = str(document.metadata.get("document_name") or document.metadata.get("source") or "Unknown")
            page = document.metadata.get("page")
            citation = f"[{name}, page {page}]" if page else f"[{name}]"
            context_parts.append(f"{citation}\n{document.page_content}")
        return "\n\n".join(context_parts)

    @staticmethod
    def _content(response: object) -> str:
        content = getattr(response, "content", response)
        return content if isinstance(content, str) else str(content)


def new_conversation_id() -> str:
    return str(uuid.uuid4())
