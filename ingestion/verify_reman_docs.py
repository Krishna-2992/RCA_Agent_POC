"""Checks that the ingested reman_docs collection is actually usable.

Ingestion reporting a point count proves only that rows landed. What matters is
whether the two access paths the retriever will depend on both work: filtering
on an exact identifier, and similarity search on prose. This asserts both, plus
the filename normalisation that lets a ticket's "IN001.MST" reach a document's
"IN0001.MST".

Run:  python -m ingestion.verify_reman_docs
"""

import os
import sys

from dotenv import load_dotenv

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue
)

from ingestion.reman_docs import find_data_files

from src.utils.llm import create_embedding
from src.utils.qdrant_client import qdrant_client


load_dotenv()


COLLECTION_NAME = os.getenv(
    "REMAN_DOCS_COLLECTION",
    "reman_docs"
)


def count_where(field, value):

    result = qdrant_client.count(
        collection_name=COLLECTION_NAME,
        count_filter=Filter(
            must=[
                FieldCondition(
                    key=field,
                    match=MatchValue(value=value)
                )
            ]
        )
    )

    return result.count


def check_counts():

    total = qdrant_client.get_collection(
        COLLECTION_NAME
    ).points_count

    print(f"points in '{COLLECTION_NAME}': {total:,}\n")

    print("by source_type")

    for source_type in [
        "technical_xml",
        "program_summary_docx",
        "program_overview",
        "business_rule",
        "estate_catalogue",
        "general_doc"
    ]:
        print(f"  {source_type:<24}{count_where('source_type', source_type):>6,}")

    print("\nby application")

    for application in [
        "Reman Index",
        "Inventory",
        "LMS",
        "Inventory Detail",
        "BOM",
        "REMAN estate"
    ]:
        print(f"  {application:<24}{count_where('application', application):>6,}")

    return total


def check_identifier_filter():
    """A ticket names F8RH0093; the filter must return only that program."""

    print("\nidentifier filter")

    ok = True

    for program_id, expected_program in [
        ("F8RH0071", "01RMNIDX"),
        ("F8RH0093", "03RMNLMS"),
        ("F8RH0101", "06RH0101")
    ]:

        records, _ = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="program_id",
                        match=MatchValue(value=program_id)
                    )
                ]
            ),
            limit=5,
            with_payload=True
        )

        programs = {
            record.payload["program"]
            for record in records
        }

        passed = programs == {expected_program}
        ok = ok and passed

        print(
            f"  {program_id} -> {sorted(programs) or '(none)'}"
            f"  {'ok' if passed else 'FAILED'}"
        )

    return ok


def check_data_file_filter():
    """The corruption case: a ticket's IN001.MST must reach IN0001.MST."""

    print("\ndata-file filter (the normalisation that carries the corruption case)")

    ticket_text = "IN001.MST file was corrupt"

    wanted = find_data_files(ticket_text)

    print(f"  ticket says 'IN001.MST' -> normalised to {wanted}")

    records, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="data_files",
                    match=MatchAny(any=wanted)
                )
            ]
        ),
        limit=5,
        with_payload=True
    )

    print(f"  matched {len(records)} chunk(s)")

    for record in records[:3]:
        print(
            f"    {record.payload['program']} / "
            f"{record.payload['source_type']} / "
            f"{record.payload['section'][:44]}"
        )

    return len(records) > 0


def check_semantic_search():
    """Prose search, which is what vectors are actually good at."""

    print("\nsemantic search")

    queries = [
        "how is a corrupted file recovered or repaired",
        "what happens when two users write to the same file at once",
        "user cannot sign on, security access denied"
    ]

    ok = True

    for query in queries:

        response = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=create_embedding(query),
            limit=3,
            with_payload=True
        )

        print(f"\n  {query}")

        if not response.points:
            ok = False
            print("    (no results)")

        for point in response.points:
            print(
                f"    {point.score:.3f}  "
                f"{point.payload['program']:<11}"
                f"{point.payload['source_type']:<22}"
                f"{point.payload['section'][:38]}"
            )

    return ok


def verify():

    total = check_counts()

    results = {
        "point count > 0": total > 0,
        "identifier filter": check_identifier_filter(),
        "data-file filter": check_data_file_filter(),
        "semantic search": check_semantic_search()
    }

    print("\n" + "-" * 52)

    for name, passed in results.items():
        print(f"  {name:<24}{'PASS' if passed else 'FAIL'}")

    return all(results.values())


if __name__ == "__main__":

    sys.exit(
        0 if verify() else 1
    )
