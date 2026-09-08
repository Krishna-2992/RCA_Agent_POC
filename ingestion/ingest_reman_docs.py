"""Loads the SharePoint AWS Transform documentation into its own collection.

These are design-time documents: they explain how the REMAN programs work and
how they fail, not what happened on any given night. That distinction is why
they live apart from `reman_incidents` rather than being merged into it - the
retriever weighs a ServiceNow record and a design document very differently,
and blending them would let documentation masquerade as evidence of an event.

Selection and chunking live in ingestion.reman_docs, which records why each
source was kept or dropped.

Run:  python -m ingestion.ingest_reman_docs
      python -m ingestion.ingest_reman_docs --recreate
"""

import os
import sys
import time
import uuid

from dotenv import load_dotenv

from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams
)

from ingestion.reman_docs import (
    DOC_ROOT,
    build_embedding_text,
    load_chunks
)

from src.utils.llm import create_embeddings
from src.utils.qdrant_client import qdrant_client, upsert_with_retry


load_dotenv()


COLLECTION_NAME = os.getenv(
    "REMAN_DOCS_COLLECTION",
    "reman_docs"
)


VECTOR_SIZE = 1536

# One embedding request per 100 chunks is efficient; one Qdrant write of 100
# points is not. Each point carries a 1536-float vector plus its payload, and a
# 100-point batch overran the client's 20s write timeout mid-run. Writes are
# therefore sent in smaller pieces than they are embedded in.
BATCH_SIZE = 100

UPSERT_BATCH_SIZE = int(
    os.getenv("REMAN_DOCS_UPSERT_BATCH", "32")
)


# A long ingest is exposed to flakiness an interactive query never sees. This
# run hit a local resolver intermittently answering REFUSED for the Qdrant
# host; the shared three attempts span about three seconds, which was not long
# enough to ride it out. Six attempts back off to roughly half a minute.
UPSERT_MAX_ATTEMPTS = int(
    os.getenv("REMAN_DOCS_UPSERT_ATTEMPTS", "6")
)


# Exact-identifier lookup is filtered, not embedded - the same conclusion the
# incident ingester reached, and measured again here against the embedding
# model in use: IN001.MST scores 0.876 against IN0056.MST, a different file, and
# only 0.828 against IN0001.MST, the same file. A ticket naming a program or a
# corrupted file must narrow by payload before similarity is consulted at all.

INDEXED_FIELDS = [
    "program",
    "program_id",
    "application",
    "source_type",
    "data_files",
    "programs"
]


def create_collection(recreate=False):

    exists = qdrant_client.collection_exists(
        COLLECTION_NAME
    )

    if exists and recreate:

        qdrant_client.delete_collection(
            COLLECTION_NAME
        )

        exists = False

    if not exists:

        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )

        print(f"Created collection: {COLLECTION_NAME}")

    else:
        print(f"Collection already exists: {COLLECTION_NAME}")

    for field in INDEXED_FIELDS:

        try:
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD
            )

        except Exception:
            # Already indexed; Qdrant has no create-if-missing for this.
            pass


EMBED_MAX_ATTEMPTS = int(
    os.getenv("EMBED_MAX_ATTEMPTS", "5")
)


def point_id(chunk):

    return str(
        uuid.uuid5(
            uuid.NAMESPACE_DNS,
            chunk["chunk_id"]
        )
    )


def embed_with_retry(texts):
    """Retries a failed batch with backoff.

    The SDK already retries three times in quick succession, which is not
    enough: a first run of this corpus died on APIConnectionError after 300 of
    2,836 chunks. Backing off gives a transient network problem time to clear
    instead of abandoning the run.
    """

    last_error = None

    for attempt in range(1, EMBED_MAX_ATTEMPTS + 1):

        try:
            return create_embeddings(texts)

        except Exception as error:

            last_error = error

            if attempt == EMBED_MAX_ATTEMPTS:
                break

            backoff = 2 ** attempt

            print(
                f"  embedding batch failed "
                f"(attempt {attempt}/{EMBED_MAX_ATTEMPTS}): "
                f"{type(error).__name__}: {error}. "
                f"Retrying in {backoff}s"
            )

            time.sleep(backoff)

    raise RuntimeError(
        f"Embedding failed after {EMBED_MAX_ATTEMPTS} attempts. "
        f"Last error: {type(last_error).__name__}: {last_error}"
    ) from last_error


