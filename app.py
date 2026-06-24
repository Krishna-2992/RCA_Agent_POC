import streamlit as st

import time

from src.graph.workflow import graph



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
    Multi-Agent RCA System using LangGraph + ServiceNow RAG + SharePoint Knowledge Base
    """
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
        7. Evidence Aggregator  
        8. RCA Agent  
        9. Validation Agent

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



    st.success(
        f"Analysis completed in {round(end-start,2)} seconds"
    )


    # -------------------------------------
    # Clarification Required
    # -------------------------------------

    if (
        result.get("needs_clarification")
        or result.get("needs_human_input")
    ):


        st.warning(
            "Additional information required before RCA generation"
        )


        questions = (
            result.get("clarification_questions")
            or
            result.get("final_missing_information")
            or
            result.get("missing_information")
            or
            []
        )


        if questions:


            st.subheader(
                "Please provide:"
            )


            for question in questions:


                st.markdown(
                    f"- {question}"
                )


        else:


            st.write(
                "The incident description does not contain enough information."
            )


        with st.expander(
            "Agent State"
        ):


            st.write(
                result
            )


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



    # -------------------------------------
    # RCA Output
    # -------------------------------------

    rca = result["rca_result"]


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
            f"- {evidence}"
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