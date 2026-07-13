import asyncio
import json
import os
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv
from langchain_core.tracers.schemas import Run
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

load_dotenv()


# ============================================================
# Tracing Helpers
# ============================================================

def format_trace_value(value):
    try:
        return json.dumps(value, indent=2, default=str, sort_keys=True)
    except Exception:
        return repr(value)


def log_run(prefix: str, run: Run) -> None:
    print(f"\n=== {prefix} ===")
    print(f"run_id: {run.id}")
    print(f"run_type: {run.run_type}")
    print(f"name: {run.name}")
    print(f"trace_id: {run.trace_id}")

    if run.inputs:
        print("inputs:")
        print(format_trace_value(run.inputs))

    if run.outputs:
        print("outputs:")
        print(format_trace_value(run.outputs))

    if run.error:
        print("error:", run.error)

    if run.events:
        print("events:")
        print(format_trace_value(run.events))


def on_start(run: Run, config=None):
    log_run("RUN START", run)


def on_end(run: Run, config=None):
    log_run("RUN END", run)


def on_error(run: Run, config=None):
    log_run("RUN ERROR", run)


# ============================================================
# Investigation State
# ============================================================

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

    def add_finding(self, finding):
        self.findings.append(finding)
        self.add_step("finding", finding)


def build_state_context(state: InvestigationState):

    compact_steps = []

    for step in state.steps[-20:]:
        compact_steps.append({
            "step": step.step_number,
            "type": step.event_type,
            "details": step.details
        })

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


# ============================================================
# Retry Logic
# ============================================================

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


# ============================================================
# GitHub Context Loading
# ============================================================

headers = {
    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
}

repos_response = requests.get(
    "https://api.github.com/user/repos?per_page=100",
    headers=headers
)

repos_data = repos_response.json()

user_response = requests.get(
    "https://api.github.com/user",
    headers=headers
)

github_username = user_response.json()["login"]


# ============================================================
# Main
# ============================================================

async def main():

    openai_api_key = os.getenv("OPENAI_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY missing")

    if not github_token:
        raise ValueError("GITHUB_TOKEN missing")

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

    print(f"\nLoaded {len(tools)} GitHub tools")

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

    while True:

        question = input("\nQuestion: ")

        if question.lower() in ["exit", "quit"]:
            break

        state = InvestigationState(
            objective=question,
            github_user=github_username,
        )

        github_context = f"""
Authenticated GitHub User:
{github_username}

Only repository that we must be working over is Dummy_RCA_Payment_app

If a repository owner is not specified,
assume repositories belong to {github_username}.

If only a repository name is mentioned,
attempt to resolve using the repository list.

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

Tool failures represent failed hypotheses,
not failed investigations.
"""

        messages = [
            ("system", github_context),
            ("system", build_state_context(state)),
            ("user", question)
        ]

        MAX_INVESTIGATION_ATTEMPTS = 3

        for attempt in range(MAX_INVESTIGATION_ATTEMPTS):

            state.iterations += 1

            print(
                f"\n========== Investigation Attempt "
                f"{attempt + 1}/{MAX_INVESTIGATION_ATTEMPTS} =========="
            )

            try:

                result = await agent.ainvoke(
                    {
                        "messages": messages
                    }
                )

                answer = result["messages"][-1].content

                state.final_answer = answer
                state.completed = True

                state.add_success(
                    {
                        "attempt": attempt + 1,
                        "result": "Investigation completed"
                    }
                )

                print("\nAnswer:\n")
                print(answer)

                break

            except Exception as e:

                # stacktrace = traceback.format_exc()

                error_summary = {
                    "type": type(e).__name__,
                    "message": str(e)
                }

                failure_payload = {
                    "attempt": attempt + 1,
                    "error": str(e)
                }

                state.add_failure(failure_payload)

                print(
                    f"\nAttempt {attempt + 1} failed:"
                )
                print(str(e))

                if not should_retry(e):
                    print(
                        "\nInfrastructure failure detected."
                        "\nStopping investigation."
                    )
                    break

                if attempt == MAX_INVESTIGATION_ATTEMPTS - 1:
                    print(
                        "\nMaximum investigation attempts reached."
                    )
                    break

                replanning_message = f"""
Previous investigation attempt failed.

Original Objective:
{question}

Failure:
{str(e)}

Failure:
{error_summary["type"]}

Message:
{error_summary["message"]}

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
                        build_state_context(state)
                    )
                )

                messages.append(
                    (
                        "system",
                        replanning_message
                    )
                )

        print("\n========== FINAL STATE ==========")
        print(
            json.dumps(
                asdict(state),
                indent=2,
                default=str
            )
        )


if __name__ == "__main__":
    asyncio.run(main())