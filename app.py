import streamlit as st

import time
from html import escape

from src.graph.workflow import graph


def safe_text(value):

    if value is None:
        return "Not available"

    return escape(str(value))


def render_reference_block(reference):

    fields = []

    if reference.get("location"):
        fields.append(
            f"<div><strong>Location:</strong> {safe_text(reference['location'])}</div>"
        )

    if reference.get("title"):
        fields.append(
            f"<div><strong>Label:</strong> {safe_text(reference['title'])}</div>"
        )

    if reference.get("commit_sha"):
        fields.append(
            f"<div><strong>Commit:</strong> {safe_text(reference['commit_sha'])}</div>"
        )

    if reference.get("pull_request"):
        fields.append(
            f"<div><strong>PR:</strong> {safe_text(reference['pull_request'])}</div>"
        )

    if reference.get("evidence"):
        fields.append(
            f"<div><strong>Why it matters:</strong> {safe_text(reference['evidence'])}</div>"
        )

    return (
        "<div class='source-reference'>"
        f"<div class='source-reference-type'>{safe_text(reference.get('type') or 'reference')}</div>"
        f"{''.join(fields)}"
        "</div>"
    )


def render_source_popover(evidence_map, evidence_ids):

    cards = []

    for evidence_id in evidence_ids:
        source = evidence_map.get(
            evidence_id,
            {}
        )

        metadata = source.get(
            "metadata",
            {}
        )

        fields = [
            f"<div><strong>Source:</strong> {safe_text(metadata.get('source_type_label') or source.get('source_type'))}</div>",
            f"<div><strong>Title:</strong> {safe_text(metadata.get('title'))}</div>",
            f"<div><strong>Location:</strong> {safe_text(metadata.get('location'))}</div>",
            f"<div><strong>Evidence ID:</strong> {safe_text(evidence_id)}</div>"
        ]

        if metadata.get("ticket_id"):
            fields.append(
                f"<div><strong>Ticket:</strong> {safe_text(metadata['ticket_id'])}</div>"
            )

        if metadata.get("page"):
            fields.append(
                f"<div><strong>Page:</strong> {safe_text(metadata['page'])}</div>"
            )

        if metadata.get("repo"):
            fields.append(
                f"<div><strong>Repository:</strong> {safe_text(metadata['repo'])}</div>"
            )

        if metadata.get("excerpt"):
            fields.append(
                f"<div><strong>Excerpt:</strong> {safe_text(metadata['excerpt'])}</div>"
            )

        references = metadata.get(
            "references",
            []
        )

        reference_html = ""

        if references:
            reference_html = (
                "<div class='source-section-title'>References</div>"
                + "".join(
                    render_reference_block(reference)
                    for reference in references
                )
            )

        cards.append(
            "<div class='source-card'>"
            f"<div class='source-card-title'>{safe_text(metadata.get('title') or evidence_id)}</div>"
            f"{''.join(fields)}"
            f"{reference_html}"
            "</div>"
        )

    if not cards:
        cards.append(
            "<div class='source-card'>"
            "<div class='source-card-title'>Source details unavailable</div>"
            "<div>This evidence item was generated without attached provenance metadata.</div>"
            "</div>"
        )

    return "".join(cards)


def render_evidence_item(item, evidence_map):

    statement = safe_text(
        item.get("statement")
    )

    evidence_ids = item.get(
        "evidence_ids",
        []
    )

    popover = render_source_popover(
        evidence_map,
        evidence_ids
    )

    return (
        "<div class='evidence-item'>"
        f"<div class='evidence-text'>{statement}</div>"
        "<div class='evidence-control'>"
        "<div class='evidence-trigger' tabindex='0'>i</div>"
        f"<div class='evidence-popover'>{popover}</div>"
        "</div>"
        "</div>"
    )



# -----------------------------------------
# Page Config
# -----------------------------------------

st.set_page_config(

    page_title="Agentic RCA Assistant",

    page_icon="🔎",

    layout="wide"

)



# -----------------------------------------
# Header
# -----------------------------------------

st.title(
    "🔎 Agentic Root Cause Analysis Assistant"
)


st.caption(
    """
    Multi-Agent RCA System using LangGraph + ServiceNow + SharePoint KB + GitHub code evidence
    """
)

