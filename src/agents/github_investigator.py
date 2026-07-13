import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent


load_dotenv()


TARGET_REPOSITORY = "Krishna-2992/Dummy_RCA_Payment_app"
MAX_INVESTIGATION_ATTEMPTS = 3


@dataclass
class InvestigationStep:
    timestamp: str
    step_number: int
    event_type: str
    details: Any


@dataclass
class InvestigationState:
    objective: str
    github_user: str
    current_hypothesis: str | None = None
    completed: bool = False
    final_answer: str | None = None
    successful_actions: list = field(default_factory=list)
    failed_actions: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    iterations: int = 0
    steps: list[InvestigationStep] = field(default_factory=list)

    def add_step(self, event_type: str, details: Any):
        self.steps.append(
            InvestigationStep(
                timestamp=datetime.utcnow().isoformat(),
                step_number=len(self.steps) + 1,
                event_type=event_type,
                details=details
            )
        )

    def add_success(self, details):
        self.successful_actions.append(details)
        self.add_step("success", details)

    def add_failure(self, details):
        self.failed_actions.append(details)
        self.add_step("failure", details)


def build_state_context(state: InvestigationState):

    compact_steps = []

    for step in state.steps[-20:]:
        compact_steps.append(
            {
                "step": step.step_number,
                "type": step.event_type,
                "details": step.details
            }
        )

    return f"""
================ INVESTIGATION STATE ================

Objective:
{state.objective}

Current Hypothesis:
{state.current_hypothesis}

Iterations Executed:
{state.iterations}

Successful Actions:
{json.dumps(state.successful_actions[-10:], indent=2, default=str)}

Failed Actions:
{json.dumps(state.failed_actions[-10:], indent=2, default=str)}

Findings:
{json.dumps(state.findings[-10:], indent=2, default=str)}

Recent Investigation History:
{json.dumps(compact_steps, indent=2, default=str)}

Investigation Completed:
{state.completed}

Final Answer:
{state.final_answer}

Use this information to decide:

- what has already been attempted
- which assumptions failed
- which evidence has been collected
- what strategies remain unexplored
- whether enough evidence exists to answer

Tool failures represent failed hypotheses,
not terminal investigation failures.

=====================================================
"""


def should_retry(error: Exception):

    error_text = str(error).lower()

    non_retryable = [
        "rate limit",
        "429",
        "authentication failed",
        "invalid api key",
        "connection refused",
        "500",
        "502",
        "503"
    ]

    retryable = [
        "404",
        "not found",
        "resource not found",
        "pull request",
        "branch not found",
        "commit not found"
    ]

    for item in non_retryable:
        if item in error_text:
            return False

    for item in retryable:
        if item in error_text:
            return True

    return True


def build_objective(state):

    entities = state.get(
        "extracted_entities",
        {}
    )

    servicenow_analysis = state.get(
        "servicenow_analysis",
        ""
    )

    kb_results = state.get(
        "filtered_kb_results",
        []
    )

    return f"""
Perform GitHub code investigation for this production RCA.

Incident:
{state["user_query"]}

Extracted Entities:
{json.dumps(entities, indent=2, default=str)}

ServiceNow Analysis:
{servicenow_analysis}

Relevant KB Evidence:
{json.dumps(kb_results, indent=2, default=str)}

Repository Scope:
Only investigate {TARGET_REPOSITORY}

Your goal:
- inspect the relevant commits, pull requests, files, and code paths
- open the actual files and diffs when required
- connect code changes to the production symptom
- explain the most likely code-level root cause if evidence supports it

Final answer format:
1. GitHub Investigation Summary
2. Files or code paths inspected
3. Key code-level findings
4. Most likely code-related root cause
5. Confidence and limitations
"""


async def load_github_user(github_token: str):

    client = MultiServerMCPClient(
        {
            "github": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-github"
                ],
                "transport": "stdio",
                "env": {
                    "GITHUB_TOKEN": github_token
                }
            }
        }
    )

    tools = await client.get_tools()

    return client, tools


