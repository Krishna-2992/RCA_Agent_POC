"""Turns the SharePoint AWS Transform export into one normalised chunk shape.

The export is five overlapping views of the same six COBOL programs, in four
formats, roughly half of it duplicated. What survives here was settled by
measurement rather than taste - a BM25 harness over sixteen queries drawn from
real incident root causes and from the Reman support team's own description of
how they investigate:

    everything, no business rules          MRR 0.849
    business rules from 01/02/03 only      MRR 0.875   recall 94%
    04RH0442 kept as background context    MRR 0.953
    04RH0442 dropped entirely              MRR 0.953   <- same score, 229 fewer chunks
    05RHE247 rules unfiltered              MRR 0.919
    every rule from every program          MRR 0.906   recall 94%

So: keep the rules (dropping them costs 0.10 MRR), drop 04RH0442 outright (it
is a standalone batch reporter with no call relationship to any supported
application, and removing it changed nothing), and thin 05RHE247's rules to the
four decision-shaped types.

The support team supports three applications - Reman Index, Inventory and LMS.
06RH0101 is kept because all three call it, and 05RHE247 because it sits inside
the Inventory and LMS call graph.

Excluded entirely: every .html file (Cloudscape renderings of the JSON, 152MB of
duplication), every .pdf that mirrors an .xml or .json, Summary/BusinessDetails/
(a second generation run that contradicts the one kept - only ~10% of rule names
overlap), the Claude/Copilot comparison exports, and the two screenshots.

Provenance
----------
The documents are AWS Transform output over the REMAN COBOL source, generated in
March 2026 (six programs, CAT-Reman.zip) and April 2026 (the ~1000-program
estate sweep, RemanCode.zip). They live in Teams under

    Caterpillar Delivery
      > AMS AWS Transform Documentation
        > Documents > Reman

and are copied to DOC_ROOT by hand. They are deliberately not in git - see
.gitignore - so a fresh checkout needs that copy before this module will run.
An earlier Microsoft Graph downloader was dropped: the delegated token needed
scopes the tenant would not grant to Graph Explorer, and a one-off manual copy
of a folder that changes rarely is simpler than maintaining an auth path for it.
"""

import glob
import json
import os
import re
import zipfile

import xml.etree.ElementTree as ET

from pypdf import PdfReader


DOC_ROOT = "sharepoint_docs/Reman/AWSTransform_Documentation"


# Word stores paragraphs under this namespace; there is no lighter way in.
DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# Chunk size was validated at this value. Prose is packed on paragraph
# boundaries and rules on rule boundaries, so nothing is split mid-sentence and
# no overlap is needed to keep a thought intact.
MAX_CHUNK_CHARS = 3500


# The legacy identifier is what incidents actually cite - a ticket says
# "F8RH0093", never "03RMNLMS".
LEGACY_ID = {
    "01RMNIDX": "F8RH0071",
    "02RMNINVTR": "F8RH0030",
    "03RMNLMS": "F8RH0093",
    "05RHE247": "F8RHE247",
    "06RH0101": "F8RH0101"
}


APPLICATION = {
    "01RMNIDX": "Reman Index",
    "02RMNINVTR": "Inventory",
    "03RMNLMS": "LMS",
    "05RHE247": "Inventory Detail",
    "06RH0101": "BOM"
}


# "all" keeps every rule; "filter" keeps only the decision-shaped types.
# 01/02/03 use a flat "Business Process" taxonomy, so a type filter would
# silently reduce them to nothing - which is exactly what an earlier draft did.
RULE_STRATEGY = {
    "01RMNIDX": "all",
    "02RMNINVTR": "all",
    "03RMNLMS": "all",
    "05RHE247": "filter",
    "06RH0101": "all"
}


KEEP_RULE_TYPES = {
    "Validation Rules",
    "Decision Rules",
    "Authorization Rules",
    "Policy Rules"
}


# Data files appear as IN0001.MST in the documentation but as IN001.MST in
# tickets typed under time pressure. Both are captured and zero-padded to a
# single canonical form; see normalise_data_file.
DATA_FILE_RE = re.compile(
    r"\b(IN|LM|BM)(\d{2,4})\.([A-Z]{3})\b",
    re.I
)


PROGRAM_RE = re.compile(
    r"\b(F\d[A-Z]{2}\d{4})\b",
    re.I
)


# A numbered heading such as "6.6Error Handling and Recovery25" - Word drops the
# space between number and title. Two letters are required after the number so
# that a table cell like "1K-2K" is not mistaken for a section heading.
HEADING_RE = re.compile(
    r"^\d+(?:\.\d+)*\s*[A-Z][A-Za-z]"
)


# One entry of the estate catalogue: a program file followed by its one-line
# summary, running until the next entry begins.
CATALOGUE_ENTRY_RE = re.compile(
    r"(F8RH[A-Z0-9]{3,5})\.(?:CBL|txt)\s+(.{40,400}?)(?=LAN COBOL|$)",
    re.I
)


