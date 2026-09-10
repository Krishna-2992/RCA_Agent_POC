"""Builds the REMAN digest from the documentation, as a JSON artifact.

The digest is what lets the pipeline judge whether a report is specific enough
to investigate, and rewrite it into the vocabulary the documents actually use.
That job needs the estate's nouns - applications, programs, data files, menu
options, recovery paths - not its prose, so this extracts names and discards
everything else.

Generated rather than hand-written for one reason: a hand-written digest is a
second source of truth that drifts from the corpus the moment either changes.
Anything asserted here can be traced back to a file under DOC_ROOT by re-running
the script.

Two things are deliberately not extracted. Error-code meanings are not in the
documentation at all - operators report 984 and 9802, the documents describe
file-status handling in the abstract - so those live in a small reviewed table
in src/domain/reman_digest.py with their provenance recorded. And the estate
catalogue's ~1000 one-line program summaries are read only for their program
ids, because that is all a query rewriter can use them for.

Run:  python -m ingestion.build_reman_digest
"""

import json
import os
import re

from collections import defaultdict


DOC_ROOT = "sharepoint_docs/Reman/AWSTransform_Documentation"

TECHNICAL_DIR = os.path.join(DOC_ROOT, "TechnicalDocuments")

OUTPUT_PATH = "src/domain/reman_digest.json"


# The six programs with full technical documentation. Everything else in the
# estate has a one-line summary and nothing more, which is why only these carry
# menus and recovery paths.
PROGRAMS = {
    "01RMNIDX": ("Reman Index", "F8RH0071"),
    "02RMNINVTR": ("Inventory", "F8RH0030"),
    "03RMNLMS": ("LMS", "F8RH0093"),
    "04RH0442": ("Reporting", "F8RH0442"),
    "05RHE247": ("Inventory Detail", "F8RHE247"),
    "06RH0101": ("BOM", "F8RH0101")
}


DATA_FILE_RE = re.compile(
    r"\b((?:IN|LM|BM)\d{2,4}\.[A-Z]{3})\b"
)


# "IN0011.MST): Indexed location file containing part location and quantity"
# The colon-and-gloss shape is how the AWS Transform output introduces a file,
# and it is the only place the corpus says what a file actually holds.
FILE_GLOSS_RE = re.compile(
    r"\b((?:IN|LM|BM)\d{2,4}\.[A-Z]{3})\)?\s*[:-]\s*([A-Z][^.\n]{15,110})"
)


# "F10: RECOVER - Performs 1405-CHECK-SECURITY" and
# "1400-OPTION-FOUR (PART MAINT)" - the two ways a screen is named.
#
# The label is not case-constrained. Screens are written "F10: RECOVER" in one
# program and "F2: Add new record" in another, and an uppercase-only pattern
# silently returned nothing at all for four of the six.
FUNCTION_KEY_RE = re.compile(
    r"\b(F\d{1,2}):\s+([A-Za-z][A-Za-z0-9 /&-]{2,34}?)"
    r"(?=\s+[-–]|\s+via\b|\s+Calls\b|\s+Performs\b|\s*$)"
)

MENU_OPTION_RE = re.compile(
    r"\b(\d{4}-OPTION-[A-Z]+)\s*\(([A-Z][A-Za-z /&-]{2,32})\)"
)


RECOVERY_HINT_RE = re.compile(
    r"[^.]{0,200}RECOVER1\.EXE[^.]{0,200}\.",
    re.I
)


def read_flat(path):
    """The document as one line, so a regex is not defeated by wrapping."""

    with open(path, errors="replace") as handle:
        return re.sub(r"\s+", " ", handle.read())


def extract_program(program, text):
    """Names, files, screens and recovery path for one documented program."""

    files = defaultdict(str)

    for name in DATA_FILE_RE.findall(text):
        files.setdefault(name, "")

    # A file is described in several places and the descriptions vary in
    # quality; the longest is reliably the one that says what it holds rather
    # than what was done to it on one particular code path.
    for name, gloss in FILE_GLOSS_RE.findall(text):

        gloss = gloss.strip()

        if len(gloss) > len(files[name]):
            files[name] = gloss

    # Every meaning, not the first one found. A function key is scoped to the
    # submenu it is pressed on: F10 is HELP on one Inventory screen and RECOVER
    # on another, and recording whichever the regex happened to reach first
    # produced a digest that confidently said F10 was HELP. A list of the
    # meanings a key carries is true; a single answer is not.
    keys = defaultdict(set)

    for key, label in FUNCTION_KEY_RE.findall(text):
        keys[key].add(label.strip())

    options = {}

    for section, label in MENU_OPTION_RE.findall(text):
        options.setdefault(section, label.strip())

    recovery = RECOVERY_HINT_RE.findall(text)

    application, program_id = PROGRAMS[program]

    return {
        "program": program,
        "program_id": program_id,
        "application": application,
        "data_files": {
            name: gloss
            for name, gloss in sorted(files.items())
            if gloss
        },
        "function_keys": {
            key: sorted(labels)
            for key, labels in sorted(keys.items())
        },
        "menu_options": dict(sorted(options.items())),
        "recovery": [
            sentence.strip()
            for sentence in recovery[:4]
        ]
    }


def build():

    estate = {}

    for program in sorted(PROGRAMS):

        path = os.path.join(
            TECHNICAL_DIR,
            f"{program}-cbl-0.4.4.xml"
        )

        if not os.path.exists(path):

            print(f"  {program}: no technical document, skipped")

            continue

        entry = extract_program(
            program,
            read_flat(path)
        )

        estate[program] = entry

        print(
            f"  {program} ({entry['application']}): "
            f"{len(entry['data_files'])} files, "
            f"{len(entry['function_keys'])} function keys, "
            f"{len(entry['menu_options'])} menu options, "
            f"{len(entry['recovery'])} recovery references"
        )

    # One file is opened by several programs, and which programs share it is
    # the fact that decides whether naming an application narrows anything.
    shared = defaultdict(list)

    for program, entry in estate.items():

        for name in entry["data_files"]:
            shared[name].append(entry["application"])

    catalogue = {
        name: {
            "what": next(
                (
                    entry["data_files"][name]
                    for entry in estate.values()
                    if entry["data_files"].get(name)
                ),
                ""
            ),
            "used_by": sorted(set(applications))
        }
        for name, applications in sorted(shared.items())
    }

    return {
        "programs": estate,
        "data_files": catalogue
    }


def main():

    print("\n--- Building REMAN digest ---")

    digest = build()

    os.makedirs(
        os.path.dirname(OUTPUT_PATH),
        exist_ok=True
    )

    with open(OUTPUT_PATH, "w") as handle:

        json.dump(
            digest,
            handle,
            indent=2,
            sort_keys=True
        )

    print(
        f"\n{len(digest['programs'])} programs, "
        f"{len(digest['data_files'])} distinct data files "
        f"-> {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
