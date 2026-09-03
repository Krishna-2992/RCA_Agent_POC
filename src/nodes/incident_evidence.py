"""Turns matched ServiceNow records into a cited evidence catalogue.

Two signals are computed here rather than asked of a model, because both are
counting exercises and a model would only guess at them:

  recurrence      - how often this failure has already been seen. On this data
                    one cause accounts for 21 incidents, which is the single
                    most useful thing to tell a support engineer.
  related changes - change records touching a program or job named in the
                    matched records. This is a narrow signal: it fires for one
                    program in the current workbook, so it is reported as a
                    possible link, never as a cause.
"""

import re
from collections import Counter


STOPWORDS = {
    "the", "was", "were", "and", "for", "with", "from", "that", "this", "job",
    "file", "issue", "error", "because", "of", "due", "to", "in", "is", "are",
    "not", "it", "we", "a", "an", "on", "at", "by", "as", "has", "had", "been"
}


def cause_signature(text):
    """A crude key for 'the same cause', used only to count repeats.

    Deliberately simple: these notes are free text written by several engineers,
    so exact matching would undercount and anything cleverer would overreach.
    """

    words = re.findall(
        r"[a-z0-9.]+",
        (text or "").lower()
    )

    keywords = sorted(
        {
            word
            for word in words
            if word not in STOPWORDS and len(word) > 2
        }
    )

    return " ".join(keywords[:6])


def build_record_evidence(record):

    evidence_id = f"sn::{record['ticket_id']}"

    sections = [
        f"Reported Problem:\n{record.get('short_description') or 'Not Available'}"
    ]

    if record.get("description"):
        sections.append(
            f"Details:\n{record['description']}"
        )

    if record.get("root_cause"):
        sections.append(
            f"Root Cause:\n{record['root_cause']}"
        )

    if record.get("action_taken"):
        sections.append(
            f"Action Taken:\n{record['action_taken']}"
        )

    metadata = {
        "title": record.get("source_title")
        or f"{record.get('record_type_label')} {record['ticket_id']}",
        "location": record.get("source_location")
        or f"ServiceNow {record['ticket_id']}",
        "source_type_label": record.get("record_type_label")
        or "ServiceNow Record",
        "ticket_id": record.get("ticket_id"),
        "record_type": record.get("record_type"),
        "service": record.get("service"),
        "priority": record.get("priority"),
        "state": record.get("state"),
        "opened_at": record.get("opened_at"),
        "closed_at": record.get("closed_at"),
        "resolution_hours": record.get("resolution_hours"),
        "root_cause": record.get("root_cause"),
        "action_taken": record.get("action_taken"),
        "error_codes": record.get("error_codes"),
        "programs": record.get("programs"),
        "assignment_group": record.get("assignment_group"),
        "excerpt": record.get("short_description")
    }

    return {
        "evidence_id": evidence_id,
        "source_type": record.get("record_type") or "servicenow",
        "source_id": record["ticket_id"],
        "confidence": record.get("score") or 0.0,
        "content": "\n\n".join(sections),
        "metadata": metadata
    }


def summarise_recurrence(records):
    """How often the matched cause has already been seen, and over what period."""

    with_cause = [
        record
        for record in records
        if record.get("root_cause")
    ]

    if not with_cause:
        return {
            "repeat_count": 0,
            "dominant_cause": None,
            "tickets": [],
            "first_seen": None,
            "last_seen": None
        }

    signatures = Counter(
        cause_signature(record["root_cause"])
        for record in with_cause
    )

    dominant, count = signatures.most_common(1)[0]

    members = [
        record
        for record in with_cause
        if cause_signature(record["root_cause"]) == dominant
    ]

    dates = sorted(
        record.get("opened_at")
        for record in members
        if record.get("opened_at")
    )

    return {
        "repeat_count": count,
        "dominant_cause": members[0]["root_cause"],
        "tickets": [record["ticket_id"] for record in members],
        "first_seen": dates[0] if dates else None,
        "last_seen": dates[-1] if dates else None
    }


def find_related_changes(matched, all_records):
    """Change records touching a program or job named in the matched records."""

    programs = {
        program
        for record in matched
        for program in (record.get("programs") or [])
    }

    if not programs:
        return []

    related = []

    for record in all_records:

        if record.get("record_type") != "change":
            continue

        shared = programs.intersection(
            record.get("programs") or []
        )

        if not shared:
            continue

        related.append(
            {
                "ticket_id": record["ticket_id"],
                "summary": record.get("short_description"),
                "programs": sorted(shared),
                "opened_at": record.get("opened_at"),
                "closed_at": record.get("closed_at")
            }
        )

    return related


def incident_evidence_node(state):

    print("\n--- Evidence Aggregator ---")

    records = state.get(
        "servicenow_results",
        []
    )

    matching_ids = set(
        state.get("matching_records", [])
    )

    matched = [
        record
        for record in records
        if record.get("ticket_id") in matching_ids
    ]

    evidence = []
    evidence_catalog = {}

    for record in matched:

        item = build_record_evidence(
            record
        )

        if item["evidence_id"] in evidence_catalog:
            continue

        evidence.append(item)
        evidence_catalog[item["evidence_id"]] = item

    recurrence = summarise_recurrence(
        matched
    )

    related_changes = find_related_changes(
        matched,
        records
    )

    print(
        f"Prepared {len(evidence)} evidence items | "
        f"recurrence={recurrence['repeat_count']} | "
        f"related changes={len(related_changes)}"
    )

    return {
        "combined_evidence": evidence,
        "evidence_catalog": evidence_catalog,
        "recurrence": recurrence,
        "related_changes": related_changes
    }
