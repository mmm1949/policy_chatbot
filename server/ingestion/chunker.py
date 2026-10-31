import hashlib

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_parent_documents(
    documents: list[Document], parent_size: int
) -> list[Document]:
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=parent_size,
        chunk_overlap=0,
        add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    parents = []
    for document in documents:
        if document.metadata.get("content_type") == "table":
            sections = [document]
        else:
            sections = parent_splitter.split_documents([document])
        for section in sections:
            metadata = dict(section.metadata)
            parent_id = hashlib.sha256(
                "\0".join(
                    (
                        str(metadata.get("source", "")),
                        str(metadata.get("page", "")),
                        str(metadata.get("content_type", "text")),
                        str(metadata.get("table_index", "")),
                        str(metadata.get("start_index", "")),
                        section.page_content,
                    )
                ).encode("utf-8")
            ).hexdigest()
            metadata["parent_id"] = parent_id
            parents.append(Document(page_content=section.page_content, metadata=metadata))
    return parents


def split_documents(
    documents: list[Document], chunk_size: int, chunk_overlap: int
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    for chunk in chunks:
        parent_id = str(chunk.metadata["parent_id"])
        start_index = chunk.metadata.get("start_index", 0)
        chunk.metadata["chunk_id"] = hashlib.sha256(
            f"{parent_id}:{start_index}:{chunk.page_content}".encode("utf-8")
        ).hexdigest()
    return chunks
