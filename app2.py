"""Agentic RCA driven by ServiceNow evidence.

A second entry point alongside app.py. That pipeline also draws on SharePoint
and GitHub; this one works from ServiceNow records, which is the source we hold
in a complete and reliable form, so it runs a shorter workflow.

The chrome deliberately matches app.py - same title, sidebar and labels - so the
two read as one product. The caption names only the sources actually used: a
claim of knowledge-base or code evidence would be untrue to whoever is watching.

Run:  streamlit run app2.py
"""

import time

import streamlit as st

from src.graph.incident_progress import (
    FIRST_INCIDENT_STEP,
    INCIDENT_ACTIVITIES,
    INCIDENT_PHASES,
    IncidentProgressTracker,
    incident_phase_snapshot
)

from src.graph.incident_workflow import graph

from src.graph.progress import (
    DONE,
    FAILED,
    SKIPPED
)

from src.graph.runner import (
    describe_error,
    stream_workflow
)

from src.ui.evidence import render_evidence_item
from src.ui.flow import render_flow
from src.ui.theme import inject_theme


# -----------------------------------------
# Page config
# -----------------------------------------

st.set_page_config(
    page_title="Agentic RCA Assistant",
    page_icon="🔎",
    layout="wide"
)


st.title(
    "🔎 Agentic Root Cause Analysis Assistant"
)


st.caption(
    """
    Multi-Agent RCA System using LangGraph + ServiceNow incident evidence
    """
)


inject_theme()


# -----------------------------------------
# Sidebar
# -----------------------------------------

with st.sidebar:

    st.header(
        "Workflow"
    )

    st.markdown(
        """

        **Agents**

        1. Query Analyzer  
        2. Clarification Agent  
        3. ServiceNow Retriever  
        4. ServiceNow Evaluator  
        5. Evidence Aggregator  
        6. RCA Agent  
        7. Validation Agent

        """
    )

    st.divider()

    st.info(
        "Powered by LangGraph Agent Workflow"
    )


# -----------------------------------------
# Input
# -----------------------------------------

query = st.text_area(

    "Describe Production Incident",

    placeholder="""

Example:

Batch job abended overnight with S0C7
on the inventory update

""",

    height=160

)


submit = st.button(
    "Generate RCA"
)


