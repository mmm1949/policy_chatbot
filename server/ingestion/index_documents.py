import logging

from config import get_settings
from logging_config import configure_logging
from services.knowledge_base import KnowledgeBase


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    knowledge_base = KnowledgeBase(settings)
    count = knowledge_base.index_directory()
    print(f"Indexed {count} chunks in {settings.chroma_persist_directory}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger(__name__).exception("Document indexing failed")
        raise
