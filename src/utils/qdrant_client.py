import os
import time

from dotenv import load_dotenv

from qdrant_client import QdrantClient

from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse
)


load_dotenv()


# A single slow response used to kill the whole investigation: the client waited
# the full read timeout and the exception surfaced as the bare word "timed out".
# Short attempts plus retries recover from a transient stall in a few seconds
# instead of failing the run after a minute.

QDRANT_TIMEOUT = float(
    os.getenv("QDRANT_TIMEOUT", "20")
)


QDRANT_MAX_ATTEMPTS = int(
    os.getenv("QDRANT_MAX_ATTEMPTS", "3")
)


RETRYABLE_STATUS = {
    429,
    500,
    502,
    503,
    504
}


qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
    timeout=QDRANT_TIMEOUT
)


def is_transient(error: Exception) -> bool:
    """True for failures that a retry can plausibly recover from."""

    # Read/connect timeouts and dropped connections arrive wrapped in this.
    if isinstance(error, ResponseHandlingException):
        return True

    if isinstance(error, UnexpectedResponse):
        return error.status_code in RETRYABLE_STATUS

    return False


def query_with_retry(
    collection_name: str,
    vector: list[float],
    limit: int = 5,
    with_payload: bool = True
):
    """Vector search that survives a transient Qdrant hiccup."""

    last_error = None

    for attempt in range(
        1,
        QDRANT_MAX_ATTEMPTS + 1
    ):

        try:
            return qdrant_client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                with_payload=with_payload
            )

        except Exception as error:

            last_error = error

            if not is_transient(error):
                raise

            if attempt == QDRANT_MAX_ATTEMPTS:
                break

            backoff = 2 ** (attempt - 1)

            print(
                f"Qdrant search on '{collection_name}' failed "
                f"(attempt {attempt}/{QDRANT_MAX_ATTEMPTS}): "
                f"{type(error).__name__}: {error or 'timed out'}. "
                f"Retrying in {backoff}s"
            )

            time.sleep(
                backoff
            )

    raise RuntimeError(
        f"Qdrant vector search on '{collection_name}' failed after "
        f"{QDRANT_MAX_ATTEMPTS} attempts "
        f"({QDRANT_TIMEOUT:.0f}s each). Last error: "
        f"{type(last_error).__name__}: {last_error or 'timed out'}"
    ) from last_error


def upsert_with_retry(
    collection_name: str,
    points: list,
    max_attempts: int | None = None
):
    """Write that survives a transient Qdrant hiccup.

    Writes need this more than reads do: a batch of points carries vectors and
    payload, so it is far larger than a query and far likelier to exceed the
    read timeout on a slow link. Ingesting the Reman documents failed on "The
    write operation timed out" partway through with no retry in place, losing
    the batch in flight.
    """

    attempts = max_attempts or QDRANT_MAX_ATTEMPTS

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        try:
            return qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )

        except Exception as error:

            last_error = error

            if not is_transient(error):
                raise

            if attempt == attempts:
                break

            backoff = 2 ** (attempt - 1)

            print(
                f"Qdrant upsert to '{collection_name}' failed "
                f"(attempt {attempt}/{attempts}): "
                f"{type(error).__name__}: {error or 'timed out'}. "
                f"Retrying in {backoff}s"
            )

            time.sleep(
                backoff
            )

    raise RuntimeError(
        f"Qdrant upsert to '{collection_name}' failed after "
        f"{attempts} attempts. Last error: "
        f"{type(last_error).__name__}: {last_error or 'timed out'}"
    ) from last_error