def normalise_data_file(prefix, digits, extension):
    """Collapses IN001.MST and IN0001.MST onto one key.

    Vectors cannot do this. Measured against the embedding model actually in
    use, IN001.MST scores 0.876 against IN0056.MST - a different file - and only
    0.828 against IN0001.MST, which is the same file. Similarity search is blind
    to identifiers, so they are carried as filterable payload instead.
    """

    return f"{prefix.upper()}{int(digits):04d}.{extension.upper()}"


def find_data_files(text):

    return sorted(
        {
            normalise_data_file(prefix, digits, extension)
            for prefix, digits, extension in DATA_FILE_RE.findall(text)
        }
    )


def find_programs(text):

    return sorted(
        {
            match.upper()
            for match in PROGRAM_RE.findall(text)
        }
    )


def clean(text):

    if not text:
        return ""

    text = text.replace("\r", "\n")

    # Collapse the blank-line runs that CDATA blocks and Word both leave behind.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def pack(pieces, meta, section):
    """Groups already-atomic pieces into chunks without splitting one in half.

    A piece is a paragraph or a single business rule. Packing on those
    boundaries is why no overlap is configured: a chunk never ends mid-thought.
    """

    chunks = []
    buffer = []
    size = 0

    def flush():

        if not buffer:
            return

        text = clean("\n".join(buffer))

        if len(text) < 60:
            return

        chunks.append(
            build_chunk(text, meta, section, len(chunks))
        )

    for piece in pieces:

        piece = piece.strip()

        if not piece:
            continue

        if size + len(piece) > MAX_CHUNK_CHARS and buffer:
            flush()
            buffer = []
            size = 0

        buffer.append(piece)
        size += len(piece) + 1

    flush()

    return chunks


def build_chunk(text, meta, section, part):

    chunk = dict(meta)

    chunk["text"] = text
    chunk["section"] = section
    chunk["part"] = part

    chunk["data_files"] = find_data_files(text)
    chunk["programs"] = find_programs(text)

    return chunk


def program_meta(program, source_type):

    return {
        "program": program,
        "program_id": LEGACY_ID[program],
        "application": APPLICATION[program],
        "source_type": source_type
    }


def read_docx_paragraphs(path):

    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(
            archive.read("word/document.xml")
        )

    paragraphs = []

    for node in document.iter(DOCX_NS + "p"):

        text = "".join(
            run.text or ""
            for run in node.iter(DOCX_NS + "t")
        ).strip()

        if text:
            paragraphs.append(text)

    return paragraphs


def chunk_technical_xml(program):
    """The deepest source: file inventories, call graphs and every branch.

    Split on the document's own section tags. These carry the input/output file
    lists that connect a corrupted-file ticket to the programs that read it.
    """

    path = f"{DOC_ROOT}/TechnicalDocuments/{program}-cbl-0.4.4.xml"

    root = ET.parse(path).getroot()

    meta = program_meta(program, "technical_xml")

    chunks = []

    for section in root:

        for subsection in list(section) or [section]:

            body = clean(
                "".join(subsection.itertext())
            )

            chunks.extend(
                pack(
                    body.split("\n"),
                    meta,
                    f"{section.tag}/{subsection.tag}"
                )
            )

    return chunks


def chunk_program_summary(program):
    """The only human-written source, and the closest thing to a runbook.

    Section 6.6 is Error Handling and Recovery; section 10 is Risks and
    Operational Considerations. Splitting on numbered headings keeps those
    intact instead of scattering them across arbitrary boundaries.
    """

    matches = glob.glob(
        f"{DOC_ROOT}/Level 1 and Level 2 documents/"
        f"YashFormat-ProgramSummary/{program}*.docx"
    )

    if not matches:
        return []

    paragraphs = read_docx_paragraphs(matches[0])

    meta = program_meta(program, "program_summary_docx")

    chunks = []
    section = "Introduction"
    body = []

    for paragraph in paragraphs:

        is_heading = (
            HEADING_RE.match(paragraph)
            and len(paragraph) < 110
        )

        if is_heading:

            chunks.extend(
                pack(body, meta, section)
            )

            section = paragraph
            body = []
            continue

        body.append(paragraph)

    chunks.extend(
        pack(body, meta, section)
    )

    return chunks


def chunk_program_overview(program):
    """A single paragraph of identity per program, used to route a query."""

    path = f"{DOC_ROOT}/Summary/TechnicalDetails/{program}-cbl.json"

    if not os.path.exists(path):
        return []

    with open(path) as handle:
        overview = (
            json.load(handle)
            .get("documentation", {})
            .get("high_level_overview", {})
        )

    lines = [
        overview.get("overview", "")
    ]

    for feature in overview.get("key_features", []):
        lines.append(
            f"- {feature['feature']}: {feature['description']}"
        )

    return pack(
        lines,
        program_meta(program, "program_overview"),
        "overview"
    )


