"""The REMAN estate as the pipeline needs to know it.

Loads the generated digest (see ingestion/build_reman_digest.py) and adds the
two things a generator cannot supply: what reporters call these systems, and
what the error numbers on their screens mean.

Both additions are hand-maintained on purpose. Plant vocabulary - "kit tickets",
"line checker", "Corinth" - appears nowhere in COBOL documentation, and error
meanings appear nowhere either: the documents describe file-status handling in
the abstract while operators report 984 and 9802. Anything asserted here that
the documents do not support carries its provenance, so a fact learned from
resolved tickets is never quoted back as if the documentation said it.

The one fact that governs everything downstream: IN0011.MST, the Location file,
is opened by both Inventory and LMS. Naming the application therefore does not
identify the file, which is why a report has to name the file or the error text
before it is worth investigating.
"""

import json
import os


DIGEST_PATH = os.path.join(
    os.path.dirname(__file__),
    "reman_digest.json"
)


def _load():
    """The generated digest, or an empty estate if it has not been built.

    Degrades rather than raises: a missing digest should cost query enrichment,
    not the investigation. The caller sees no applications and falls back to
    searching on the reporter's own words.
    """

    try:
        with open(DIGEST_PATH) as handle:
            return json.load(handle)

    except Exception as error:

        print(
            f"  REMAN digest unavailable ({type(error).__name__}); "
            f"run: python -m ingestion.build_reman_digest"
        )

        return {"programs": {}, "data_files": {}}


DIGEST = _load()

PROGRAMS = DIGEST["programs"]

DATA_FILES = DIGEST["data_files"]


# What reporters type, lowercased. Not derivable from the documentation - these
# are the words that appear in ticket short descriptions, not in COBOL.
ALIASES = {
    "Inventory": (
        "inventory", "material system", "material systems", "corinth",
        "invtr", "f8rh0030", "02rmninvtr", "part master", "stock", "on-hand"
    ),
    "LMS": (
        "lms", "location management", "warehouse location", "locator", "bin",
        "f8rh0093", "03rmnlms", "kit ticket", "kits", "line checker",
        "replenishment"
    ),
    "Reman Index": (
        "reman index", "sign on", "signon", "sign-on", "login", "log in",
        "password", "security", "access level", "f8rh0071", "01rmnidx"
    ),
    "Inventory Detail": (
        "inventory detail", "detail inquiry", "f8rhe247", "05rhe247", "e247"
    ),
    "BOM": (
        "bom", "bill of material", "assembly", "component", "f8rh0101",
        "06rh0101"
    ),
    # Not "report" or "reporting": the analyser routinely writes symptoms as
    # "... reporting error code 98", and a substring alias that loose pulled
    # the Reporting application into the scope of every error a user reports.
    "Reporting": (
        "f8rh0442", "04rh0442", "report program", "reporting program"
    )
}


# From resolved tickets, not from the documents. `source` is carried through to
# every prompt that quotes these so the distinction survives.
ERROR_FAMILIES = {
    "98": {
        "seen_as": ("98", "983", "984", "9802"),
        "means": "Indexed file corrupt, locked, or both",
        "usual_fix": "Close every open instance, then run file recovery",
        "source": "ticket history (10 incidents)"
    },
    "4600": {
        "seen_as": ("4600",),
        "means": "No file position, reported alongside a corrupt index",
        "usual_fix": "Close every open instance, then run file recovery",
        "source": "ticket history (2 incidents)"
    },
    "35": {
        "seen_as": ("35",),
        "means": "File not found on open",
        "usual_fix": "Confirm the file exists and the drive is mapped",
        "source": "02RMNINVTR technical documentation"
    }
}


# Transcription slips seen in real tickets. A reporter reading an error off a
# terminal loses a digit or a letter, and the resulting name is a different real
# file rather than an obvious typo - IN001.MST pads to IN0001.MST, the Inventory
# Master, when five sibling tickets prove it means IN0011.MST, the Location file.
FILE_ALIASES = {
    "IN001.MST": "IN0011.MST",
    "IN0011MST": "IN0011.MST",
    "IN0015.MOR": "IN0015.MOV",
    "IN0018.MOL": "IN0018.MOV",
    "IN0018.MST": "IN0018.MOV"
}


APPLICATION_OF = {
    entry["application"]: program
    for program, entry in PROGRAMS.items()
}


def resolve_application(text):
    """Applications a report plausibly concerns, by alias match."""

    if not text:
        return []

    lowered = text.lower()

    return [
        name
        for name in ALIASES
        if name in APPLICATION_OF
        and any(alias in lowered for alias in ALIASES[name])
    ]


def resolve_error_family(text):
    """The family an error number belongs to, longest code first.

    Longest first so 9802 is not swallowed by a match on 98.
    """

    if not text:
        return None

    lowered = text.lower()

    candidates = sorted(
        (
            (code, family)
            for family in ERROR_FAMILIES.values()
            for code in family["seen_as"]
        ),
        key=lambda pair: -len(pair[0])
    )

    for code, family in candidates:

        if code in lowered:
            return family

    return None


def canonical_file(name):
    """The real file a ticket's spelling denotes."""

    return FILE_ALIASES.get(
        name.upper(),
        name.upper()
    )


def program_for(application):

    return PROGRAMS.get(
        APPLICATION_OF.get(application, ""),
        {}
    )


def estate_summary():
    """Every application, one line each, for a sufficiency judgement.

    Deliberately terse: this is shown to a model deciding whether a report
    names a system it recognises, which needs the names and nothing else.
    """

    lines = []

    for application, program in sorted(APPLICATION_OF.items()):

        entry = PROGRAMS[program]

        lines.append(
            f"- {application} (program {entry['program']}, "
            f"{entry['program_id']})"
        )

    return "\n".join(lines)


def digest_for_prompt(applications=None):
    """The digest as prompt text, narrowed to the applications in play.

    Passing the whole estate invites questions and rewrites about programs the
    reporter has never opened, so the caller filters first and only falls back
    to everything when nothing resolved.
    """

    names = [
        name
        for name in (applications or [])
        if name in APPLICATION_OF
    ] or sorted(APPLICATION_OF)

    lines = []

    for application in names:

        entry = program_for(application)

        if not entry:
            continue

        lines.append(
            f"{application} - program {entry['program']} "
            f"({entry['program_id']})"
        )

        files = entry.get("data_files") or {}

        if files:

            lines.append("  data files:")

            for name, what in sorted(files.items()):

                shared = DATA_FILES.get(name, {}).get("used_by") or []

                also = (
                    f" [also opened by {', '.join(n for n in shared if n != application)}]"
                    if len(shared) > 1
                    else ""
                )

                lines.append(f"    {name}: {what}{also}")

        options = entry.get("menu_options") or {}

        if options:

            lines.append(
                "  menu options: "
                + ", ".join(
                    f"{section} ({label})"
                    for section, label in sorted(options.items())
                )
            )

        keys = entry.get("function_keys") or {}

        if keys:

            lines.append(
                "  function keys (a key means different things on different "
                "submenus): "
                + ", ".join(
                    f"{key}={'/'.join(labels)}"
                    for key, labels in sorted(keys.items())
                )
            )

        for sentence in entry.get("recovery") or []:
            lines.append(f"  recovery: {sentence}")

    lines.append("")

    lines.append("Error codes operators report (source: resolved tickets, not documentation):")

    for family in ERROR_FAMILIES.values():

        lines.append(
            f"  {', '.join(family['seen_as'])} - {family['means']}. "
            f"{family['usual_fix']}."
        )

    return "\n".join(lines)
