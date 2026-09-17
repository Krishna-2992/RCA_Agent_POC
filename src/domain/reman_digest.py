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
    "9302": {
        "seen_as": ("9302",),
        "means": "File lock, reported on control files rather than masters",
        "usual_fix": "Close the lock; the file is usually not corrupt",
        "source": "ticket history (3 incidents, all IN0014.CTL)"
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


# Files the tickets name that the technical documentation never describes, so
# the generated digest cannot know them. IN0014.CTL appears in three incidents
# as "file lock in light decon" and in no document at all - the estate is larger
# than the six programs AWS Transform wrote up, and a file being undocumented is
# not a reason to leave the support team without its name.
UNDOCUMENTED_FILES = {
    "IN0014.CTL": {
        "what": "Light decon control file",
        "used_by": ["Inventory"],
        "source": "ticket history (INC10148317, INC10109021, INC10055662)"
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

            # Undocumented files are listed with the documented ones, marked so
            # nothing downstream quotes them as documentation. A support
            # engineer needs the name whether or not AWS Transform wrote it up.
            for name, entry_data in sorted(UNDOCUMENTED_FILES.items()):

                if application not in entry_data["used_by"]:
                    continue

                lines.append(
                    f"    {name}: {entry_data['what']} "
                    f"[not in the documentation; known from "
                    f"{entry_data['source']}]"
                )

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


# Symptoms whose remedy is a recovery procedure rather than an explanation.
# A corrupt or locked file is not a question about what a program does; it is a
# request for the screen that repairs it, and that screen usually lives in a
# different program from the one the reporter names.
RECOVERY_SYMPTOMS = (
    "corrupt", "corrupted", "corruption", "invalid file structure",
    "bad file", "damaged", "rebuild", "recover", "recovery",
    "file lock", "locked", "lock error", "duplicate open", "will not open",
    "cannot open", "can not open", "unopened"
)


def recovery_applications():
    """Applications whose documentation actually describes a recovery procedure.

    Derived from the digest rather than named here, so this stays correct when
    the corpus changes. Today it resolves to Reman Index (RECOVER1.EXE via
    Option 34, 6200-FILE-RECOVERY) and Inventory (section 1407-RECOVER); the
    remaining four programs document no recovery at all.

    The distinction this exists to serve: the file that breaks and the screen
    that repairs it belong to different programs. IN0018.MOV is an Inventory
    file, but the operator recovers it from the Reman Index menu, so scoping a
    corruption report to the reporter's own application hides the answer. The
    Option 34 chunk sits at rank two of the whole corpus for such a report and
    was being excluded before ranking began.
    """

    return [
        entry["application"]
        for entry in PROGRAMS.values()
        if entry.get("recovery")
    ]


def needs_recovery_context(text):
    """Whether a report is the kind whose answer is a recovery procedure."""

    if not text:
        return False

    lowered = text.lower()

    return any(
        symptom in lowered
        for symptom in RECOVERY_SYMPTOMS
    )


# What the support team does, in their words, for the failures they see often.
#
# These are not in the documentation and not in the ticket history in any usable
# form. The tickets record outcomes - "Recovered the file", "Locks were closed"
# - and the documentation records mechanism - 6200-FILE-RECOVERY calls
# RECOVER1.EXE. Neither records the sequence an engineer actually performs, and
# an RCA that cannot supply it sends someone to a terminal with "recover the
# file using the approved procedure", which is not an instruction.
#
# Every entry carries its provenance so nothing here is ever quoted back as if
# a document said it. `when` is matched against the report; `steps` are offered
# to the analysis as a candidate procedure, not asserted as the answer.
PLAYBOOKS = {
    "file_recovery": {
        "when": (
            "corrupt", "corrupted", "invalid file structure", "bad file",
            "983", "984", "9802", "98", "4600", "damaged file"
        ),
        "what": "Indexed file is corrupt, locked, or both",
        "steps": [
            "Confirm every user is out of the affected file.",
            "From the DOS prompt, close the lock on the file.",
            "From Reman Index, take Option 34 (File Recovery). This needs "
            "security level 4 or above (HOLD-UPDATE >= '4').",
            "Option 34 runs 6200-FILE-RECOVERY, which calls RECOVER1.EXE to "
            "rebuild the indexed file.",
            "Have the user reopen the application and confirm the error is "
            "gone."
        ],
        "source": (
            "Reman support team, confirmed against INC9581851 "
            "(\"From DOS prompt close the lock and then from Reman Index "
            "Option 34 recover the file\"); the Option 34 and RECOVER1.EXE "
            "detail is corroborated by 01RMNIDX documentation"
        )
    },
    "control_file_lock": {
        "when": ("9302", "file lock", "light decon"),
        "what": "File lock on a control file rather than a master file",
        "steps": [
            "Identify the locked control file from the error text - these are "
            "usually .CTL files such as IN0014.CTL, not the masters.",
            "Close the lock. The file is usually not corrupt, so recovery is "
            "not normally needed.",
            "If the error returns immediately, treat it as the file-recovery "
            "case instead."
        ],
        "source": "ticket history (3 incidents, all IN0014.CTL)"
    },
    "batch_transient": {
        "when": (
            "did not print", "didn't print", "not printed", "did not run",
            "batch", "tidal", "scheduled job", "overnight", "auto",
            "not showing", "zeroed out"
        ),
        "what": (
            "Batch- or schedule-raised incident with no specific fault found"
        ),
        "steps": [
            "Retry the operation before investigating further - reprint the "
            "ticket, reopen the screen, or let the next scheduled run go.",
            "Confirm with the user whether it recurred. A large share of "
            "these do not.",
            "Only if it recurs, look for a locked or corrupt file behind it.",
            "If it cannot be reproduced, say so and close it as not "
            "reproducible rather than inventing a cause."
        ],
        "source": (
            "Reman support team: batch-created incidents are often resolved "
            "by a restart or reopen, and INC9791495 was closed after 24 hours "
            "as not reproducible with no logic fault found"
        )
    }
}


def resolve_playbooks(text):
    """Playbooks whose trigger words appear in the report.

    Longest trigger first so "9802" is not claimed by a match on "98".
    """

    if not text:
        return []

    lowered = text.lower()

    matched = []

    for name, playbook in PLAYBOOKS.items():

        if any(trigger in lowered for trigger in playbook["when"]):
            matched.append((name, playbook))

    return matched


def playbooks_for_prompt(text):
    """Matched playbooks as prompt text, or an empty string if none match."""

    matched = resolve_playbooks(text)

    if not matched:
        return ""

    lines = [
        "Known support procedures for failures of this shape. These come from "
        "the Reman support team, not from the documentation. Use them for the "
        "operator detail of the resolution steps where the report fits, and "
        "say where the detail came from. Do not use them as evidence that this "
        "incident occurred or what caused it."
    ]

    for name, playbook in matched:

        lines.append("")
        lines.append(f"{name}: {playbook['what']}")

        for step in playbook["steps"]:
            lines.append(f"  - {step}")

        lines.append(f"  [source: {playbook['source']}]")

    return "\n".join(lines)