def already_ingested(chunks):
    """Ids already in the collection, so a resumed run skips finished work.

    Ids are deterministic, so this is safe: a chunk that reappears with changed
    text keeps its id and is overwritten rather than duplicated. Pass
    --recreate when the chunking itself changes.
    """

    existing = set()

    for start in range(0, len(chunks), BATCH_SIZE):

        batch = chunks[start:start + BATCH_SIZE]

        found = qdrant_client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id(chunk) for chunk in batch],
            with_payload=False,
            with_vectors=False
        )

        existing.update(
            str(record.id)
            for record in found
        )

    return existing


def build_batch_points(batch):

    texts = [
        build_embedding_text(chunk)
        for chunk in batch
    ]

    vectors = embed_with_retry(texts)

    points = []

    for chunk, text, vector in zip(batch, texts, vectors):

        payload = dict(chunk)

        # `content` is the embedded text and already contains `text` verbatim
        # after its header, so keeping both would double the payload for no
        # gain.
        payload.pop("text", None)

        payload["content"] = text

        payload["ingestion_source"] = "reman_sharepoint_docs"

        # What a citation shows the engineer.
        payload["source_title"] = (
            f"{chunk['program']} - {chunk['section']}"
        )

        payload["source_type_label"] = "SharePoint Document"

        points.append(
            PointStruct(
                # Deterministic id, so re-running updates in place.
                id=point_id(chunk),
                vector=vector,
                payload=payload
            )
        )

    return points


def embed_and_upsert(chunks):
    """Upserts each batch as it is embedded.

    Deliberately not "embed everything, then store everything": that pattern
    loses the whole run to one failed request near the end, which is exactly
    what happened on the first attempt.
    """

    done = 0

    for start in range(0, len(chunks), BATCH_SIZE):

        batch = chunks[start:start + BATCH_SIZE]

        points = build_batch_points(batch)

        for offset in range(0, len(points), UPSERT_BATCH_SIZE):

            upsert_with_retry(
                COLLECTION_NAME,
                points[offset:offset + UPSERT_BATCH_SIZE],
                max_attempts=UPSERT_MAX_ATTEMPTS
            )

        done += len(batch)

        print(f"  stored {done}/{len(chunks)}", flush=True)

    return done


def summarise(chunks):

    counts = {}

    for chunk in chunks:
        counts[chunk["source_type"]] = counts.get(chunk["source_type"], 0) + 1

    for source_type in sorted(counts):
        print(f"  {source_type:<24}{counts[source_type]:>6,}")

    characters = sum(
        len(chunk["text"])
        for chunk in chunks
    )

    print(
        f"  {'total':<24}{len(chunks):>6,} chunks, "
        f"{characters:,} chars"
    )


def ingest(doc_root=DOC_ROOT, recreate=False, resume=True):

    chunks = load_chunks(
        doc_root
    )

    print(f"Loaded {len(chunks)} chunks from {doc_root}")

    summarise(chunks)

    create_collection(
        recreate=recreate
    )

    if resume and not recreate:

        existing = already_ingested(chunks)

        if existing:

            chunks = [
                chunk
                for chunk in chunks
                if point_id(chunk) not in existing
            ]

            print(
                f"Resuming: {len(existing)} already stored, "
                f"{len(chunks)} to go"
            )

    if not chunks:
        print("Nothing to ingest; collection is already up to date.")

    else:
        embed_and_upsert(chunks)

    total = qdrant_client.get_collection(
        COLLECTION_NAME
    ).points_count

    print(f"Ingested into '{COLLECTION_NAME}': {total} points")

    return total


if __name__ == "__main__":

    ingest(
        recreate="--recreate" in sys.argv
    )
