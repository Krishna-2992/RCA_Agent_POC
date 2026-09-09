"""Retrieves REMAN documentation for an incident the ticket history cannot explain.

Consulted only after the ServiceNow evaluator reports it has not found enough,
which is also where these documents are worth the most: when history already
holds nine identical tickets with the same fix, a design document adds little.

Search is hybrid for the same reason the incident retriever is, only more so.
Measured against the embedding model in use, IN001.MST scores 0.876 against
IN0056.MST - a different file - and 0.828 against IN0001.MST, the same file.
Similarity is blind to identifiers, so programs and data files are matched by
payload filter and similarity is used only for the prose around them.
"""

import os
import re

from qdrant_client import models

from ingestion.reman_docs import find_data_files

from src.utils.incident_search import search_with_retry
from src.utils.llm import create_embedding


COLLECTION_NAME = os.getenv(
    "REMAN_DOCS_COLLECTION",
    "reman_docs"
)


RESULT_LIMIT = int(
    os.getenv("REMAN_DOCS_RESULT_LIMIT", "6")
)


# No single strategy may fill the result set. Without this cap the identifier
# filter took all six slots for "IN001.MST file was corrupt", four of them
# background documents that merely mention the file - crowding out the LMS
# technical extract that actually says what it holds and which programs read it.
PER_STRATEGY_LIMIT = max(
    2,
    RESULT_LIMIT // 2
)


PROGRAM_RE = re.compile(
    r"\b(F\d[A-Z]{2}\d{4})\b",
    re.I
)


# The support team supports three applications. A ticket usually names one of
# them in plain words even when it names no program at all, which is the common
# case: 43% of incidents mention a program, but almost all mention a system.
APPLICATION_KEYWORDS = {
    "LMS": ("lms", "location management", "warehouse location", "bin"),
    "Inventory": ("inventory", "stock", "on-hand", "onhand", "part master"),
    "Reman Index": ("index", "security", "sign-on", "signon", "login",
                    "password", "access level"),
    "BOM": ("bom", "bill of material", "assembly", "component")
}


PAYLOAD_FIELDS = [
    "chunk_id",
    "program",
    "program_id",
    "application",
    "source_type",
    "section",
    "content",
    "data_files",
    "programs",
    "source_title",
    "source_type_label"
]


def extract_identifiers(*texts):
    """Programs and data files named anywhere in the incident.

    Data files are normalised by the same function the ingester used, so a
    ticket's "IN001.MST" and a document's "IN0001.MST" land on one key. Sharing
    the function rather than copying the pattern is deliberate: if the two ever
    disagreed, the failure would be silent - a filter that quietly matches
    nothing.
    """

    blob = " ".join(
        str(text or "")
        for text in texts
    )

    programs = []

    for match in PROGRAM_RE.findall(blob):

        match = match.upper()

        if match not in programs:
            programs.append(match)

    return {
        "programs": programs,
        "data_files": find_data_files(blob)
    }


def infer_applications(*texts):

    blob = " ".join(
        str(text or "")
        for text in texts
    ).lower()

    found = []

    for application, keywords in APPLICATION_KEYWORDS.items():

        if any(keyword in blob for keyword in keywords):
            found.append(application)

    return found


def build_search_query(state):
    """What the documentation is asked, which is not what history is asked.

    History is searched for a matching incident; documentation is searched for
    the mechanism behind one - what a named file holds, what breaks when it is
    damaged, how the program recovers.
    """

    entities = state.get(
        "extracted_entities",
        {}
    )

    parts = [
        "REMAN program behaviour and failure handling",
        f"Affected system:\n{entities.get('service')}",
        f"Observed failure:\n{entities.get('symptom') or state['user_query']}"
    ]

    if entities.get("component"):
        parts.append(
            f"Programs, jobs or files involved:\n{entities['component']}"
        )

    parts.append(
        "Explain what the affected files and programs do, how this failure "
        "arises, and how it is recovered."
    )

    return "\n\n".join(parts)


def identifier_filter(identifiers):

    conditions = []

    if identifiers["programs"]:

        for field in ("program_id", "programs"):

            conditions.append(
                models.FieldCondition(
                    key=field,
                    match=models.MatchAny(any=identifiers["programs"])
                )
            )

    if identifiers["data_files"]:

        conditions.append(
            models.FieldCondition(
                key="data_files",
                match=models.MatchAny(any=identifiers["data_files"])
            )
        )

    if not conditions:
        return None

    return models.Filter(
        should=conditions
    )


def application_filter(applications):

    if not applications:
        return None

    return models.Filter(
        should=[
            models.FieldCondition(
                key="application",
                match=models.MatchAny(any=applications)
            )
        ]
    )


def to_document(point):

    payload = point.payload or {}

    document = {
        field: payload.get(field)
        for field in PAYLOAD_FIELDS
    }

    document["score"] = point.score

    return document


def reman_docs_retriever_node(state):

    print("\n--- REMAN Documentation Retriever ---")

    entities = state.get(
        "extracted_entities",
        {}
    )

    identifiers = extract_identifiers(
        state["user_query"],
        entities.get("component"),
        entities.get("symptom")
    )

    applications = infer_applications(
        state["user_query"],
        entities.get("service"),
        entities.get("symptom")
    )

    vector = create_embedding(
        build_search_query(state)
    )

    documents = []
    seen = set()

    def collect(points, cap=None):

        taken = 0

        for point in points:

            if cap is not None and taken >= cap:
                break

            document = to_document(point)

            if document["chunk_id"] in seen:
                continue

            seen.add(document["chunk_id"])
            documents.append(document)

            taken += 1

    # Exact identifier matches first - a named program or file is a fact.
    payload_filter = identifier_filter(
        identifiers
    )

    if payload_filter is not None:

        collect(
            search_with_retry(
                collection_name=COLLECTION_NAME,
                vector=vector,
                limit=RESULT_LIMIT,
                query_filter=payload_filter
            ).points,
            cap=PER_STRATEGY_LIMIT
        )

        print(
            f"Identifier matches for {identifiers}: {len(documents)}"
        )

    # Then the application, which is what most tickets actually name.
    scoped_filter = application_filter(
        applications
    )

    if scoped_filter is not None:

        collect(
            search_with_retry(
                collection_name=COLLECTION_NAME,
                vector=vector,
                limit=RESULT_LIMIT,
                query_filter=scoped_filter
            ).points,
            cap=PER_STRATEGY_LIMIT
        )

        print(
            f"Application matches for {applications}: {len(documents)}"
        )

    collect(
        search_with_retry(
            collection_name=COLLECTION_NAME,
            vector=vector,
            limit=RESULT_LIMIT
        ).points
    )

    documents = documents[:RESULT_LIMIT]

    print(
        f"Retrieved {len(documents)} documentation chunks"
    )

    return {
        "docs_identifiers": identifiers,
        "docs_applications": applications,
        "docs_results": documents
    }
