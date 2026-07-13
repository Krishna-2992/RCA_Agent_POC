from pydantic import BaseModel, Field

from src.utils.llm import llm


TARGET_REPOSITORY = "Krishna-2992/Dummy_RCA_Payment_app"


class GitHubDecision(BaseModel):

    need_github: bool = Field(
        description="Whether code-level GitHub investigation is required"
    )

    reasoning: str = Field(
        description="Why GitHub evidence is needed or can be skipped"
    )


structured_llm = llm.with_structured_output(
    GitHubDecision
)


def github_decision_agent(state):

    print(
        "\n--- GitHub Decision Agent ---"
    )


    query = state["user_query"]

    entities = state.get(
        "extracted_entities",
        {}
    )

    servicenow_analysis = state.get(
        "servicenow_analysis",
        ""
    )

    matching_incidents = state.get(
        "matching_incidents",
        []
    )

    kb_docs = state.get(
        "filtered_kb_results",
        []
    )

    prompt = f"""

You are an RCA orchestration agent.

Your task:

Decide whether the workflow should perform
additional GitHub investigation.

Important scope restriction:

If GitHub analysis is performed, it must use ONLY this repository:
{TARGET_REPOSITORY}


Current Incident:

{query}


Extracted Incident Details:

{entities}


ServiceNow Evaluation:

Reasoning:
{servicenow_analysis}

Matching Incidents:
{matching_incidents}


Relevant SharePoint KB Evidence:

{kb_docs}


Choose need_github = True when GitHub analysis would materially
improve the RCA, especially for:

- deployment-related or change-related incidents
- application code regressions
- API/backend errors likely tied to code paths
- cases where ServiceNow and KB evidence are insufficient
- situations where commit or PR history could confirm the cause


Choose need_github = False when:

- historical incidents and KB already provide strong RCA evidence
- the issue is clearly operational with no code-change signal
- GitHub evidence is unlikely to narrow the root cause


Be practical and conservative:

- If code-level validation could meaningfully increase confidence,
  prefer True.
- If the incident explicitly mentions deployment/change,
  prefer True.
- Do not assume any other repository is available.

"""


    response = structured_llm.invoke(
        prompt
    )


    return {
        "need_github":
            response.need_github,

        "github_decision_reasoning":
            response.reasoning
    }
