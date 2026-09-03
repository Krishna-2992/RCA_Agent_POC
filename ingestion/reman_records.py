"""Turns the three Reman workbook sheets into one normalised record shape.

Incidents, service requests and changes are all ServiceNow records and all end
up in the same collection, but they carry very different evidential weight:

  incident        - has an explicit Root Cause and Action Taken, buried in an
                    effort-tracking template that is ~88% of the note text
  service_request - written in end-user language, which is how people actually
                    describe a problem, but its work notes are mostly
                    acknowledgements rather than fixes
  change          - what was deliberately changed, and when

Keeping them in one collection with a record_type lets retrieval see all of it
while letting the evaluator weigh each kind appropriately.
"""

import re

import pandas as pd


WORKBOOK_PATH = "sample_data/Reman.xlsx"


# Both note templates in use: "3.3. Root Cause -" and "3.Root Cause -"
ROOT_CAUSE_RE = re.compile(
    r"Root\s*Cause\s*[-:]\s*(.+?)(?:\n|$)",
    re.I
)

ACTION_TAKEN_RE = re.compile(
    r"Action\s*Taken\s*[-:]?\s*(.+?)(?:\n|$)",
    re.I
)

SLA_RE = re.compile(
    r"SLA\s*(?:miss|\[Missed)[^\n]*?[-:]\s*([^\n]+)",
    re.I
)

# Mainframe abend and job-scheduler codes; strong retrieval signals.
ERROR_CODE_RE = re.compile(
    r"\b(?:S0C\d|U\d{4}|AJS\d+E|ABEND=\S+)\b",
    re.I
)

# COBOL program / job identifiers such as F8RH0251.
PROGRAM_RE = re.compile(
    r"\b(F\d[A-Z]{2}\d{4})\b",
    re.I
)

# "2026-07-07 12:59:40 - FNU Preeti (Work notes)" prefixing the actual text.
WORK_NOTE_PREFIX_RE = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}[^\n]*?\(Work notes\)\s*",
    re.I
)

# Catalog-item boilerplate that carries no information about the problem.
SR_BOILERPLATE_RE = re.compile(
    r"Request for catalog item[^\n]*",
    re.I
)

PLACEHOLDER_RE = re.compile(
    r"^(n/?a|none|nan|<[^>]*>|[-.\s]*)$",
    re.I
)

# Work notes that only acknowledge receipt tell us nothing about a resolution.
ACKNOWLEDGEMENT_RE = re.compile(
    r"^(ack|acknowledged\.?|will look into it|looking into it|assigned to\s+\w+|"
    r"\w+\s+\w+)$",
    re.I
)


def clean(value):

    if value is None:
        return ""

    text = str(value).strip()

    if PLACEHOLDER_RE.match(text):
        return ""

    return text


def first_match(pattern, text):

    match = pattern.search(text or "")

    if not match:
        return ""

    return clean(
        match.group(1).strip().strip("<>").strip()
    )


def find_all(pattern, *texts):

    found = []

    for text in texts:

        for item in pattern.findall(str(text or "")):

            item = item.upper()

            if item not in found:
                found.append(item)

    return found


def strip_work_note(value):
    """Drops the timestamp/author header ServiceNow prefixes work notes with."""

    text = clean(value)

    if not text:
        return ""

    return WORK_NOTE_PREFIX_RE.sub("", text).strip()


def is_substantive(text):
    """True when a resolution says what was done, not merely that it was seen."""

    if not text or len(text) < 12:
        return False

    return not ACKNOWLEDGEMENT_RE.match(text.strip())


def to_iso(value):

    if value is None or pd.isna(value):
        return ""

    try:
        return pd.to_datetime(value).isoformat()

    except Exception:
        return ""


def elapsed_hours(start, end):

    if start is None or end is None or pd.isna(start) or pd.isna(end):
        return None

    try:
        delta = pd.to_datetime(end) - pd.to_datetime(start)

    except Exception:
        return None

    return round(
        delta.total_seconds() / 3600.0,
        2
    )


def build_incident_record(row):

    short_description = clean(row.get("Short Description"))
    description = clean(row.get("Description"))
    resolution_text = clean(row.get("Resolution notes"))

    root_cause = first_match(ROOT_CAUSE_RE, resolution_text)
    action_taken = first_match(ACTION_TAKEN_RE, resolution_text)

    return {
        "ticket_id": clean(row.get("Number")),
        "record_type": "incident",
        "record_type_label": "ServiceNow Incident",
        "service": clean(row.get("Service")),
        "priority": clean(row.get("Priority")),
        "state": clean(row.get("State")),
        "channel": clean(row.get("Channel")),
        "short_description": short_description,
        "description": description,
        "root_cause": root_cause,
        "action_taken": action_taken,
        "resolution_text": resolution_text,
        "has_resolution": bool(root_cause or is_substantive(action_taken)),
        "sla_missed": first_match(SLA_RE, resolution_text),
        "parent_incident": clean(row.get("Parent Incident")),
        "assignment_group": clean(row.get("Assignment group")),
        "assigned_to": clean(row.get("Assigned to")),
        "caller": clean(row.get("Caller")),
        "opened_at": to_iso(row.get("Created")),
        "closed_at": to_iso(row.get("Resolved")),
        "resolution_hours": elapsed_hours(
            row.get("Created"),
            row.get("Resolved")
        ),
        "error_codes": find_all(
            ERROR_CODE_RE,
            short_description,
            description
        ),
        "programs": find_all(
            PROGRAM_RE,
            short_description,
            description,
            resolution_text
        )
    }


