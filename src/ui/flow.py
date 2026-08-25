"""Horizontal workflow flow strip rendered into a Streamlit placeholder."""

from html import escape

from src.graph.progress import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    SKIPPED
)


SPIN_SECONDS = 0.9


BADGES = {
    DONE: "&#10003;",
    RUNNING: "",
    SKIPPED: "&#8211;",
    FAILED: "!",
    PENDING: ""
}


FLOW_STYLES = """
<style>
.rca-flow-wrap {
    border: 1px solid rgba(120, 160, 220, 0.18);
    border-radius: 20px;
    padding: 1rem 1.1rem 1.15rem 1.1rem;
    margin-bottom: 1rem;
    background: linear-gradient(180deg, rgba(15, 29, 49, 0.92) 0%, rgba(10, 21, 37, 0.96) 100%);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
.rca-flow-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.55rem;
    margin-bottom: 0.15rem;
    color: #edf4ff;
    font-size: 0.95rem;
    font-weight: 700;
}
.rca-flow-head .rca-flow-timer {
    color: #8fc2ff;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.rca-flow-sub {
    color: #b3c4dc;
    font-size: 0.84rem;
    line-height: 1.5;
    margin-bottom: 0.85rem;
    overflow-wrap: anywhere;
}
.rca-flow-bar {
    height: 4px;
    border-radius: 999px;
    background: rgba(120, 160, 220, 0.16);
    overflow: hidden;
    margin-bottom: 0.9rem;
}
.rca-flow-bar span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #2077ff 0%, #40c38b 100%);
    transition: width 0.35s ease;
}
.rca-flow {
    display: flex;
    align-items: stretch;
    gap: 0;
    overflow-x: auto;
    padding-bottom: 0.35rem;
}
.rca-flow::-webkit-scrollbar {
    height: 6px;
}
.rca-flow::-webkit-scrollbar-thumb {
    background: rgba(120, 160, 220, 0.28);
    border-radius: 999px;
}
.rca-node {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 0 0 auto;
    min-width: 9.5rem;
    max-width: 12rem;
    padding: 0.55rem 0.75rem;
    border-radius: 14px;
    border: 1px solid rgba(120, 160, 220, 0.18);
    background: rgba(9, 18, 31, 0.75);
}
.rca-node-badge {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    width: 1.45rem;
    height: 1.45rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    color: #0a1220;
    background: rgba(120, 160, 220, 0.22);
}
.rca-node-body {
    min-width: 0;
}
.rca-node-label {
    display: block;
    font-size: 0.8rem;
    font-weight: 600;
    line-height: 1.25;
    color: #cfdcf0;
}
.rca-node-meta {
    display: block;
    margin-top: 0.12rem;
    font-size: 0.7rem;
    color: #7d90aa;
    font-variant-numeric: tabular-nums;
}
.rca-link {
    flex: 0 0 auto;
    align-self: center;
    width: 1.15rem;
    height: 2px;
    border-radius: 999px;
    background: rgba(120, 160, 220, 0.22);
}
.rca-link.is-passed {
    background: rgba(64, 195, 139, 0.55);
}

.rca-node.is-pending .rca-node-badge {
    color: #93a6bf;
    background: rgba(120, 160, 220, 0.16);
}
.rca-node.is-done {
    border-color: rgba(64, 195, 139, 0.35);
    background: rgba(16, 42, 35, 0.55);
}
.rca-node.is-done .rca-node-badge {
    background: #40c38b;
    color: #04140d;
}
.rca-node.is-done .rca-node-label {
    color: #e6fff4;
}
.rca-node.is-skipped {
    border-style: dashed;
    border-color: rgba(120, 160, 220, 0.2);
    opacity: 0.5;
}
.rca-node.is-failed {
    border-color: rgba(255, 108, 108, 0.5);
    background: rgba(56, 16, 22, 0.6);
}
.rca-node.is-failed .rca-node-badge {
    background: #ff6c6c;
    color: #2a0508;
}
.rca-node.is-running {
    border-color: rgba(78, 161, 255, 0.6);
    background: rgba(14, 38, 68, 0.85);
    box-shadow: 0 0 0 1px rgba(78, 161, 255, 0.18), 0 12px 30px rgba(20, 88, 190, 0.22);
}
.rca-node.is-running .rca-node-label {
    color: #ffffff;
}
.rca-node.is-running .rca-node-meta {
    color: #8fc2ff;
}
.rca-node.is-running .rca-node-badge {
    background: transparent;
    border: 2px solid rgba(143, 194, 255, 0.35);
    border-top-color: #4ea1ff;
    animation: rca-spin 0.9s linear infinite;
}
.rca-node.is-running .rca-node-meta::after {
    content: "";
    display: inline-block;
    margin-left: 0.3rem;
    width: 0.32rem;
    height: 0.32rem;
    border-radius: 999px;
    background: #4ea1ff;
    vertical-align: middle;
}
@keyframes rca-spin {
    to { transform: rotate(360deg); }
}
@media (max-width: 680px) {
    .rca-node {
        min-width: 8.5rem;
    }
}
</style>
"""


