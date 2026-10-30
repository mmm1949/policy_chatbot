import os
import uuid

import requests
import streamlit as st


API_URL = os.getenv("POLICY_API_URL", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="Toucan Merchant Assistant", layout="wide")

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

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stMainBlockContainer"],
    [data-testid="stBottomBlockContainer"] {
        max-width: 1000px;
        width: calc(100% - 2.5rem);
        margin-left: auto;
        margin-right: auto;
    }

    .toucan-navbar {
        position: sticky;
        top: 0;
        z-index: 1000;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1.5rem;
        margin: -0.2rem 0 2rem;
        padding: 0.95rem 1.25rem;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 18px;
        background: rgba(6, 29, 61, 0.88);
        backdrop-filter: blur(10px);
        box-shadow: 0 14px 35px rgba(6, 29, 61, 0.16);
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

    .toucan-hero {
        margin: 0 auto 2rem;
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

    [class*="st-key-chat-user-"],
    [class*="st-key-chat-assistant-"] {
        display: flex !important;
        flex-direction: column !important;
        width: 100%;
    }

    /* column layout: align-items controls left/right placement */
    [class*="st-key-chat-user-"] {
        align-items: flex-end !important;
    }

    [class*="st-key-chat-assistant-"] {
        align-items: flex-start !important;
    }

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"],
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] {
        width: 100%;
        max-width: 100%;
        padding: 0.85rem 1.05rem;
        border: 1px solid transparent;
        border-radius: 18px;
        box-shadow: 0 5px 18px rgba(6, 29, 61, 0.08);
    }

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] {
        border-color: #dce7f5;
        background: #eaf1fb;
        color: var(--toucan-ink);
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] {
        border-color: #173966;
        background: var(--toucan-navy);
        color: #f4f8ff;
    }

    [class*="st-key-chat-user-"] [data-testid^="stChatMessageAvatar"],
    [class*="st-key-chat-assistant-"] [data-testid^="stChatMessageAvatar"] {
        display: none !important;
    }

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] p,
    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] li,
    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] strong,
    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] em,
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] p,
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] li,
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] strong,
    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] em {
        color: inherit;
    }

    /* user message: dark text, right-aligned */
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

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] a {
        color: #1555a5;
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] a {
        color: #8adfd2;
    }

    [class*="st-key-chat-user-"] [data-testid="stChatMessage"] [data-testid="stCaptionContainer"] {
        color: var(--toucan-muted);
    }

    [class*="st-key-chat-assistant-"] [data-testid="stChatMessage"] [data-testid="stCaptionContainer"] {
        color: #91a8c7;
    }

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
        border-radius: 18px;
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
        border-radius: 12px;
    }

    [data-testid="stChatInput"] button:hover {
        background: var(--toucan-bright-blue);
    } 

    [data-testid="stSpinner"] {
    background: var(--toucan-navy);
    border: 1px solid #244d7d;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    box-shadow: 0 8px 24px rgba(6, 29, 61, 0.15);
    }

    [data-testid="stSpinner"] p {
        color: #f4f8ff !important;
        font-weight: 500;
    }
    
    /* Style the loading spinner animation circle/element if needed */
    [data-testid="stSpinner"] svg {
        color: var(--toucan-teal) !important;
    }

    @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] {
            padding: 0.8rem 0.8rem 6rem;
        }

        .toucan-navbar {
            align-items: flex-start;
            flex-direction: column;
            gap: 0.8rem;
        }

        .toucan-hero {
            padding: 1.4rem;
        }

    }
    </style>

    <nav class="toucan-navbar" aria-label="Toucan">
        <a class="toucan-brand" href="https://toucanus.com/" target="_blank" rel="noreferrer">
            TOUCAN
        </a>
    </nav>

    <section class="toucan-hero">
        <div class="toucan-eyebrow">Toucan · Merchant support</div>
        <h1>Policy answers, made clear.</h1>
        <p>Ask a question about your merchant policies. Answers are grounded in the available policy documents and include their sources.</p>
    </section>
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


def _render_message(message: dict, message_index: int) -> None:
    role = "user" if message["role"] == "user" else "assistant"
    with st.container(key=f"chat-{role}-{message_index}"):
        with st.chat_message(role, width="stretch"):
            if role == "assistant":
                st.markdown(message["content"])
            else:
                st.text(message["content"])

            details = []
            sources = message.get("sources") or []
            if sources:
                citations = "; ".join(
                    source["document"]
                    + (f", page {source['page']}" if source.get("page") else "")
                    for source in sources
                )
                details.append(f"Sources: {citations}")
            confidence = message.get("confidence")
            if confidence is not None:
                details.append(f"Confidence: {float(confidence):.0%}")
            if details:
                st.caption(" · ".join(details))


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

for message_index, chat_message in enumerate(st.session_state.messages):
    _render_message(chat_message, message_index)

question = st.chat_input("Write a message...")
if question:
    user_message = {"role": "user", "content": question}
    st.session_state.messages.append(user_message)
    _render_message(user_message, len(st.session_state.messages) - 1)

    try:
        with st.spinner("Searching policy documents..."):
            response = requests.post(
                f"{API_URL}/chat",
                json={
                    "question": question,
                    "conversation_id": st.session_state.conversation_id,
                },
                timeout=90,
            )
            response.raise_for_status()
            answer = response.json()
        assistant_message = {
            "role": "assistant",
            "content": answer["answer"],
            "sources": answer["sources"],
            "confidence": answer["confidence"],
        }
        st.session_state.messages.append(assistant_message)
        st.session_state.conversation_id = answer["conversation_id"]
        _render_message(assistant_message, len(st.session_state.messages) - 1)
    except requests.RequestException as exc:
        error = _request_error(exc)
        assistant_message = {"role": "assistant", "content": f"Request failed: {error}"}
        st.session_state.messages.append(assistant_message)
        _render_message(assistant_message, len(st.session_state.messages) - 1)