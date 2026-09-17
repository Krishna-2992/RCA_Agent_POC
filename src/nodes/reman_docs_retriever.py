"""Retrieves REMAN documentation explaining the mechanism behind an incident.

Supplementary by design, and the code treats it that way: a search that cannot
reach Qdrant degrades to "documentation unavailable" and lets the analysis
proceed on ticket history alone. An earlier version raised instead, and a
half-minute of local DNS trouble failed an entire investigation that already
had eight matching incident records in hand. A supporting source must not be
able to take down the primary one.

Search is hybrid for the same reason the incident retriever is, only more so.
Measured against the embedding model in use, IN001.MST scores 0.876 against
IN0056.MST - a different file - and 0.828 against IN0001.MST, the same file.
Similarity is blind to identifiers, so programs and data files are matched by
payload filter and similarity is used only for the prose around them.
"""

import os
import re

from qdrant_client import models

from ingestion.reman_docs import DATA_FILE_RE, find_data_files

from src.domain.reman_digest import (
    needs_recovery_context,
    recovery_applications
)

from src.nodes.incident_evidence import document_role

from src.nodes.reman_docs_rerank import (
    CANDIDATE_MULTIPLIER,
    diversity_report,
    select_diverse
)

from src.utils.incident_search import search_with_retry
from src.utils.llm import create_embedding
from src.utils.qdrant_client import qdrant_client


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


# Slots reserved for procedural documentation on a remedy question. Two, not
# more: the procedure is worth a third of the window and no more than that,
# because a step still has to be justified by what the records show happened.
PROCEDURE_SLOTS = int(
    os.getenv("REMAN_DOCS_PROCEDURE_SLOTS", "2")
)


# Words that make a report a request for a remedy rather than an explanation.
# Deliberately a word list and not a model call: it runs on every incident, the
# vocabulary is small and stable, and a wrong answer only costs two slots.
REMEDY_MARKERS = (
    "recover", "recovery", "repair", "fix", "restore", "rebuild",
    "what do i do", "what should i do", "what i need to do", "how do i",
    "how to", "steps", "resolve", "unlock", "clear the lock"
)


def wants_remedy(state):
    """Whether the reporter is asking how to put this right."""

    entities = state.get("extracted_entities") or {}

    haystack = " ".join(
        str(value)
        for value in (
            state.get("user_query"),
            state.get("rewritten_query"),
            entities.get("symptom")
        )
        if value
    ).lower()

    return any(
        marker in haystack
        for marker in REMEDY_MARKERS
    )


PROGRAM_RE = re.compile(
    r"\b(F\d[A-Z]{2}\d{4})\b",
    re.I
)


# Report names are identifiers, and similarity is as blind to them as it is to
# file names. 04RH0442 produces seventy-five numbered reports and its
# documentation runs to 3,167 chunks; the twenty-nine that name reports 068 and
# 069 lose on cosine distance to three thousand siblings written in the same
# vocabulary, so an incident reporting garbage data in MISCRPT068 retrieved a
# window with nothing about MISCRPT068 in it. The same conclusion the corpus
# already reached for IN0011.MST applies here: filter, do not embed.
REPORT_RE = re.compile(
    r"\b(?:MISCRPT|RPT)[\s-]?(\d{2,3})\b",
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


_KNOWN_FILES = None

FILE_NAME_RE = re.compile(
    r"^([A-Z]{2})(\d+)\.([A-Z]{3})$"
)


def known_data_files():
    """The data files the corpus actually contains, read once and cached.

    Used to resolve ticket typos against reality instead of guessing. Falls
    back to an empty vocabulary if Qdrant cannot be reached, which degrades
    candidate expansion to plain zero-padding rather than failing.
    """

    global _KNOWN_FILES

    if _KNOWN_FILES is not None:
        return _KNOWN_FILES

    names = set()

    try:
        offset = None

        while True:

            records, offset = qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                limit=500,
                with_payload=["data_files"],
                offset=offset
            )

            for record in records:
                names.update(record.payload.get("data_files") or [])

            if offset is None:
                break

    except Exception as error:

        print(
            f"  could not load the data-file vocabulary: "
            f"{type(error).__name__}: {error}"
        )

    _KNOWN_FILES = names

    return _KNOWN_FILES


def is_subsequence(shorter, longer):

    iterator = iter(longer)

    return all(
        character in iterator
        for character in shorter
    )


