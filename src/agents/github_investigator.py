import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.prebuilt import create_react_agent
from src.utils.llm import llm

load_dotenv()


TARGET_REPOSITORY = "Krishna-2992/Dummy_RCA_Payment_app"
MAX_INVESTIGATION_ATTEMPTS = 3

GITHUB_API = "https://api.github.com"

# Repository map pre-fetch: how much to hand the agent before it starts.
REPO_MAP_COMMITS = 3
REPO_MAP_MAX_FILES = 400
REPO_MAP_MAX_FILES_PER_COMMIT = 25
REPO_MAP_TIMEOUT = 20.0


# ---------------------------------
# Investigation trace (observability only)
# ---------------------------------

TRACE_LOG_PATH = os.getenv(
    "GITHUB_TRACE_LOG",
    "github_investigation_trace.jsonl"
)


def write_trace(event_type: str, payload: Any):

    record = {
        "ts": datetime.utcnow().isoformat(),
        "event": event_type,
        "payload": payload
    }

    try:
        with open(TRACE_LOG_PATH, "a") as handle:
            handle.write(
                json.dumps(record, default=str) + "\n"
            )
            handle.flush()
    except Exception:
        pass


class GitHubTraceCallback(BaseCallbackHandler):
    """Streams every GitHub MCP tool call to the trace log as it happens."""

    def on_tool_start(self, serialized, input_str, **kwargs):
        write_trace(
            "tool_start",
            {
                "tool": (serialized or {}).get("name")
                or kwargs.get("name"),
                "input": str(input_str)[:2000]
            }
        )

    def on_tool_end(self, output, **kwargs):
        text = str(output)
        write_trace(
            "tool_end",
            {
                "output_chars": len(text),
                "output": text[:4000]
            }
        )

    def on_tool_error(self, error, **kwargs):
        write_trace(
            "tool_error",
            {"error": str(error)[:2000]}
        )


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
        "404",
        "not found",
        "resource not found",
        "pull request",
        "branch not found",
        "commit not found",
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
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection closed"
    ]

    for item in non_retryable:
        if item in error_text:
            return False

    for item in retryable:
        if item in error_text:
            return True

    return True


def handle_github_tool_error(error: Exception) -> str:

    error_text = str(error)
    lowered_error = error_text.lower()

    if "not found" in lowered_error or "resource not found" in lowered_error:
        return (
            "GitHub tool error: the requested resource was not found. "
            "Do not repeat the same lookup. Resolve the exact repository object "
            "(file path, branch, PR number, commit SHA, or issue number) using "
            "listing or search-style tools first, then continue."
        )

    return (
        "GitHub tool error: "
        f"{error_text}. "
        "Adjust the investigation strategy and continue without repeating the same call."
    )


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

Return valid JSON only using this schema:
{{
  "summary": "short investigation summary",
  "root_cause": "most likely code-level cause or empty string",
  "confidence": "high|medium|low",
  "limitations": ["..."],
  "references": [
    {{
      "reference_type": "file|pull_request|commit|directory|release|issue",
      "repo": "{TARGET_REPOSITORY}",
      "path": "path/to/file.ext",
      "start_line": 10,
      "end_line": 24,
      "commit_sha": "optional commit sha",
      "pull_request": 123,
      "title": "human readable label",
      "evidence": "what this reference proves"
    }}
  ]
}}