st.markdown(
    """
    <style>
    :root {
        --rca-bg: #07111f;
        --rca-bg-soft: #0c1829;
        --rca-panel: #0f1d31;
        --rca-panel-2: #13243b;
        --rca-border: rgba(120, 160, 220, 0.18);
        --rca-border-strong: rgba(126, 170, 255, 0.32);
        --rca-text: #edf4ff;
        --rca-text-soft: #b3c4dc;
        --rca-accent: #4ea1ff;
        --rca-accent-soft: rgba(78, 161, 255, 0.18);
        --rca-success: #40c38b;
        --rca-shadow: 0 22px 50px rgba(1, 8, 20, 0.45);
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(78, 161, 255, 0.12), transparent 28%),
            radial-gradient(circle at top right, rgba(64, 195, 139, 0.10), transparent 24%),
            linear-gradient(180deg, #09111d 0%, #06101a 100%);
        color: var(--rca-text);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #121824 0%, #0e1520 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    [data-testid="stSidebar"] * {
        color: var(--rca-text);
    }
    [data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(15, 29, 49, 0.92) 0%, rgba(10, 21, 37, 0.96) 100%);
        border: 1px solid var(--rca-border);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }
    div[data-testid="stMetricLabel"] label,
    div[data-testid="stMetricValue"] {
        color: var(--rca-text) !important;
    }
    .stTextArea textarea {
        background: rgba(12, 24, 41, 0.9) !important;
        color: var(--rca-text) !important;
        border: 1px solid var(--rca-border) !important;
        border-radius: 18px !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #2077ff 0%, #37a2ff 100%);
        color: white;
        border: 0;
        border-radius: 999px;
        font-weight: 700;
        padding: 0.65rem 1.25rem;
        box-shadow: 0 10px 30px rgba(32, 119, 255, 0.28);
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #3182ff 0%, #48b1ff 100%);
    }
    .stInfo, .stSuccess, .stWarning, .stError {
        border-radius: 18px;
    }
    .evidence-item {
        position: relative;
        display: flex;
        align-items: stretch;
        gap: 0.9rem;
        margin-bottom: 1rem;
        padding: 1rem 1rem 1rem 1.15rem;
        border: 1px solid var(--rca-border);
        border-radius: 20px;
        background: linear-gradient(180deg, rgba(15, 29, 49, 0.94) 0%, rgba(11, 23, 39, 0.98) 100%);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }
    .evidence-text {
        flex: 1;
        min-width: 0;
        color: var(--rca-text);
        line-height: 1.62;
        font-size: 0.98rem;
    }
    .evidence-control {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .evidence-trigger {
        width: 1.9rem;
        height: 1.9rem;
        border-radius: 999px;
        background: linear-gradient(135deg, #2f7fff 0%, #5cb4ff 100%);
        color: #f8fbff;
        font-size: 0.9rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: help;
        flex-shrink: 0;
        box-shadow: 0 10px 24px rgba(34, 120, 255, 0.22);
        border: 1px solid rgba(255, 255, 255, 0.18);
    }
    .evidence-popover {
        display: none;
        position: absolute;
        top: calc(100% + 12px);
        right: 0;
        width: min(34rem, calc(100vw - 7rem));
        max-width: 34rem;
        max-height: 24rem;
        overflow-y: auto;
        z-index: 20;
        background: linear-gradient(180deg, rgba(8, 17, 29, 0.99) 0%, rgba(13, 25, 41, 0.99) 100%);
        border: 1px solid var(--rca-border-strong);
        border-radius: 20px;
        box-shadow: var(--rca-shadow);
        padding: 0.95rem;
        backdrop-filter: blur(10px);
    }
    .evidence-control:hover .evidence-popover,
    .evidence-control:focus-within .evidence-popover {
        display: block;
    }
    .source-card {
        border: 1px solid rgba(110, 150, 220, 0.16);
        border-radius: 16px;
        padding: 0.9rem;
        background: linear-gradient(180deg, rgba(19, 36, 59, 0.96) 0%, rgba(13, 25, 41, 0.98) 100%);
        margin-bottom: 0.8rem;
        color: var(--rca-text);
        font-size: 0.92rem;
        line-height: 1.5;
        overflow-wrap: anywhere;
    }
    .source-card:last-child {
        margin-bottom: 0;
    }
    .source-card-title {
        font-weight: 700;
        color: #f7fbff;
        margin-bottom: 0.55rem;
    }
    .source-card strong {
        color: #95c3ff;
    }
    .source-section-title {
        margin-top: 0.7rem;
        margin-bottom: 0.45rem;
        font-weight: 700;
        color: #d7e8ff;
    }
    .source-reference {
        border-top: 1px solid rgba(145, 180, 235, 0.10);
        margin-top: 0.55rem;
        padding-top: 0.55rem;
    }
    .source-reference-type {
        display: inline-block;
        margin-bottom: 0.4rem;
        padding: 0.18rem 0.55rem;
        border-radius: 999px;
        background: var(--rca-accent-soft);
        color: #8fc2ff;
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    @media (max-width: 1100px) {
        .evidence-popover {
            top: calc(100% + 10px);
            right: -0.5rem;
            width: min(30rem, calc(100vw - 3rem));
            max-width: min(30rem, calc(100vw - 3rem));
        }
    }
    @media (max-width: 680px) {
        .evidence-item {
            align-items: flex-start;
        }
        .evidence-popover {
            position: fixed;
            left: 1rem;
            right: 1rem;
            top: auto;
            bottom: 1rem;
            width: auto;
            max-width: none;
            max-height: 52vh;
        }
        .evidence-control:hover .evidence-popover,
        .evidence-control:focus-within .evidence-popover {
            display: block;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)



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
        5. KB Retriever  
        6. KB Evaluator  
        7. GitHub Decision  
        8. GitHub Investigator  
        9. Evidence Aggregator  
        10. RCA Agent  
        11. Validation Agent

        """
    )


    st.divider()


    st.info(
        "Powered by LangGraph Agent Workflow"
    )