if submit:

    if not query.strip():

        st.warning(
            "Please enter incident details"
        )

        st.stop()

    # -------------------------------------
    # Live workflow progress
    # -------------------------------------

    flow_slot = st.empty()

    tracker = IncidentProgressTracker()

    tracker.start(
        FIRST_INCIDENT_STEP
    )

    result = None

    failure = None

    start = time.time()

    def paint(headline):

        detail = None

        if tracker.active and failure is None:
            detail = INCIDENT_ACTIVITIES.get(
                tracker.active
            )

        steps = tracker.snapshot()

        settled = sum(
            1
            for step in steps
            if step["status"] in (DONE, SKIPPED, FAILED)
        )

        flow_slot.markdown(

            render_flow(
                incident_phase_snapshot(steps),
                headline,
                detail,
                time.time() - start,
                progress=settled / max(len(steps), 1)
            ),

            unsafe_allow_html=True

        )

    paint(
        "Starting investigation"
    )

    for event in stream_workflow(
        graph,
        {"user_query": query}
    ):

        if event["type"] == "node_end":

            tracker.observe(
                event["node"],
                event["delta"]
            )

        elif event["type"] == "state":

            tracker.merge_state(
                event["state"]
            )

        elif event["type"] == "final":

            tracker.finish()

            result = event["state"] or tracker.state

        elif event["type"] == "error":

            tracker.fail_active()

            failure = event

        elif event["type"] == "busy":

            flow_slot.empty()

            st.warning(
                "An investigation started "
                f"{int(event['elapsed'])} seconds ago is still running. "
                "Please wait for it to finish before starting another one."
            )

            st.stop()

        if failure:

            paint("Investigation failed")

            break

        if result is not None:

            paint("Investigation complete")

            break

        active_phase = next(
            (
                phase
                for phase in incident_phase_snapshot(tracker.snapshot())
                if phase["status"] == "running"
            ),
            None
        )

        if active_phase:

            headline = (
                "Investigating · stage "
                f"{active_phase['position']} of {len(INCIDENT_PHASES)}"
            )

        else:

            headline = "Moving to the next stage"

        paint(
            headline
        )

    end = time.time()

    if failure:

        failed_step = tracker.active_label or "The workflow"

        st.error(
            f"{failed_step} failed · {describe_error(failure['error'])}"
        )

        with st.expander("Error details"):
            st.code(failure["traceback"])

        st.stop()

    # -------------------------------------
    # Not enough information to investigate
    # -------------------------------------

    questions = result.get("clarification_questions") or []

    # Only a run that produced no analysis at all should end on questions. A
    # completed RCA that the validator flagged is still worth showing, with the
    # reviewer's caveats attached.
    if questions and "rca_result" not in result:

        message = (
            "I need a little more before I can search the incident history "
            "reliably.\n\n"
        )

        for question in questions:
            message += f"• {question}\n"

        st.warning(message)

        with st.expander("Agent state"):
            st.write(result)

        st.stop()

    if "rca_result" not in result:

        st.error(
            "RCA could not be generated"
        )

        st.write(
            """
            The workflow finished without reaching the RCA agent. That usually
            means no historical record matched closely enough to analyse.
            """
        )

        with st.expander("Agent state"):
            st.write(result)

        st.stop()

    validation = result.get("validation_result") or {}

    if validation.get("final_decision", "").upper() == "REJECT":

        st.warning(
            f"Analysis completed in {round(end - start, 2)} seconds, "
            "but the reviewer did not approve it. Treat the analysis below as a "
            "lead to check rather than a conclusion."
        )

    else:

        st.success(
            f"Analysis completed in {round(end - start, 2)} seconds"
        )

    rca = result["rca_result"]

    evidence_catalog = result.get(
        "evidence_catalog",
        {}
    )

    # -------------------------------------
    # Result
    # -------------------------------------

    st.subheader("Root cause")

    st.write(rca["root_cause"])

    def as_percentage(score):
        """Confidence as a percentage. The schema asks for 0-1, but a model that
        answers 88 instead of 0.88 should not render as 8800%."""

        try:
            value = float(score)

        except (TypeError, ValueError):
            return "N/A"

        if value <= 1:
            value *= 100

        return f"{round(value)}%"


    column_one, column_two, column_three = st.columns(3)

    with column_one:
        st.metric(
            "RCA confidence",
            as_percentage(rca["confidence_score"])
        )

    with column_two:
        st.metric(
            "Validation",
            result.get("validation_result", {}).get(
                "final_decision",
                "NOT AVAILABLE"
            )
        )

    with column_three:
        st.metric(
            "Records cited",
            len(evidence_catalog)
        )

    # Recurrence is the strongest signal this data carries: a fault seen many
    # times needs a permanent fix rather than another restart.
    recurrence = result.get("recurrence") or {}

    if recurrence.get("repeat_count", 0) > 1:

        st.warning(
            f"**Recurring failure** — \"{recurrence['dominant_cause']}\" appears in "
            f"{recurrence['repeat_count']} of the matched records "
            f"({', '.join(recurrence['tickets'])})."
        )

    related_changes = result.get("related_changes") or []

    if related_changes:

        st.info(
            "**Possibly related changes** — "
            + "; ".join(
                f"{change['ticket_id']} ({', '.join(change['programs'])}): {change['summary']}"
                for change in related_changes
            )
        )

    issues = validation.get("issues_found") or []

    if issues:

        with st.expander(
            f"Reviewer notes ({len(issues)})",
            expanded=validation.get("final_decision", "").upper() == "REJECT"
        ):

            for issue in issues:
                st.markdown(f"- {issue}")

            if questions:

                st.markdown("**What would settle this:**")

                for question in questions:
                    st.markdown(f"- {question}")

    st.subheader("Evidence")

    for item in rca.get("evidence", []):

        st.markdown(
            render_evidence_item(
                item,
                evidence_catalog
            ),
            unsafe_allow_html=True
        )

    st.subheader("Resolution steps")

    for step in rca.get("resolution_steps", []):
        st.markdown(f"✅ {step}")

    st.subheader("Preventive actions")

    for action in rca.get("preventive_actions", []):
        st.markdown(f"🔒 {action}")

    if rca.get("missing_information"):

        st.subheader("What would raise confidence")

        for item in rca["missing_information"]:
            st.markdown(f"❓ {item}")

    with st.expander("View agent trace"):
        st.write(result)