def expand_file_candidates(names):
    """Resolves a ticket's filename against the files that actually exist.

    Zero-padding alone gets this wrong, and the failure is silent. Eight
    incidents describe one LMS outage; five name IN0011.MST, the Location File,
    and three name IN001.MST. Padding turns IN001 into IN0001 - the Inventory
    Master, a different file entirely - so the filter would narrow to
    documentation about the wrong data.

    A dropped digit and a missing leading zero are indistinguishable from the
    string alone, so no single answer is guessable. Every known file the ticket
    text could denote is returned instead, and the evaluator resolves it from
    context.
    """

    vocabulary = known_data_files()

    if not vocabulary:
        return names

    resolved = []

    for name in names:

        match = FILE_NAME_RE.match(name)

        if not match:
            resolved.append(name)
            continue

        prefix, digits, extension = match.groups()

        candidates = []

        for candidate in sorted(vocabulary):

            other = FILE_NAME_RE.match(candidate)

            if not other:
                continue

            other_prefix, other_digits, other_extension = other.groups()

            if other_prefix != prefix:
                continue

            same_extension = other_extension == extension

            # Tickets also mistype the extension: the workbook contains
            # IN0015.MOR and IN0018.MOL where the corpus has .MOV. One
            # character apart, with the digits matching exactly, is a typo
            # rather than a different file.
            near_extension = (
                len(other_extension) == len(extension)
                and sum(
                    1
                    for a, b in zip(other_extension, extension)
                    if a != b
                ) == 1
            )

            same_digits = other_digits == digits

            near_digits = (
                abs(len(other_digits) - len(digits)) <= 1
                and is_subsequence(digits, other_digits)
            )

            if same_extension and (same_digits or near_digits):
                candidates.append(candidate)

            elif near_extension and same_digits:
                candidates.append(candidate)

        resolved.extend(candidates or [name])

    return sorted(set(resolved))