# -----------------------------------------
# Session State
# -----------------------------------------

if "history" not in st.session_state:


    st.session_state.history = []



# -----------------------------------------
# User Input
# -----------------------------------------

query = st.text_area(

    "Describe Production Incident",

    placeholder="""

Example:

Payment Gateway transactions are failing
with timeout errors after yesterday deployment

""",

    height=160

)



submit = st.button(
    "Generate RCA"
)



# -----------------------------------------
# Execute Graph
# -----------------------------------------

if submit:


    if not query.strip():


        st.warning(
            "Please enter incident details"
        )


        st.stop()



    input_state = {

        "user_query": query

    }



    with st.spinner(
        "Agents investigating incident..."
    ):


        start = time.time()


        result = graph.invoke(
            input_state
        )


        end = time.time()



    

    # -------------------------------------
    # Clarification Required
    # -------------------------------------

    if (
        result.get("needs_clarification")
        or result.get("needs_human_input")
    ):

        questions = (
            result.get("clarification_questions")
            or result.get("final_missing_information")
            or result.get("missing_information")
            or []
        )

        FIELD_MAP = {
            "affected service":
                "the affected service, application, or system",

            "affected application":
                "the affected service, application, or system",

            "application":
                "the affected application or service",

            "service":
                "the affected service",

            "specific symptom":
                "the exact symptom being observed (for example timeout, HTTP 500 error, login failure, or high latency)",

            "error message":
                "any error messages or error codes",

            "environment":
                "whether this is occurring in Production, UAT, or another environment",

            "recent changes":
                "whether any deployments or configuration changes were made recently"
        }

        friendly_questions = []

        for q in questions:
            friendly_questions.append(
                FIELD_MAP.get(q.lower().strip(), q)
            )

        message = (
            "I need a little more information before I can generate a reliable "
            "root cause analysis.\n\n"
        )

        if friendly_questions:

            message += (
                "Could you please update the incident description with:\n\n"
            )

            for item in friendly_questions:
                message += f"• {item}\n"

            message += (
                "\nProviding these details helps me retrieve the most relevant "
                "historical incidents and knowledge base articles before generating the RCA."
            )

        else:

            message += (
                "The incident description is too generic. Please include details such as "
                "the affected application or service, the observed issue, any error "
                "messages, and recent deployments or configuration changes."
            )

        st.warning(message)

        with st.expander("Agent State"):
            st.write(result)

        st.stop()


    # -------------------------------------
    # RCA Availability Check
    # -------------------------------------

    if "rca_result" not in result:


        st.error(
            "RCA could not be generated"
        )


        st.write(
            """
            The workflow completed but RCA Agent was not reached.

            Possible reasons:
            - insufficient incident information
            - no relevant evidence found
            - validation rejected RCA
            """
        )


        with st.expander(
            "Debug Workflow State"
        ):


            st.write(
                result
            )


        st.stop()

    # Analysis succeeded only if RCA exists
    st.success(
        f"Analysis completed in {round(end-start,2)} seconds"
    )

    # -------------------------------------
    # RCA Output
    # -------------------------------------

    rca = result["rca_result"]
    evidence_catalog = result.get(
        "evidence_catalog",
        {}
    )


    st.subheader(
        "Root Cause"
    )


    st.write(
        rca[
            "root_cause"
        ]
    )



    col1, col2 = st.columns(
        2
    )


    with col1:


        st.metric(

            "RCA Confidence",

            rca[
                "confidence_score"
            ]

        )


    with col2:


        st.metric(

            "Validation",

            result.get(
                "validation_result",
                {}
            ).get(
                "final_decision",
                "NOT AVAILABLE"
            )

        )



    # -------------------------------------
    # Evidence
    # -------------------------------------


    st.subheader(
        "Evidence"
    )


    for evidence in rca.get(
        "evidence",
        []
    ):
        st.markdown(
            render_evidence_item(
                evidence,
                evidence_catalog
            ),
            unsafe_allow_html=True
        )



    # -------------------------------------
    # Resolution
    # -------------------------------------


    st.subheader(
        "Resolution Steps"
    )


    for step in rca.get(
        "resolution_steps",
        []
    ):


        st.markdown(
            f"✅ {step}"
        )



    # -------------------------------------
    # Prevention
    # -------------------------------------


    st.subheader(
        "Preventive Actions"
    )


    for action in rca.get(
        "preventive_actions",
        []
    ):


        st.markdown(
            f"🔒 {action}"
        )



    # -------------------------------------
    # Debug Expander
    # -------------------------------------


    with st.expander(
        "View Agent Trace"
    ):


        st.write(
            result
        )
