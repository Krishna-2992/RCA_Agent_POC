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

STEP_SEQUENCE = [

    ("query_analyzer", "Query Analyzer"),

    ("clarification", "Clarification"),

    ("servicenow", "ServiceNow Retriever"),

    ("servicenow_evaluator", "ServiceNow Evaluator"),

    ("kb_retriever", "KB Retriever"),

    ("kb_evaluator", "KB Evaluator"),

    ("github_decision", "GitHub Decision"),

    ("github_investigator", "GitHub Investigator"),

    ("evidence", "Evidence Aggregator"),

    ("rca", "RCA Agent"),

    ("validation", "Validation Agent")

]


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
        "Extracting service, symptom and missing details from the incident",

    "clarification":
        "Preparing follow-up questions",

    "servicenow":
        "Searching historical ServiceNow incidents",

    "servicenow_evaluator":
        "Judging whether past incidents explain this one",

    "kb_retriever":
        "Searching the SharePoint knowledge base",

    "kb_evaluator":
        "Filtering knowledge base articles for relevance",

    "github_decision":
        "Deciding whether code evidence is required",

    "github_investigator":
        "Investigating the repository through the GitHub MCP server",

    "evidence":
        "Merging all evidence into a single catalog",

    "rca":
        "Writing the root cause analysis",

    "validation":
        "Validating the RCA against the evidence"

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

    LABELS = {

        "attempt_start":
            lambda payload: f"Investigation attempt {payload.get('attempt')}",

        "tool_start":
            lambda payload: f"Calling GitHub tool: {payload.get('tool') or 'unknown'}",

        "tool_end":
            lambda payload: f"Received {payload.get('output_chars', 0)} characters from GitHub",

        "tool_error":
            lambda payload: "GitHub tool error, recovering",

        "final_answer":
            lambda payload: "Summarising code evidence"

    }

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

            formatter = self.LABELS.get(
                record.get("event")
            )

            if not formatter:
                continue

            try:
                self.latest_label = formatter(
                    record.get("payload") or {}
                )

            except Exception:
                continue

        return self.latest_label
