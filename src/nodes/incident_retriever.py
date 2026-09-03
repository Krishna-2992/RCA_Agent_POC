"""Retrieves ServiceNow records for an incident description.

Search is hybrid on purpose. Embeddings are good at "inventory master file is
corrupted" and bad at "program F8RH0251" - measured on this data, a semantic
search for that program returned five records none of which mention it, while a
keyword filter returned exactly the two that do. So when the caller names an
error code, job or program, those records are pulled deterministically and the
semantic hits are used to fill out the rest.
"""

import os
import re

from qdrant_client import models

from src.utils.llm import create_embedding
from src.utils.incident_search import search_with_retry


COLLECTION_NAME = os.getenv(
    "REMAN_COLLECTION",
    "reman_incidents"
)


RESULT_LIMIT = int(
    os.getenv("REMAN_RESULT_LIMIT", "8")
)


ERROR_CODE_RE = re.compile(
    r"\b(?:S0C\d|U\d{4}|AJS\d+E)\b",
    re.I
)

PROGRAM_RE = re.compile(
    r"\b(F\d[A-Z]{2}\d{4})\b",
    re.I
)

TICKET_RE = re.compile(
    r"\b((?:INC|SCTASK|CHG|PRB)\d+)\b",
    re.I
)


PAYLOAD_FIELDS = [
    "ticket_id",
    "record_type",
    "record_type_label",
    "service",
    "priority",
    "state",
    "channel",
    "short_description",
    "description",
    "root_cause",
    "action_taken",
    "has_resolution",
    "parent_incident",
    "opened_at",
    "closed_at",
    "resolution_hours",
    "error_codes",
    "programs",
    "assignment_group",
    "assigned_to",
    "content",
    "source_title",
    "source_location",
    "source_type_label"
]


def extract_identifiers(*texts):
    """Error codes, programs and ticket numbers mentioned anywhere in the input."""

    blob = " ".join(
        str(text or "")
        for text in texts
    )

    def unique_upper(pattern):

        found = []

        for item in pattern.findall(blob):

            item = item.upper()

            if item not in found:
                found.append(item)

        return found

    return {
        "error_codes": unique_upper(ERROR_CODE_RE),
        "programs": unique_upper(PROGRAM_RE),
        "tickets": unique_upper(TICKET_RE)
    }


def build_search_query(state):

    entities = state.get(
        "extracted_entities",
        {}
    )

    parts = [
        "Production Incident Record",
        f"Affected Service:\n{entities.get('service')}",
        f"Reported Problem:\n{entities.get('symptom') or state['user_query']}"
    ]

    if entities.get("error_code"):
        parts.append(
            f"Error Codes:\n{entities['error_code']}"
        )

    if entities.get("component"):
        parts.append(
            f"Programs and Jobs:\n{entities['component']}"
        )

    return "\n\n".join(parts)


def identifier_filter(identifiers):

    conditions = []

    for field, key in [
        ("error_codes", "error_codes"),
        ("programs", "programs"),
        ("ticket_id", "tickets")
    ]:

        values = identifiers.get(key) or []

        if values:
            conditions.append(
                models.FieldCondition(
                    key=field,
                    match=models.MatchAny(any=values)
                )
            )

    if not conditions:
        return None

    return models.Filter(
        should=conditions
    )


def to_record(point):

    payload = point.payload or {}

    record = {
        field: payload.get(field)
        for field in PAYLOAD_FIELDS
    }

    record["score"] = point.score

    return record


def incident_retriever_node(state):

    print("\n--- ServiceNow Record Retriever ---")

    entities = state.get(
        "extracted_entities",
        {}
    )

    identifiers = extract_identifiers(
        state["user_query"],
        entities.get("error_code"),
        entities.get("component")
    )

    vector = create_embedding(
        build_search_query(state)
    )

    records = []
    seen = set()

    def collect(points):

        for point in points:

            record = to_record(point)

            if record["ticket_id"] in seen:
                continue

            seen.add(record["ticket_id"])
            records.append(record)

    # Exact identifier matches first - they are facts, not similarities.
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
            ).points
        )

        print(
            f"Identifier matches for {identifiers}: {len(records)}"
        )

    collect(
        search_with_retry(
            collection_name=COLLECTION_NAME,
            vector=vector,
            limit=RESULT_LIMIT
        ).points
    )

    records = records[:RESULT_LIMIT]

    print(
        f"Retrieved {len(records)} ServiceNow records"
    )

    return {
        "search_identifiers": identifiers,
        "servicenow_results": records
    }