Rules:
- include at least one reference whenever GitHub evidence exists
- use exact repository paths and line numbers when you inspected code
- if line numbers are unavailable, leave them null instead of inventing them
"""


def extract_json_object(text: str) -> dict[str, Any] | None:

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL
    )

    if not match:
        return None

    try:
        return json.loads(
            match.group(0)
        )
    except json.JSONDecodeError:
        return None


def normalize_github_report(
    final_answer: str
) -> dict[str, Any]:

    parsed = extract_json_object(
        final_answer
    ) or {}

    references = parsed.get(
        "references",
        []
    )

    if not isinstance(references, list):
        references = []

    normalized_references = []

    for ref in references:
        if not isinstance(ref, dict):
            continue

        normalized_references.append(
            {
                "reference_type": ref.get(
                    "reference_type",
                    "file"
                ),
                "repo": ref.get(
                    "repo",
                    TARGET_REPOSITORY
                ),
                "path": ref.get("path"),
                "start_line": ref.get(
                    "start_line"
                ),
                "end_line": ref.get(
                    "end_line"
                ),
                "commit_sha": ref.get(
                    "commit_sha"
                ),
                "pull_request": ref.get(
                    "pull_request"
                ),
                "title": ref.get("title"),
                "evidence": ref.get(
                    "evidence"
                )
            }
        )

    return {
        "summary": parsed.get(
            "summary",
            final_answer
        ),
        "root_cause": parsed.get(
            "root_cause",
            ""
        ),
        "confidence": parsed.get(
            "confidence",
            "unknown"
        ),
        "limitations": parsed.get(
            "limitations",
            []
        ),
        "references": normalized_references
    }


def build_mcp_client(github_token: str):

    return MultiServerMCPClient(
        {
            "github": {
                "command": "npx",
                "args": [
                    "-y",
                    "@modelcontextprotocol/server-github"
                ],
                "transport": "stdio",
                "env": {
                    "GITHUB_PERSONAL_ACCESS_TOKEN": github_token
                }
            }
        }
    )


def format_repository_map(repo, head_sha, paths, truncated, commits):

    file_lines = [
        f"  {path}"
        for path in paths[:REPO_MAP_MAX_FILES]
    ]

    if truncated or len(paths) > REPO_MAP_MAX_FILES:
        file_lines.append(
            f"  ... listing truncated at {REPO_MAP_MAX_FILES} of {len(paths)} "
            "files; use discovery tools for anything not listed"
        )

    commit_lines = []

    for commit in commits:

        commit_lines.append(
            f"  {commit['sha'][:8]}  {commit['date']}  {commit['message']}"
        )

        for changed in commit["files"][:REPO_MAP_MAX_FILES_PER_COMMIT]:
            commit_lines.append(
                f"      {changed['status']:9s} +{changed['additions']}/-{changed['deletions']}"
                f"  {changed['filename']}"
            )

        if len(commit["files"]) > REPO_MAP_MAX_FILES_PER_COMMIT:
            remaining = len(commit["files"]) - REPO_MAP_MAX_FILES_PER_COMMIT
            commit_lines.append(
                f"      ... and {remaining} more changed files"
            )

    return f"""
================ REPOSITORY MAP (pre-fetched from the GitHub API) ================

Repository: {repo}
HEAD commit: {head_sha}

Every file in the repository at HEAD:
{chr(10).join(file_lines)}

Most recent {len(commits)} commits and the files each one changed:
{chr(10).join(commit_lines) if commit_lines else "  (commit details unavailable)"}

