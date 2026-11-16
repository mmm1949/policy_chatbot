import html
import os
import uuid

import requests
import streamlit as st


API_URL = os.getenv("POLICY_API_URL", "http://localhost:8000").rstrip("/")
API_TOKEN = os.getenv("POLICY_API_TOKEN", "")
API_HEADERS = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
st.set_page_config(page_title="Toucan Merchant Assistant", layout="wide")

SAMPLE_QUESTIONS = [
    ("Refunds", "What is the refund policy for merchants?"),
    ("Settlements", "How long do settlements take to reach my account?"),
    ("Chargebacks", "What are the timelines for disputing a chargeback?"),
    ("Restrictions", "Which business types are prohibited or restricted?"),
]

st.markdown(
    """
    <style>
    :root {
        --toucan-navy: #061d3d;
        --toucan-blue: #1555a5;
        --toucan-bright-blue: #1464e8;
        --toucan-teal: #12b89f;
        --toucan-orange: #f5a623;
        --toucan-ink: #15243a;
        --toucan-muted: #66758b;
        --toucan-canvas: #f4f7fb;
    }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 50% 0%, rgba(21, 85, 165, 0.07), transparent 40%),
            var(--toucan-canvas);
    }

    /* Streamlit's own header is replaced by our fixed navbar */
    [data-testid="stHeader"] {
        display: none;
    }

    [data-testid="stMainBlockContainer"],
    [data-testid="stBottomBlockContainer"] {
        max-width: 820px;
        width: calc(100% - 2.5rem);
        margin-left: auto;
        margin-right: auto;
    }

    [data-testid="stMainBlockContainer"] {
        padding-top: 5.5rem;
        padding-bottom: 7rem;
    }

    /* ---------- Fixed navbar ---------- */
    .toucan-navbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 999999;
        background: rgba(6, 29, 61, 0.94);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.10);
        box-shadow: 0 8px 28px rgba(6, 29, 61, 0.18);
    }

    .toucan-navbar-inner {
        max-width: 1100px;
        margin: 0 auto;
        padding: 0.85rem 1.25rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1.5rem;
    }

    .toucan-brand {
        color: #fff !important;
        font-size: 1.2rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-decoration: none !important;
        white-space: nowrap;
    }

    .toucan-brand span {
        color: var(--toucan-orange);
    }

    .toucan-nav-tag {
        color: #79e0d0;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }

    /* ---------- Hero ---------- */
    .toucan-hero {
        margin: 0.5rem auto 1.4rem;
        padding: 1.9rem 2rem;
        border-radius: 22px;
        background: linear-gradient(122deg, #092c5c 0%, #1555a5 72%, #1769bb 100%);
        color: #fff;
        box-shadow: 0 18px 42px rgba(9, 44, 92, 0.18);
    }

    .toucan-eyebrow {
        margin: 0 0 0.55rem;
        color: #79e0d0;
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }

    .toucan-hero h1 {
        margin: 0;
        color: #fff;
        font-size: clamp(1.65rem, 4vw, 2.2rem);
        line-height: 1.16;
        letter-spacing: -0.035em;
    }

    .toucan-hero p {
        max-width: 650px;
        margin: 0.7rem 0 0;
        color: #d8e6fa;
        font-size: 0.98rem;
        line-height: 1.55;
    }

    .toucan-suggest-label {
        margin: 0.4rem 0 0.6rem;
        color: var(--toucan-muted);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }

    /* ---------- Sample question cards ---------- */
    [class*="st-key-suggest-"] button {
        width: 100%;
        min-height: 72px;
        padding: 0.9rem 1.1rem;
        justify-content: flex-start;
        text-align: left;
        border: 1px solid #dce7f5;
        border-radius: 16px;
        background: #ffffff;
        color: var(--toucan-ink);
        box-shadow: 0 4px 14px rgba(6, 29, 61, 0.05);
        transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
    }

    [class*="st-key-suggest-"] button > div {
        justify-content: flex-start;
        width: 100%;
    }

    [class*="st-key-suggest-"] button p {
        text-align: left;
        font-size: 0.95rem;
        font-weight: 500;
        line-height: 1.4;
        color: var(--toucan-ink);
    }

    [class*="st-key-suggest-"] button:hover {
        border-color: var(--toucan-teal);
        background: #ffffff;
        box-shadow: 0 8px 22px rgba(18, 184, 159, 0.16);
        transform: translateY(-1px);
    }

    [class*="st-key-suggest-"] button:focus:not(:active) {
        border-color: var(--toucan-teal);
        color: var(--toucan-ink);
    }

    /* ---------- Chat messages ---------- */
    [class*="st-key-chat-user-"],
    [class*="st-key-chat-assistant-"] {
        display: flex !important;
        flex-direction: column !important;
        width: 100%;
    }

    [class*="st-key-chat-user-"] {
        align-items: flex-end !important;
    }

    [class*="st-key-chat-assistant-"] {
        align-items: flex-start !important;
    }

    [data-testid^="stChatMessageAvatar"] {
        display: none !important;
    }

    /* User: compact rounded bubble on the right */
    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] {
        width: fit-content;
        max-width: 80%;
        padding: 0.7rem 1.1rem;
        border: 1px solid #dce7f5;
        border-radius: 20px 20px 6px 20px;
        background: #eaf1fb;
        box-shadow: 0 3px 12px rgba(6, 29, 61, 0.05);
    }

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"],
    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] * {
        color: #0b1a2e !important;
        text-align: left;
    }

    [class*="st-key-chat-user-"] [data-testid="stText"],
    [class*="st-key-chat-user-"] [data-testid="stText"] * {
        font-family: inherit !important;
        white-space: pre-wrap;
        color: #0b1a2e !important;
    }

    /* Assistant: no bubble, plain readable text like Claude */
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] {
        width: 100%;
        max-width: 100%;
        padding: 0.2rem 0 0.4rem;
        border: none;
        background: transparent;
        box-shadow: none;
        color: var(--toucan-ink);
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] p,
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] li {
        color: var(--toucan-ink);
        font-size: 1rem;
        line-height: 1.7;
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] strong {
        color: var(--toucan-navy);
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] a {
        color: var(--toucan-blue);
    }

    .assistant-head {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.45rem;
    }

    .assistant-avatar {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 30px;
        height: 30px;
        border-radius: 50%;
        background: var(--toucan-navy);
        color: var(--toucan-orange);
        font-size: 0.85rem;
        font-weight: 800;
        box-shadow: 0 4px 12px rgba(6, 29, 61, 0.22);
    }

    .assistant-name {
        color: var(--toucan-navy);
        font-size: 0.86rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }

    /* Sources and reranker-score chips */
    .meta-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.45rem;
        margin-top: 0.7rem;
        padding-top: 0.7rem;
        border-top: 1px solid #dce7f5;
    }

    .meta-label {
        color: var(--toucan-muted);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }

    .src-chip {
        display: inline-flex;
        align-items: center;
        padding: 0.28rem 0.7rem;
        border: 1px solid #cfe0f5;
        border-radius: 999px;
        background: #ffffff;
        color: var(--toucan-blue);
        font-size: 0.78rem;
        font-weight: 600;
    }

    .score-chip {
        display: inline-flex;
        align-items: center;
        margin-left: auto;
        padding: 0.28rem 0.7rem;
        border-radius: 999px;
        background: rgba(18, 184, 159, 0.12);
        color: #0b7f6d;
        font-size: 0.78rem;
        font-weight: 700;
    }

    /* ---------- Input ---------- */
    [data-testid="stBottomBlockContainer"] {
        padding-top: 0.6rem;
        padding-bottom: 0.8rem;
        background: transparent !important;
    }

    [data-testid="stBottom"],
    [data-testid="stBottom"] > div,
    .stChatFloatingInputContainer {
        background: transparent !important;
        background-image: none !important;
        box-shadow: none !important;
    }

    [data-testid="stChatInput"] {
        width: 100%;
        max-width: 100%;
        border: 1px solid #244d7d;
        border-radius: 22px;
        background: var(--toucan-navy);
        box-shadow: 0 10px 30px rgba(6, 29, 61, 0.2);
    }

    [data-testid="stChatInput"] textarea {
        color: #fff !important;
        -webkit-text-fill-color: #fff !important;
        caret-color: var(--toucan-teal);
    }

    [data-testid="stChatInput"] textarea::placeholder {
        color: #cfddf0 !important;
        -webkit-text-fill-color: #cfddf0 !important;
        opacity: 1;
    }

    [data-testid="stChatInput"] button {
        color: #fff;
        background: var(--toucan-blue);
        border-radius: 14px;
    }

    [data-testid="stChatInput"] button:hover {
        background: var(--toucan-bright-blue);
    }

    /* ---------- Thinking indicator ---------- */
    [data-testid="stSpinner"] {
        padding: 0.4rem 0;
    }

    [data-testid="stSpinner"] p {
        color: var(--toucan-muted) !important;
        font-weight: 500;
        font-style: italic;
    }

    [data-testid="stSpinner"] svg,
    [data-testid="stSpinner"] i {
        color: var(--toucan-teal) !important;
        border-top-color: var(--toucan-teal) !important;
    }

    @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] {
            padding: 5rem 0.8rem 6rem;
        }

        .toucan-navbar-inner {
            padding: 0.75rem 1rem;
        }

        .toucan-nav-tag {
            display: none;
        }

        .toucan-hero {
            padding: 1.4rem;
        }

        [class*="st-key-chat-user-"] [data-testid="stChatMessage"] {
            max-width: 92%;
        }

        .score-chip {
            margin-left: 0;
        }
    }
    </style>

    <nav class="toucan-navbar" aria-label="Toucan">
        <div class="toucan-navbar-inner">
            <a class="toucan-brand" href="https://toucanus.com/" target="_blank" rel="noreferrer">
                TOUCAN
            </a>
            <span class="toucan-nav-tag">Merchant support</span>
        </div>
    </nav>
    """,
    unsafe_allow_html=True,
)


