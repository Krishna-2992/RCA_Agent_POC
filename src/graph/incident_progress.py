"""Progress tracking for the ServiceNow-only workflow.

Self-contained on purpose: the payment pipeline's tracker is hardwired to its
own eleven steps and routers, and this pipeline should be able to change shape
without touching a file that app.py depends on. Only the status constants are
shared, since the renderer keys off them.
"""

import time

from src.graph.progress import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    SKIPPED
)


INCIDENT_STEPS = [

    ("query_analyzer", "Understanding the incident"),

    ("clarification", "Requesting more details"),

    ("retrieve", "Searching past records"),

    ("evaluate", "Assessing past records"),

    ("evidence", "Assembling the evidence"),

    ("rca", "Writing the root cause analysis"),

    ("validation", "Validating the analysis")

]


INCIDENT_PHASES = [

    (
        "understanding",
        "Understanding the incident",
        ["query_analyzer", "clarification"]
    ),

    (
        "history",
        "Reviewing past incidents",
        ["retrieve", "evaluate"]
    ),

    (
        "analysis",
        "Producing the analysis",
        ["evidence", "rca", "validation"]
    )

]


INCIDENT_ACTIVITIES = {

    "query_analyzer":
        "Pulling out the affected system, the symptom and any error code named",

    "clarification":
        "Working out what still needs to be asked",

    "retrieve":
        "Searching historical incidents, requests and changes",

    "evaluate":
        "Judging which past records genuinely match this one",

    "evidence":
        "Gathering the matching records and counting repeats",

    "rca":
        "Drafting the root cause, fixes and preventive actions",

    "validation":
        "Checking every claim is backed by a cited record"

}


INCIDENT_TECHNICAL_NAMES = {

    "query_analyzer": "Query Analyzer",

    "clarification": "Clarification Agent",

    "retrieve": "ServiceNow Retriever",

    "evaluate": "ServiceNow Evaluator",

    "evidence": "Evidence Aggregator",

    "rca": "RCA Agent",

    "validation": "Validation Agent"

}


def predict_next_incident_step(node, state):

    if node == "query_analyzer":

        return (
            "clarification"
            if state.get("needs_clarification")
            else "retrieve"
        )

    if node == "retrieve":
        return "evaluate"

    if node == "evaluate":

        return (
            "evidence"
            if state.get("matching_records")
            else "clarification"
        )

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


FIRST_INCIDENT_STEP = INCIDENT_STEPS[0][0]


INCIDENT_STEP_ORDER = {
    key: index
    for index, (key, _label) in enumerate(INCIDENT_STEPS)
}


class IncidentProgressTracker:
    """Status of every step in the incident workflow, plus the state so far."""

    def __init__(self):

        self.state = {}

        self.active = None

        self.steps = {

            key: {
                "key": key,
                "label": label,
                "technical": INCIDENT_TECHNICAL_NAMES.get(key, key),
                "position": index + 1,
                "status": PENDING,
                "started_at": None,
                "duration": None
            }

            for index, (key, label) in enumerate(INCIDENT_STEPS)

        }

    # ------------------------------------------------------------------

    def start(self, key):

        if key not in self.steps:
            return

        for step in self.steps.values():

            if (
                step["status"] == PENDING
                and INCIDENT_STEP_ORDER[step["key"]] < INCIDENT_STEP_ORDER[key]
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

        next_step = predict_next_incident_step(
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

        for key, _label in INCIDENT_STEPS:

            step = dict(self.steps[key])

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

        return dict(INCIDENT_STEPS).get(
            self.active,
            self.active
        )


def incident_phase_snapshot(steps):
    """Rolls the step snapshot up into the three stages shown in the UI."""

    by_key = {
        step["key"]: step
        for step in steps
    }

    rows = []

    for index, (key, label, members) in enumerate(INCIDENT_PHASES):

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