def build_service_request_record(row):

    short_description = clean(row.get("Short Description"))

    # Every SR short description is prefixed with its catalog item name.
    short_description = re.sub(
        r"^I Need Something\s*-\s*",
        "",
        short_description
    ).strip()

    description = SR_BOILERPLATE_RE.sub(
        "",
        clean(row.get("Description"))
    ).strip()

    action_taken = strip_work_note(row.get("Work notes"))

    return {
        "ticket_id": clean(row.get("Number")),
        "record_type": "service_request",
        "record_type_label": "ServiceNow Service Request",
        "service": clean(row.get("Service")),
        "priority": clean(row.get("Priority")),
        "state": clean(row.get("State")),
        "channel": "Self-service",
        "short_description": short_description,
        "description": description,
        "root_cause": "",
        "action_taken": action_taken,
        "resolution_text": action_taken,
        "has_resolution": is_substantive(action_taken),
        "sla_missed": "",
        "parent_incident": "",
        "assignment_group": clean(row.get("Assignment group")),
        "assigned_to": clean(row.get("Assigned to")),
        "caller": clean(row.get("Created by")),
        "opened_at": to_iso(row.get("Opened")),
        "closed_at": to_iso(row.get("Closed")),
        "resolution_hours": elapsed_hours(
            row.get("Opened"),
            row.get("Closed")
        ),
        "error_codes": find_all(
            ERROR_CODE_RE,
            short_description,
            description,
            action_taken
        ),
        "programs": find_all(
            PROGRAM_RE,
            short_description,
            description,
            action_taken
        )
    }


def build_change_record(row):

    short_description = clean(row.get("Short Description"))

    return {
        "ticket_id": clean(row.get("Number")),
        "record_type": "change",
        "record_type_label": "ServiceNow Change Request",
        "service": clean(row.get("Service")),
        "priority": clean(row.get("Risk")),
        "state": clean(row.get("State")),
        "channel": clean(row.get("Type")),
        "short_description": short_description,
        "description": "",
        "root_cause": "",
        # A change is itself the action: it records what was deliberately altered.
        "action_taken": short_description,
        "resolution_text": short_description,
        "has_resolution": bool(short_description),
        "sla_missed": "",
        "parent_incident": "",
        "assignment_group": clean(row.get("Assignment group")),
        "assigned_to": clean(row.get("Assigned to")),
        "caller": "",
        "opened_at": to_iso(row.get("Created")),
        "closed_at": to_iso(row.get("Actual end date")),
        "resolution_hours": elapsed_hours(
            row.get("Created"),
            row.get("Actual end date")
        ),
        "change_category": clean(row.get("Category")),
        "change_subcategory": clean(row.get("Subcategory")),
        "error_codes": [],
        "programs": find_all(
            PROGRAM_RE,
            short_description
        )
    }


SHEET_BUILDERS = {
    "INC": build_incident_record,
    "SR": build_service_request_record,
    "CR": build_change_record
}


def load_records(workbook_path=WORKBOOK_PATH):
    """Every row of every sheet, normalised to one shape."""

    records = []

    for sheet, builder in SHEET_BUILDERS.items():

        frame = pd.read_excel(
            workbook_path,
            sheet_name=sheet
        )

        for _, row in frame.iterrows():

            record = builder(row)

            if not record["ticket_id"]:
                continue

            record["source_title"] = (
                f"{record['record_type_label']} {record['ticket_id']}"
            )

            record["source_location"] = (
                f"ServiceNow {record['record_type_label'].split()[-1].lower()} "
                f"{record['ticket_id']}"
            )

            record["source_type_label"] = record["record_type_label"]

            records.append(record)

    return records


def join_lines(*parts):

    return "\n".join(
        part
        for part in parts
        if part
    )


def build_embedding_text(record, variant="symptom_cause"):
    """The text that gets embedded, i.e. what similarity search matches on.

    Variants exist because the right answer is not obvious and was settled by
    measurement, not intuition - see the A/B in the ingestion script. The stored
    resolution notes are ~88% effort-tracking template, so none of the variants
    embed them raw; the extracted root cause and action are used instead.
    """

    header = join_lines(
        f"{record['record_type_label']}",
        f"Affected Service:\n{record['service']}" if record["service"] else "",
        f"Reported Problem:\n{record['short_description']}"
        if record["short_description"] else "",
        f"Details:\n{record['description']}" if record["description"] else ""
    )

    if variant == "symptom":
        return header

    signals = ""

    if variant == "symptom_signals_cause":

        signals = join_lines(
            f"Error Codes:\n{', '.join(record['error_codes'])}"
            if record["error_codes"] else "",
            f"Programs and Jobs:\n{', '.join(record['programs'])}"
            if record["programs"] else ""
        )

    cause = join_lines(
        f"Root Cause:\n{record['root_cause']}" if record["root_cause"] else "",
        f"Action Taken:\n{record['action_taken']}"
        if record["action_taken"] else ""
    )

    return join_lines(header, signals, cause)