==================================================================================
"""


async def fetch_repository_map(github_token: str, repo: str = TARGET_REPOSITORY):
    """Hands the agent the repository layout before it starts.

    Without it the agent discovers paths by listing one directory level per LLM
    round trip - six sequential rounds before it can open its first file. This
    is purely additive context: the agent still decides what to read, and an
    empty result simply restores the old discovery behaviour.
    """

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:

        async with httpx.AsyncClient(
            headers=headers,
            timeout=REPO_MAP_TIMEOUT
        ) as client:

            commits_response = await client.get(
                f"{GITHUB_API}/repos/{repo}/commits",
                params={"per_page": REPO_MAP_COMMITS}
            )

            commits_response.raise_for_status()

            commit_list = commits_response.json()

            if not commit_list:
                return ""

            head_sha = commit_list[0]["sha"]

            tree_response, *detail_responses = await asyncio.gather(

                client.get(
                    f"{GITHUB_API}/repos/{repo}/git/trees/{head_sha}",
                    params={"recursive": "1"}
                ),

                *[
                    client.get(
                        f"{GITHUB_API}/repos/{repo}/commits/{commit['sha']}"
                    )
                    for commit in commit_list
                ],

                return_exceptions=True
            )

            if isinstance(tree_response, BaseException):
                raise tree_response

            tree_response.raise_for_status()

            tree = tree_response.json()

            paths = sorted(
                node["path"]
                for node in tree.get("tree", [])
                if node.get("type") == "blob"
            )

            commits = []

            for response in detail_responses:

                if isinstance(response, BaseException):
                    continue

                if response.status_code != 200:
                    continue

                detail = response.json()

                commits.append(
                    {
                        "sha": detail["sha"],
                        "date": detail["commit"]["author"]["date"],
                        "message": detail["commit"]["message"].splitlines()[0][:120],
                        "files": [
                            {
                                "status": item.get("status", "?"),
                                "additions": item.get("additions", 0),
                                "deletions": item.get("deletions", 0),
                                "filename": item.get("filename", "?")
                            }
                            for item in detail.get("files", [])
                        ]
                    }
                )

    except Exception as error:

        write_trace(
            "repository_map_failed",
            {"error": str(error)[:500]}
        )

        return ""

    write_trace(
        "repository_map",
        {
            "files": len(paths),
            "commits": len(commits),
            "head": head_sha
        }
    )

    return format_repository_map(
        repo,
        head_sha,
        paths,
        tree.get("truncated", False),
        commits
    )


async def run_agent_attempts(
    agent,
    messages,
    objective,
    investigation_state
):
    """Runs the ReAct agent, replanning after a retryable failure."""

    final_answer = None

    for attempt in range(
        MAX_INVESTIGATION_ATTEMPTS
    ):

        investigation_state.iterations += 1

        try:

            write_trace(
                "attempt_start",
                {"attempt": attempt + 1}
            )

            result = await agent.ainvoke(
                {
                    "messages": messages
                },
                config={
                    "callbacks": [GitHubTraceCallback()],
                    "recursion_limit": 100
                }
            )

            for message in result["messages"]:

                for call in getattr(
                    message,
                    "tool_calls",
                    []
                ) or []:
                    write_trace(
                        "trajectory_tool_call",
                        {
                            "tool": call.get("name"),
                            "args": call.get("args")
                        }
                    )

            final_answer = result["messages"][-1].content

            write_trace(
                "final_answer",
                {"content": final_answer}
            )

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
                    f"a non-retryable tool error: {error}"
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

    return final_answer


async def run_github_investigation(state):

    github_token = os.getenv(
        "GITHUB_TOKEN"
    )

    github_user = os.getenv(
        "GITHUB_USERNAME",
        "Krishna-2992"
    )

    if not github_token:
        raise ValueError(
            "GITHUB_TOKEN missing"
        )

    client = build_mcp_client(
        github_token
    )

    repository_map = await fetch_repository_map(
        github_token
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
{repository_map}
Investigate thoroughly, but in as few rounds of tool calls as possible.
Being efficient means fewer round trips, not less evidence: read every file
that could plausibly bear on the incident.

- The repository map above is complete and authoritative. Do not list
  directories to discover paths, and do not walk the tree one level at a time.
- Decide which files you need, then request them together in a single batch of
  tool calls rather than one after another.
- Never request the same path twice. You already have its content.
- Use discovery or search tools only for what the map cannot answer, such as
  pull requests, issues, or a path that fails to load.

Do not guess:
- file paths
- branch names
- pull request numbers
- commit SHAs
- issue numbers

Take file paths and commit SHAs from the repository map rather than inferring
them. If a GitHub lookup returns "not found", treat it as an invalid reference.
Resolve the identifier first using broader discovery steps and do not repeat
the same failing lookup.

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

    # One MCP session for the whole investigation. Tools built by
    # client.get_tools() carry no session, so langchain-mcp-adapters spawns a
    # fresh `npx @modelcontextprotocol/server-github` process for EVERY tool
    # call - measured at 1.62s per call versus 0.43s on a shared session.

    async with client.session("github") as session:

        tools = await load_mcp_tools(
            session
        )

        tool_node = ToolNode(
            tools,
            handle_tool_errors=handle_github_tool_error
        )

        agent = create_react_agent(
            model=llm,
            tools=tool_node,
            debug=False
        )

        final_answer = await run_agent_attempts(
            agent,
            messages,
            objective,
            investigation_state
        )

    if not final_answer:
        final_answer = (
            "GitHub investigation completed with no final answer."
        )

    normalized_report = normalize_github_report(
        final_answer
    )

    report = {
        "artifact_id":
            "github_investigation_report",
        "artifact_type":
            "investigation_report",
        "repo":
            TARGET_REPOSITORY,
        "summary":
            normalized_report["summary"],
        "root_cause":
            normalized_report["root_cause"],
        "confidence_label":
            normalized_report["confidence"],
        "limitations":
            normalized_report["limitations"],
        "references":
            normalized_report["references"],
        "investigation_state":
            asdict(investigation_state)
    }

    return {
        "github_results": [report],
        "filtered_github_results": [report],
        "github_analysis": normalized_report["summary"]
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
