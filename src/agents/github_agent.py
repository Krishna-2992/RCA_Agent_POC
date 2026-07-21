from pydantic import BaseModel, Field

from src.utils.llm import llm


class GitHubDecision(BaseModel):
    need_github: bool = Field(
        description="Whether GitHub investigation is likely to help RCA"
    )

    reasoning: str = Field(
        description="Why GitHub is or is not useful"
    )

    github_search_query: str | None = Field(
        default=None,
        description="A concise search query to use against GitHub if needed"
    )


structured_llm = llm.with_structured_output(
    GitHubDecision
)


def github_agent(state):
    print("\n--- GitHub Decision Agent ---")

    query = state.get("user_query", "")
    servicenow_analysis = state.get("servicenow_analysis", "")
    kb_reasoning = state.get("kb_evaluation_reasoning", "")

    prompt = f"""
You are a senior SRE/engineer assisting in RCA.

Decide whether consulting GitHub (issues, PRs, commits, releases)
will provide evidence useful for root cause analysis given the
current incident and the evidence already retrieved.

Current Incident:
{query}

ServiceNow analysis:
{servicenow_analysis}

KB analysis:
{kb_reasoning}

Consider whether GitHub artifacts might show:
- recent deploys/commits that correlate with incident time
- open issues or PRs mentioning the failure
- configuration/code changes that explain the regression

Return structured fields:
- need_github: boolean
- reasoning: short explanation
- github_search_query: a short search query to use (or null)
"""

    response = structured_llm.invoke(prompt)

    return {
        "need_github": response.need_github,
        "github_reasoning": response.reasoning,
        "github_search_query": response.github_search_query,
    }