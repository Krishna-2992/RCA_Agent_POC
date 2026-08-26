"""Live progress tracking for the RCA workflow.

The LangGraph run is a long, mostly-silent process (the GitHub investigator
alone can take several minutes). This module turns the graph stream into a
step-by-step status model the UI can paint while the run is still going.
"""

import json
import os
import time


PENDING = "pending"
RUNNING = "running"
DONE = "done"
SKIPPED = "skipped"
FAILED = "failed"


# Canonical left-to-right order shown in the UI flow.
# Branch-only nodes (clarification, kb, github investigator) stay in the list
# and are marked "skipped" when the router walks past them.

# Labels are what the person watching reads, so they describe the work rather
# than naming the agent that does it. The technical name is kept alongside for
# whoever has to map a slow or failed row back to the code.

STEP_SEQUENCE = [

    ("query_analyzer", "Understanding the incident"),

    ("clarification", "Requesting more details"),

    ("servicenow", "Searching past incidents"),

    ("servicenow_evaluator", "Assessing past incidents"),

    ("kb_retriever", "Searching the knowledge base"),

    ("kb_evaluator", "Selecting relevant articles"),

    ("github_decision", "Deciding on code investigation"),

    ("github_investigator", "Investigating the code repository"),

    ("evidence", "Assembling the evidence"),

    ("rca", "Writing the root cause analysis"),

    ("validation", "Validating the analysis")

]


STEP_TECHNICAL_NAMES = {

    "query_analyzer": "Query Analyzer",

    "clarification": "Clarification Agent",

    "servicenow": "ServiceNow Retriever",

    "servicenow_evaluator": "ServiceNow Evaluator",

    "kb_retriever": "KB Retriever",

    "kb_evaluator": "KB Evaluator",

    "github_decision": "GitHub Decision",

    "github_investigator": "GitHub Investigator",

    "evidence": "Evidence Aggregator",

    "rca": "RCA Agent",

    "validation": "Validation Agent"

}


# What the person watching actually wants to know: which stage is this at.
# The graph's eleven nodes are implementation detail, so they are rolled up into
# phases. Each phase still reports the live activity of whichever node inside it
# is running, so grouping costs no visible detail.

PHASE_SEQUENCE = [

    (
        "understanding",
        "Understanding the incident",
        ["query_analyzer", "clarification"]
    ),

    (
        "history",
        "Reviewing past incidents",
        ["servicenow", "servicenow_evaluator"]
    ),

    (
        "knowledge",
        "Consulting the knowledge base",
        ["kb_retriever", "kb_evaluator"]
    ),

    (
        "code",
        "Investigating the code",
        ["github_decision", "github_investigator"]
    ),

    (
        "analysis",
        "Producing the analysis",
        ["evidence", "rca", "validation"]
    )

]


def phase_snapshot(steps):
    """Rolls a step snapshot up into the phases shown in the UI.

    A phase fails if anything in it failed, runs while anything in it is running
    or has started but not finished, and is skipped only when the router bypassed
    every node it contains. Its duration is the time spent across its nodes.
    """

    by_key = {
        step["key"]: step
        for step in steps
    }

    rows = []

    for index, (key, label, members) in enumerate(PHASE_SEQUENCE):

        children = [
            by_key[member]
            for member in members
            if member in by_key
        ]

        statuses = {
            child["status"]
            for child in children
        }

        if FAILED in statuses:
            status = FAILED

        elif RUNNING in statuses:
            status = RUNNING

        elif statuses == {SKIPPED}:
            status = SKIPPED

        elif statuses <= {PENDING, SKIPPED}:
            status = PENDING

        elif PENDING in statuses:
            # part way through, momentarily between two of its own nodes
            status = RUNNING

        else:
            status = DONE

        elapsed = 0.0

        for child in children:

            if child["duration"] is not None:
                elapsed += child["duration"]

            elif child["status"] == RUNNING and child.get("elapsed"):
                elapsed += child["elapsed"]

        rows.append(
            {
                "key": key,
                "label": label,
                "position": index + 1,
                "status": status,
                "elapsed": elapsed if elapsed else None,
                "duration": elapsed if status == DONE else None
            }
        )

    return rows


FIRST_STEP = STEP_SEQUENCE[0][0]


STEP_LABELS = dict(
    STEP_SEQUENCE
)


STEP_ORDER = {
    key: index
    for index, (key, _) in enumerate(STEP_SEQUENCE)
}


# What each step is doing, shown while it is running.

STEP_ACTIVITY = {

    "query_analyzer":
        "Pulling out the affected service, the symptom and anything missing",

    "clarification":
        "Working out what still needs to be asked",

    "servicenow":
        "Searching historical incident records for similar failures",

    "servicenow_evaluator":
        "Judging which past tickets genuinely match this incident",

    "kb_retriever":
        "Searching runbooks and knowledge base documents",

    "kb_evaluator":
        "Keeping only the articles that apply here",

    "github_decision":
        "Working out whether code evidence is needed",

    "github_investigator":
        "Reading the application source and its recent changes",

    "evidence":
        "Merging every source into one cited catalogue",

    "rca":
        "Drafting the root cause, fixes and preventive actions",

    "validation":
        "Checking every claim is backed by cited evidence"

}


# Mirrors the routers in src/graph/workflow.py so the UI can mark the next
# node as running the moment the previous one finishes.