def chunk_business_rules(program):
    """Given/When/Then statements of what the program does.

    Kept despite their bulk: removing them entirely costs 0.10 MRR, the largest
    single drop measured. 05RHE247 is thinned to the decision-shaped types
    because keeping all of its 8,105 rules costs 0.034 MRR.
    """

    path = f"{DOC_ROOT}/BusinessDocuments/{program}-cbl.json"

    if not os.path.exists(path):
        return []

    with open(path) as handle:
        rules = json.load(handle).get("all_rules") or []

    if RULE_STRATEGY[program] == "filter":

        rules = [
            rule
            for rule in rules
            if rule.get("Rule_Type") in KEEP_RULE_TYPES
        ]

    lines = []

    for rule in rules:

        criteria = rule.get("Acceptance_Criteria") or {}

        line = (
            f"[{rule.get('Rule_Id')}] {rule.get('Rule_Name')} "
            f"({rule.get('Rule_Type')}): {rule.get('Rule_Description')}"
        )

        if criteria:
            line += (
                f" GIVEN {criteria.get('Given')}"
                f" WHEN {criteria.get('When')}"
                f" THEN {criteria.get('Then')}"
            )

        lines.append(line)

    return pack(
        lines,
        program_meta(program, "business_rule"),
        "business_rules"
    )


def chunk_estate_catalogue():
    """One sentence for each of ~900 programs across the whole estate.

    The detailed documents cover five programs; incidents name many more. This
    is what lets the agent say something about an unfamiliar program instead of
    returning nothing.
    """

    path = (
        f"{DOC_ROOT}/WorkingTransformOutputs_Prakash'sWorkshop/"
        "TransformCoverPage-1000Programs.pdf"
    )

    reader = PdfReader(path)

    text = re.sub(
        r"\s*\n\s*",
        " ",
        "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )
    )

    chunks = []

    for match in CATALOGUE_ENTRY_RE.finditer(text):

        program_id = match.group(1).upper()

        summary = clean(match.group(2))

        chunks.append(
            build_chunk(
                f"Program {program_id}: {summary}",
                {
                    "program": program_id,
                    "program_id": program_id,
                    "application": "REMAN estate",
                    "source_type": "estate_catalogue"
                },
                "one_line_summary",
                0
            )
        )

    return chunks


def chunk_general_documents():
    """Business-language context: exec summaries and requirements documents.

    Measured as neutral - neither helped nor hurt the sixteen failure-oriented
    test queries. Kept because they are 1.6% of the corpus and cover questions
    phrased in business rather than failure terms, which the harness does not
    probe.
    """

    paths = sorted(
        glob.glob(f"{DOC_ROOT}/Level 1 and Level 2 documents/*.docx")
    ) + [
        f"{DOC_ROOT}/WorkingTransformOutputs_Prakash'sWorkshop/"
        "Requirement Document_6Programs.docx"
    ]

    chunks = []

    for path in paths:

        if not os.path.exists(path):
            continue

        meta = {
            "program": "(general)",
            "program_id": "",
            "application": "REMAN",
            "source_type": "general_doc"
        }

        chunks.extend(
            pack(
                read_docx_paragraphs(path),
                meta,
                os.path.basename(path)
            )
        )

    return chunks


def assign_chunk_ids(chunks):
    """Numbers chunks within each (program, source_type, section).

    Assigned centrally rather than per-section because two things collide
    otherwise: a section heading that repeats inside one document, and the
    estate catalogue, which lists a handful of programs twice with slightly
    different wording (once from the .CBL path, once from the .txt path).
    Both are kept - the id just has to stay unique and stable across re-runs.
    """

    seen = {}

    for chunk in chunks:

        key = (
            chunk["program"],
            chunk["source_type"],
            chunk["section"]
        )

        index = seen.get(key, 0)
        seen[key] = index + 1

        chunk["part"] = index

        chunk["chunk_id"] = (
            f"{chunk['program']}:{chunk['source_type']}:"
            f"{chunk['section']}:{index}"
        )

    return chunks


def load_chunks(doc_root=DOC_ROOT):

    if not os.path.isdir(doc_root):
        raise RuntimeError(
            f"Document root not found: {doc_root}"
        )

    chunks = []

    for program in LEGACY_ID:
        chunks.extend(chunk_technical_xml(program))
        chunks.extend(chunk_program_summary(program))
        chunks.extend(chunk_program_overview(program))
        chunks.extend(chunk_business_rules(program))

    chunks.extend(chunk_estate_catalogue())
    chunks.extend(chunk_general_documents())

    return assign_chunk_ids(chunks)


def build_embedding_text(chunk):
    """What similarity search actually matches on.

    The program and application are prefixed so a query mentioning "LMS" can
    reach an LMS chunk semantically. Identifiers are deliberately NOT relied on
    here - they are filtered on instead, because the embedding model cannot tell
    IN0001.MST from IN0056.MST.
    """

    header = f"{chunk['application']} - {chunk['program']}"

    section = chunk.get("section", "")

    if section and not section.startswith("("):
        header += f" - {section}"

    return f"{header}\n\n{chunk['text']}"
