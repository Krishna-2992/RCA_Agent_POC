"""Filtered vector search for the incident pipeline.

Kept separate from src/utils/qdrant_client.py so the existing workflow's search
path is untouched. It reuses that module's client and retry policy rather than
opening a second connection or inventing a second set of timeouts.
"""

import time

from src.utils.qdrant_client import (
    QDRANT_MAX_ATTEMPTS,
    QDRANT_TIMEOUT,
    is_transient,
    qdrant_client
)


# A DNS blip fails instantly rather than after the read timeout, so the normal
# exponential backoff burns all three attempts in about three seconds - far too
# fast to ride out a resolver that recovers on its own within a minute. Name
# resolution failures therefore get more attempts and a longer, linear wait.

DNS_MAX_ATTEMPTS = 5

NAME_RESOLUTION_MARKERS = (
    "nodename nor servname",
    "name or service not known",
    "temporary failure in name resolution",
    "failed to resolve",
    "gaierror"
)


def is_name_resolution_failure(error) -> bool:

    text = f"{type(error).__name__} {error}".lower()

    source = getattr(error, "source", None)

    if source is not None:
        text += f" {type(source).__name__} {source}".lower()

    return any(
        marker in text
        for marker in NAME_RESOLUTION_MARKERS
    )


def search_with_retry(
    collection_name: str,
    vector: list[float],
    limit: int = 8,
    query_filter=None,
    with_payload: bool = True
):
    """Vector search, optionally restricted by a payload condition.

    `query_filter` needs a keyword index on the fields it references; the
    ingestion script creates those.
    """

    last_error = None

    dns_failure = False

    started = time.time()

    for attempt in range(
        1,
        max(QDRANT_MAX_ATTEMPTS, DNS_MAX_ATTEMPTS) + 1
    ):

        try:
            return qdrant_client.query_points(
                collection_name=collection_name,
                query=vector,
                limit=limit,
                with_payload=with_payload,
                query_filter=query_filter
            )

        except Exception as error:

            last_error = error

            if not is_transient(error):
                raise

            dns_failure = is_name_resolution_failure(error)

            limit = (
                DNS_MAX_ATTEMPTS
                if dns_failure
                else QDRANT_MAX_ATTEMPTS
            )

            if attempt >= limit:
                break

            backoff = (
                3 * attempt
                if dns_failure
                else 2 ** (attempt - 1)
            )

            reason = (
                "could not resolve the Qdrant hostname"
                if dns_failure
                else f"{type(error).__name__}: {error or 'timed out'}"
            )

            print(
                f"Qdrant search on '{collection_name}' failed "
                f"(attempt {attempt}/{limit}): {reason}. "
                f"Retrying in {backoff}s"
            )

            time.sleep(backoff)

    elapsed = time.time() - started

    if dns_failure:

        raise RuntimeError(
            "Could not resolve the Qdrant hostname after "
            f"{DNS_MAX_ATTEMPTS} attempts over {elapsed:.0f}s. The search "
            "service was never reached, so this is a DNS problem on this "
            "machine or network rather than a fault in the data or the "
            f"cluster. Underlying error: {last_error or 'name resolution failed'}"
        ) from last_error

    raise RuntimeError(
        f"Qdrant vector search on '{collection_name}' failed after "
        f"{QDRANT_MAX_ATTEMPTS} attempts over {elapsed:.0f}s "
        f"({QDRANT_TIMEOUT:.0f}s allowed per attempt). "
        f"Last error: {type(last_error).__name__}: {last_error or 'timed out'}"
    ) from last_error
