import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from openai import OpenAI
from openai import BadRequestError

load_dotenv(override=True)


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value

# ----------------------------
# LLM Client
# ----------------------------

# Both clients default to a 600s read timeout, so a stalled request would hang
# the workflow for ten minutes with no way to tell it apart from slow work.
# Bounded attempts plus SDK-level retries fail fast and recover on their own.

LLM_TIMEOUT = float(
    os.getenv("LLM_TIMEOUT", "180")
)


EMBEDDING_TIMEOUT = float(
    os.getenv("EMBEDDING_TIMEOUT", "60")
)


MODEL_MAX_RETRIES = int(
    os.getenv("MODEL_MAX_RETRIES", "3")
)


llm = ChatOpenAI(
    model=get_required_env("LLM_MODEL_DEPLOYMENT_NAME"),
    api_key=get_required_env("LLM_MODEL_KEY"),
    base_url=get_required_env("LLM_MODEL_ENDPOINT"),
    temperature=0,
    timeout=LLM_TIMEOUT,
    max_retries=MODEL_MAX_RETRIES
)

# ----------------------------
# Embedding Client
# ----------------------------

embedding_client = OpenAI(
    api_key=get_required_env("EMBEDDING_MODEL_KEY"),
    base_url=get_required_env("EMBEDDING_MODEL_ENDPOINT"),
    timeout=EMBEDDING_TIMEOUT,
    max_retries=MODEL_MAX_RETRIES
)


def create_embedding(text: str) -> list[float]:
    """
    Generate embedding vector for input text.
    """

    embedding_model = get_required_env(
        "EMBEDDING_MODEL_DEPLOYMENT_NAME"
    )

    try:
        response = embedding_client.embeddings.create(
            model=embedding_model,
            input=text
        )
    except BadRequestError as error:
        error_text = str(error)

        if "unknown_model" in error_text or "Unknown model" in error_text:
            endpoint = get_required_env(
                "EMBEDDING_MODEL_ENDPOINT"
            )

            raise RuntimeError(
                "Embedding configuration error: "
                f"'{embedding_model}' is not recognized by "
                f"'{endpoint}'. For Azure/OpenAI-compatible endpoints, "
                "EMBEDDING_MODEL_DEPLOYMENT_NAME must match the embedding "
                "deployment name available on that endpoint, not just the "
                "base model family name."
            ) from error

        raise

    return response.data[0].embedding