def _request_error(exc: requests.RequestException) -> str:
    if exc.response is not None:
        try:
            detail = exc.response.json().get("detail")
            if detail:
                return str(detail)
        except ValueError:
            pass
    return str(exc)


def _meta_html(message: dict) -> str:
    chips = []
    sources = message.get("sources") or []
    if sources:
        chips.append('<span class="meta-label">Sources</span>')
        for source in sources:
            label = source["document"] + (
                f", page {source['page']}" if source.get("page") else ""
            )
            chips.append(f'<span class="src-chip">{html.escape(label)}</span>')
    reranker_score = message.get("reranker_score")
    if reranker_score is not None:
        chips.append(
            f'<span class="score-chip">Reranker score {float(reranker_score):.3f}</span>'
        )
    if not chips:
        return ""
    return f'<div class="meta-row">{"".join(chips)}</div>'


def _render_message(message: dict, message_index: int) -> None:
    role = "user" if message["role"] == "user" else "assistant"
    with st.container(key=f"chat-{role}-{message_index}"):
        with st.chat_message(role, width="stretch"):
            if role == "assistant":
                st.markdown(
                    '<div class="assistant-head">'
                    '<span class="assistant-avatar">T</span>'
                    '<span class="assistant-name">Toucan Assistant</span>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(message["content"])
            else:
                st.text(message["content"])

            meta = _meta_html(message)
            if meta:
                st.markdown(meta, unsafe_allow_html=True)


def _queue_question(text: str) -> None:
    st.session_state.pending_question = text


if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
if "history_loaded" not in st.session_state:
    st.session_state.history_loaded = False

if not st.session_state.history_loaded:
    try:
        history_response = requests.get(
            f"{API_URL}/conversations/{st.session_state.conversation_id}",
            headers=API_HEADERS,
            timeout=10,
        )
        history_response.raise_for_status()
        st.session_state.messages = [
            {"role": message["role"], "content": message["content"]}
            for message in history_response.json()["messages"]
        ]
    except requests.RequestException as exc:
        st.warning(f"Could not restore this conversation: {_request_error(exc)}")
    finally:
        st.session_state.history_loaded = True

# A clicked sample question is handled exactly like a typed one.
clicked_question = st.session_state.pop("pending_question", None)

# Welcome screen (hero + sample questions) only before the conversation starts.
if not st.session_state.messages and not clicked_question:
    st.markdown(
        """
        <section class="toucan-hero">
            <div class="toucan-eyebrow">Toucan · Merchant support</div>
            <h1>Policy answers, made clear.</h1>
            <p>Ask a question about your merchant policies. Answers are grounded in the available policy documents and include their sources.</p>
        </section>
        <div class="toucan-suggest-label">Try asking</div>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(2)
    for index, (title, text) in enumerate(SAMPLE_QUESTIONS):
        with columns[index % 2]:
            st.button(
                text,
                key=f"suggest-{index}",
                on_click=_queue_question,
                args=(text,),
                use_container_width=True,
            )

for message_index, chat_message in enumerate(st.session_state.messages):
    _render_message(chat_message, message_index)

question = st.chat_input("Write a message...") or clicked_question
if question:
    user_message = {"role": "user", "content": question}
    st.session_state.messages.append(user_message)
    _render_message(user_message, len(st.session_state.messages) - 1)

    try:
        with st.spinner("Processing your message..."):
            response = requests.post(
                f"{API_URL}/chat",
                json={
                    "question": question,
                    "conversation_id": st.session_state.conversation_id,
                },
                headers=API_HEADERS,
                timeout=90,
            )
            response.raise_for_status()
            answer = response.json()
        assistant_message = {
            "role": "assistant",
            "content": answer["answer"],
            "sources": answer["sources"],
            "reranker_score": answer["reranker_score"],
        }
        st.session_state.messages.append(assistant_message)
        st.session_state.conversation_id = answer["conversation_id"]
        _render_message(assistant_message, len(st.session_state.messages) - 1)
    except requests.RequestException as exc:
        error = _request_error(exc)
        assistant_message = {"role": "assistant", "content": f"Request failed: {error}"}
        st.session_state.messages.append(assistant_message)
        _render_message(assistant_message, len(st.session_state.messages) - 1)