def extract_identifiers(*texts):
    """Programs and data files named anywhere in the incident.

    Data files go through the ingester's own normaliser first, so index-time
    and query-time agree on the canonical form, and are then widened to every
    known file the ticket text could denote - see expand_file_candidates for
    why one answer cannot be guessed.
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

    # Expansion has to see the text as the ticket wrote it. find_data_files
    # pads IN001 to IN0001 first, which is one of the two readings and hides
    # the other, so the raw spelling is what gets resolved against the corpus.
    raw = sorted(
        {
            f"{prefix.upper()}{digits}.{extension.upper()}"
            for prefix, digits, extension in DATA_FILE_RE.findall(blob)
        }
    )

    # Both spellings are kept: the ticket says MISCRPT068 and the documentation
    # says RPT068 for the same report, and a full-text match needs the token as
    # it is written.
    reports = []

    for number in REPORT_RE.findall(blob):

        for form in (f"MISCRPT{number}", f"RPT{number}"):

            if form not in reports:
                reports.append(form)

    return {
        "programs": programs,
        "data_files": expand_file_candidates(raw) or find_data_files(blob),
        "reports": reports
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


def widen_for_recovery(state, applications):
    """Adds the programs that own a recovery procedure to a recovery report.

    The file that breaks and the screen that repairs it are not in the same
    program. IN0018.MOV belongs to Inventory, but an operator recovers it from
    the Reman Index menu - Option 34, 6200-FILE-RECOVERY, security level 4,
    RECOVER1.EXE. Scoping such a report to the application the ticket names
    therefore filters the answer out before ranking begins.

    Measured on the two file-corruption incidents in the held-out set: with the
    reporter's application alone, the chunk naming Option 34 does not appear in
    the window at all and the analysis falls back to "the precise recovery
    method is not present in the retrieved evidence". With the recovery owners
    admitted, the same chunk is selected at rank two - the procedure reservation
    that already exists promotes it once it is allowed to compete.

    Deliberately narrow. It widens only on a corruption, lock or duplicate-open
    symptom, and only to programs whose digest entry actually documents a
    recovery. A report about a report printing wrong widens to nothing.
    """

    entities = state.get("extracted_entities") or {}

    haystack = " ".join(
        str(value)
        for value in (
            state.get("user_query"),
            state.get("rewritten_query"),
            entities.get("symptom"),
            entities.get("error_code")
        )
        if value
    )

    if not needs_recovery_context(haystack):
        return applications

    widened = list(applications)

    for name in recovery_applications():

        if name not in widened:
            widened.append(name)

    return widened


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


def documentation_query(state):
    """The rewritten incident where one exists, the assembled one otherwise.

    The rewrite is preferred outright rather than blended. Measured on the same
    corpus, the assembled query returns eleven estate-catalogue one-liners in
    its top twelve and nothing about the recovery screen; the rewrite returns no
    catalogue entries at all and puts the recovery section first. Mixing them
    would reintroduce the vague half of the difference.

    The fallback matters anyway: the rewriter is skipped when the analyser stops
    a contentless report, and a resumed or replayed state may not carry one.
    """

    rewritten = state.get("rewritten_query")

    if rewritten:
        return rewritten

    return build_search_query(state)


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

    # Matched against the chunk text rather than a payload field, because the
    # corpus was not indexed with a report list and re-embedding 8,247 chunks to
    # add one would cost hours for a field a full-text index supplies in
    # seconds. Needs the text index on `content`; without it Qdrant rejects the
    # condition, which is why the caller treats a failed strategy as recoverable.
    for report in identifiers.get("reports") or []:

        conditions.append(
            models.FieldCondition(
                key="content",
                match=models.MatchText(text=report)
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

    # Carried only as far as re-ranking, which needs it to measure how much a
    # candidate repeats the ones already chosen. Stripped before the document
    # reaches the evaluator, which has no use for 1,536 floats.
    document["vector"] = point.vector

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

    # The rewriter resolved these against the digest - real file names, real
    # application names - so its answers are added rather than re-derived. They
    # are merged with what the raw text yields instead of replacing it: the
    # rewrite can only name files the digest knows, and a ticket occasionally
    # names one the documentation never described.
    for name in state.get("rewrite_data_files") or []:

        if name not in identifiers["data_files"]:
            identifiers["data_files"].append(name)

    applications = infer_applications(
        state["user_query"],
        entities.get("service"),
        entities.get("symptom")
    )

    for name in state.get("rewrite_applications") or []:

        if name not in applications:
            applications.append(name)

    # A corruption or lock report is answered by the program that owns the
    # recovery screen, which is usually not the program the ticket names.
    before = list(applications)

    applications = widen_for_recovery(state, applications)

    if applications != before:

        print(
            f"  widened for recovery: {before} -> {applications}"
        )

    try:
        vector = create_embedding(
            documentation_query(state)
        )

    except Exception as error:

        print(
            f"  documentation unavailable, embedding failed: "
            f"{type(error).__name__}: {error}"
        )

        return {
            "docs_identifiers": identifiers,
            "docs_applications": applications,
            "docs_results": [],
            "docs_unavailable": True
        }

    documents = []
    seen = set()
    failures = []

    def attempt(label, **kwargs):
        """Runs one search strategy, surviving its failure.

        search_with_retry already rides out brief network trouble; what reaches
        here is a sustained outage. Losing one strategy costs some recall,
        losing all of them costs the documentation stage - neither is worth
        losing the investigation over.
        """

        try:
            return search_with_retry(
                collection_name=COLLECTION_NAME,
                vector=vector,
                limit=RESULT_LIMIT * CANDIDATE_MULTIPLIER,
                with_vectors=True,
                **kwargs
            ).points

        except Exception as error:

            failures.append(label)

            print(
                f"  {label} search unavailable: "
                f"{type(error).__name__}: {error}"
            )

            return []

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

    # The per-strategy caps now bound a candidate pool rather than the result
    # set, so they are multiplied by the same factor as the searches. The final
    # cut is MMR's, and it needs more than RESULT_LIMIT candidates to have any
    # choice to make.
    candidate_cap = PER_STRATEGY_LIMIT * CANDIDATE_MULTIPLIER

    # Exact identifier matches first - a named program or file is a fact.
    payload_filter = identifier_filter(
        identifiers
    )

    pinned = 0

    if payload_filter is not None:

        collect(
            attempt("identifier", query_filter=payload_filter),
            cap=candidate_cap
        )

        # Only the strongest few are pinned. All of them would be the old
        # crowding fault under a new name: the identifier pass returns
        # background documents that merely mention the file alongside the one
        # that explains it.
        pinned = min(
            len(documents),
            PER_STRATEGY_LIMIT
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
            attempt("application", query_filter=scoped_filter),
            cap=candidate_cap
        )

        print(
            f"Application matches for {applications}: {len(documents)}"
        )

    collect(
        attempt("semantic")
    )

    # Identifier matches are pinned ahead of diversification: a chunk carrying
    # a file or program the report actually named earned its slot on a fact,
    # not on resembling the query, and MMR has no way to know that.
    # Slots held for procedural extracts when the reporter is asking how to put
    # something right. Relevance alone does not reserve them: descriptions of
    # what a program does outrank and outnumber descriptions of what an operator
    # presses, so the window filled with the former and the resolution steps
    # came out as "recover the file using the approved procedure".
    reserve = (
        PROCEDURE_SLOTS
        if wants_remedy(state)
        else 0
    )

    documents = select_diverse(
        documents,
        RESULT_LIMIT,
        pinned=min(pinned, RESULT_LIMIT),
        reserve_for=lambda document: document_role(document) == "procedure",
        reserve_count=reserve
    )

    spread = diversity_report(documents)

    print(
        f"  selection: {spread['duplicate_pairs']} duplicate pairs, "
        f"worst section share {spread['worst_section_share']}, "
        f"mean similarity {spread['mean_similarity']:.3f}"
    )

    for document in documents:
        document.pop("vector", None)

    print(
        f"Retrieved {len(documents)} documentation chunks"
    )

    unavailable = bool(failures) and not documents

    if unavailable:
        print(
            "Documentation unavailable; continuing on ticket history alone."
        )

    return {
        "docs_identifiers": identifiers,
        "docs_applications": applications,
        "docs_results": documents,
        "docs_unavailable": unavailable
    }