def format_duration(seconds):

    if seconds is None:
        return ""

    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)

    remainder = int(seconds % 60)

    return f"{minutes}m {remainder:02d}s"


def _node_html(step):

    status = step["status"]

    badge = BADGES.get(
        status,
        ""
    )

    if status == PENDING:
        badge = str(
            step["position"]
        )

    # The placeholder is repainted every few hundred ms, which remounts the
    # node and would restart the spinner from zero. A negative animation-delay
    # derived from the elapsed time keeps the rotation visually continuous.

    badge_style = ""

    if status == RUNNING:
        meta = format_duration(
            step.get("elapsed")
        )

        elapsed = step.get("elapsed") or 0.0

        badge_style = (
            f" style='animation-delay:{-(elapsed % SPIN_SECONDS):.2f}s'"
        )

    elif status == DONE:
        meta = format_duration(
            step.get("duration")
        )

    elif status == SKIPPED:
        meta = "not required"

    elif status == FAILED:
        meta = "failed"

    else:
        meta = "queued"

    return (
        f"<div class='rca-node is-{status}'>"
        f"<span class='rca-node-badge'{badge_style}>{badge}</span>"
        "<span class='rca-node-body'>"
        f"<span class='rca-node-label'>{escape(step['label'])}</span>"
        f"<span class='rca-node-meta'>{escape(meta)}</span>"
        "</span>"
        "</div>"
    )


def render_flow(steps, headline, detail=None, total_elapsed=None):
    """Builds the flow strip HTML for the given step snapshot."""

    settled = sum(
        1
        for step in steps
        if step["status"] in (DONE, SKIPPED, FAILED)
    )

    percent = int(
        round(
            100 * settled / max(len(steps), 1)
        )
    )

    nodes = []

    for index, step in enumerate(steps):

        if index:

            passed = steps[index - 1]["status"] in (DONE, SKIPPED)

            nodes.append(
                f"<span class='rca-link{' is-passed' if passed else ''}'></span>"
            )

        nodes.append(
            _node_html(step)
        )

    timer = (
        f"<span class='rca-flow-timer'>{escape(format_duration(total_elapsed))}</span>"
        if total_elapsed is not None
        else ""
    )

    sub = (
        f"<div class='rca-flow-sub'>{escape(detail)}</div>"
        if detail
        else "<div class='rca-flow-sub'>&nbsp;</div>"
    )

    return (
        FLOW_STYLES
        + "<div class='rca-flow-wrap'>"
        + f"<div class='rca-flow-head'><span>{escape(headline)}</span>{timer}</div>"
        + sub
        + f"<div class='rca-flow-bar'><span style='width:{percent}%'></span></div>"
        + f"<div class='rca-flow'>{''.join(nodes)}</div>"
        + "</div>"
    )