def predict_next_step(node, state):

    if node == "query_analyzer":

        return (
            "clarification"
            if state.get("needs_clarification")
            else "servicenow"
        )

    if node == "servicenow":

        return "servicenow_evaluator"

    if node == "servicenow_evaluator":

        return (
            "kb_retriever"
            if state.get("need_kb")
            else "github_decision"
        )

    if node == "kb_retriever":

        return "kb_evaluator"

    if node == "kb_evaluator":

        return "github_decision"

    if node == "github_decision":

        return (
            "github_investigator"
            if state.get("need_github")
            else "evidence"
        )

    if node == "github_investigator":

        return "evidence"

    if node == "evidence":

        return "rca"

    if node == "rca":

        return "validation"

    if node == "validation":

        return (
            "clarification"
            if state.get("needs_human_input")
            else None
        )

    return None


class ProgressTracker:
    """Status of every workflow step, plus the merged state seen so far."""

    def __init__(self):

        self.state = {}

        self.active = None

        self.steps = {

            key: {
                "key": key,
                "label": label,
                "technical": STEP_TECHNICAL_NAMES.get(key, key),
                "position": index + 1,
                "status": PENDING,
                "started_at": None,
                "duration": None
            }

            for index, (key, label) in enumerate(STEP_SEQUENCE)

        }

    # ------------------------------------------------------------------

    def start(self, key):

        if key not in self.steps:
            return

        for step in self.steps.values():

            if (
                step["status"] == PENDING
                and STEP_ORDER[step["key"]] < STEP_ORDER[key]
            ):
                step["status"] = SKIPPED

        step = self.steps[key]

        step["status"] = RUNNING

        step["started_at"] = time.monotonic()

        step["duration"] = None

        self.active = key

    def complete(self, key):

        step = self.steps.get(key)

        if not step:
            return

        if step["started_at"] is not None:
            step["duration"] = time.monotonic() - step["started_at"]

        step["status"] = DONE

        if self.active == key:
            self.active = None

    def fail_active(self):

        if not self.active:
            return

        step = self.steps[self.active]

        if step["started_at"] is not None:
            step["duration"] = time.monotonic() - step["started_at"]

        step["status"] = FAILED

    def finish(self):
        """Graph ended: nothing is running and untouched steps were bypassed."""

        for step in self.steps.values():

            if step["status"] == RUNNING:
                self.complete(step["key"])

            elif step["status"] == PENDING:
                step["status"] = SKIPPED

        self.active = None

    # ------------------------------------------------------------------

    def observe(self, node, delta):
        """Record that `node` finished and advance to whatever runs next."""

        if isinstance(delta, dict):
            self.state.update(delta)

        if node in self.steps and self.steps[node]["status"] != RUNNING:
            self.start(node)

        self.complete(node)

        next_step = predict_next_step(
            node,
            self.state
        )

        if next_step:
            self.start(next_step)

    def merge_state(self, state):

        if isinstance(state, dict):
            self.state.update(state)

    # ------------------------------------------------------------------

    def snapshot(self):

        now = time.monotonic()

        rows = []

        for _, (key, _label) in enumerate(STEP_SEQUENCE):

            step = dict(
                self.steps[key]
            )

            if step["status"] == RUNNING and step["started_at"] is not None:
                step["elapsed"] = now - step["started_at"]

            else:
                step["elapsed"] = step["duration"]

            rows.append(step)

        return rows

    @property
    def active_label(self):

        if not self.active:
            return None

        return STEP_LABELS.get(
            self.active,
            self.active
        )

    @property
    def active_elapsed(self):

        if not self.active:
            return None

        started = self.steps[self.active]["started_at"]

        if started is None:
            return None

        return time.monotonic() - started


class TraceTail:
    """Reads new lines appended to the GitHub investigation trace log.

    Only lines written after this object is created are considered, so a
    previous run's trace never leaks into the current status line.
    """

    TOOL_ACTIVITY = {
        "get_file_contents": "Reading a source file",
        "search_code": "Searching the codebase",
        "list_commits": "Reviewing recent changes",
        "list_pull_requests": "Checking pull requests",
        "get_pull_request": "Reviewing a pull request",
        "get_pull_request_files": "Reviewing what a change touched",
        "get_pull_request_comments": "Reading review discussion",
        "list_issues": "Checking reported issues",
        "get_issue": "Reading a reported issue"
    }

    @classmethod
    def describe(cls, event, payload):
        """A short, plain description of what the investigation is doing.

        Returning None leaves the previous description in place, which is what
        we want for bookkeeping events - a raw byte count tells a reader nothing.
        """

        if event == "tool_start":

            return cls.TOOL_ACTIVITY.get(
                payload.get("tool"),
                "Querying the repository"
            )

        if event == "attempt_start" and (payload.get("attempt") or 1) > 1:
            return "Retrying the code investigation"

        if event == "tool_error":
            return "Recovering from a failed lookup"

        if event == "final_answer":
            return "Summarising what the code shows"

        return None

    def __init__(self, path):

        self.path = path

        self.offset = 0

        self.latest_label = None

        try:
            self.offset = os.path.getsize(path)

        except OSError:
            self.offset = 0

    def poll(self):

        try:
            size = os.path.getsize(self.path)

        except OSError:
            return self.latest_label

        if size < self.offset:
            self.offset = 0

        if size == self.offset:
            return self.latest_label

        try:
            with open(self.path, "r") as handle:

                handle.seek(self.offset)

                chunk = handle.read()

                self.offset = handle.tell()

        except OSError:
            return self.latest_label

        for line in chunk.splitlines():

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)

            except ValueError:
                continue

            try:
                described = self.describe(
                    record.get("event"),
                    record.get("payload") or {}
                )

            except Exception:
                continue

            if described:
                self.latest_label = described

        return self.latest_label