async def run_github_investigation(state):

    openai_api_key = os.getenv(
        "OPENAI_API_KEY"
    )

    github_token = os.getenv(
        "GITHUB_TOKEN"
    )

    github_user = os.getenv(
        "GITHUB_USERNAME",
        "Krishna-2992"
    )

    if not openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY missing"
        )

    if not github_token:
        raise ValueError(
            "GITHUB_TOKEN missing"
        )

    _, tools = await load_github_user(
        github_token
    )

    llm = ChatOpenAI(
        model="gpt-5.1",
        api_key=openai_api_key,
        temperature=0
    )

    agent = create_react_agent(
        model=llm,
        tools=tools,
        debug=False
    )

    objective = build_objective(
        state
    )

    investigation_state = InvestigationState(
        objective=objective,
        github_user=github_user
    )

    github_context = f"""
Authenticated GitHub User:
{github_user}

Only repository that we must be working over is:
{TARGET_REPOSITORY}

Do not investigate any other repository.

You are a GitHub investigation agent supporting
root cause analysis and engineering investigations.

Your objective is to gather evidence from GitHub
and converge on the most likely explanation.

Prefer direct evidence over assumptions.

Do not assume relationships between:
- commits
- pull requests
- branches
- issues
- releases
- deployments

unless evidence exists.

When code-level investigation is needed, open the actual
relevant files or diffs instead of stopping at commit metadata.

Tool failures represent failed hypotheses,
not failed investigations.
"""

    messages = [
        ("system", github_context),
        (
            "system",
            build_state_context(
                investigation_state
            )
        ),
        ("user", objective)
    ]

    final_answer = None

    for attempt in range(
        MAX_INVESTIGATION_ATTEMPTS
    ):

        investigation_state.iterations += 1

        try:

            result = await agent.ainvoke(
                {
                    "messages": messages
                }
            )

            final_answer = result["messages"][-1].content

            investigation_state.final_answer = final_answer
            investigation_state.completed = True

            investigation_state.add_success(
                {
                    "attempt": attempt + 1,
                    "result": "Investigation completed"
                }
            )

            break

        except Exception as error:

            failure_payload = {
                "attempt": attempt + 1,
                "error": str(error)
            }

            investigation_state.add_failure(
                failure_payload
            )

            if not should_retry(error):
                final_answer = (
                    "GitHub investigation stopped due to "
                    f"infrastructure issue: {error}"
                )
                break

            if attempt == MAX_INVESTIGATION_ATTEMPTS - 1:
                final_answer = (
                    "GitHub investigation could not complete after "
                    f"{MAX_INVESTIGATION_ATTEMPTS} attempts: {error}"
                )
                break

            replanning_message = f"""
Previous investigation attempt failed.

Original Objective:
{objective}

Failure:
{str(error)}

This likely indicates:

- an invalid assumption
- an incorrect resource
- an unsuitable tool selection
- missing evidence

Reconsider previous assumptions,
review investigation state,
select an alternative strategy,
and continue the investigation.
"""

            messages.append(
                (
                    "system",
                    build_state_context(
                        investigation_state
                    )
                )
            )

            messages.append(
                (
                    "system",
                    replanning_message
                )
            )

    if not final_answer:
        final_answer = (
            "GitHub investigation completed with no final answer."
        )

    report = {
        "artifact_id":
            "github_investigation_report",
        "artifact_type":
            "investigation_report",
        "repo":
            TARGET_REPOSITORY,
        "summary":
            final_answer,
        "investigation_state":
            asdict(investigation_state)
    }

    return {
        "github_results": [report],
        "filtered_github_results": [report],
        "github_analysis": final_answer
    }


def github_investigator_agent(state):

    print(
        "\n--- GitHub Investigation Agent ---"
    )

    return asyncio.run(
        run_github_investigation(
            state
        )
    )
