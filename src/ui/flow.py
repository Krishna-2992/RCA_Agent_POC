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
    border: 1px solid var(--rca-border, rgba(28, 62, 112, 0.16));
    border-radius: 20px;
    padding: 1rem 1.1rem 1.15rem 1.1rem;
    margin-bottom: 1rem;
    background: linear-gradient(180deg, var(--rca-panel-from, #ffffff) 0%, var(--rca-panel-to, #f6f9fe) 100%);
    box-shadow: inset 0 1px 0 var(--rca-inset, rgba(11, 29, 52, 0.04));
}
.rca-flow-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.55rem;
    margin-bottom: 0.15rem;
    color: var(--rca-text, #12243d);
    font-size: 0.95rem;
    font-weight: 700;
}
.rca-flow-head .rca-flow-timer {
    color: var(--rca-accent-text, #12559c);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.rca-flow-sub {
    color: var(--rca-text-soft, #41567a);
    font-size: 0.84rem;
    line-height: 1.5;
    margin-bottom: 0.85rem;
    overflow-wrap: anywhere;
}
.rca-flow-bar {
    height: 4px;
    border-radius: 999px;
    background: var(--rca-track, rgba(28, 62, 112, 0.12));
    overflow: hidden;
    margin-bottom: 0.9rem;
}
.rca-flow-bar span {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--rca-accent-strong, #1565d8) 0%, var(--rca-success, #1a8f60) 100%);
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
    background: var(--rca-border-strong, rgba(28, 62, 112, 0.30));
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
    border: 1px solid var(--rca-border, rgba(28, 62, 112, 0.16));
    background: var(--rca-panel-solid, rgba(255, 255, 255, 0.9));
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
    color: var(--rca-text, #12243d);
    background: var(--rca-track, rgba(28, 62, 112, 0.12));
}
.rca-node-body {
    min-width: 0;
}
.rca-node-label {
    display: block;
    font-size: 0.8rem;
    font-weight: 600;
    line-height: 1.25;
    color: var(--rca-text, #12243d);
}
.rca-node-meta {
    display: block;
    margin-top: 0.12rem;
    font-size: 0.7rem;
    color: var(--rca-text-muted, #6b7f9e);
    font-variant-numeric: tabular-nums;
}
.rca-link {
    flex: 0 0 auto;
    align-self: center;
    width: 1.15rem;
    height: 2px;
    border-radius: 999px;
    background: var(--rca-track, rgba(28, 62, 112, 0.12));
}
.rca-link.is-passed {
    background: var(--rca-success, #1a8f60);
}

.rca-node.is-pending .rca-node-badge {
    color: var(--rca-text-muted, #6b7f9e);
    background: var(--rca-track, rgba(28, 62, 112, 0.12));
}
.rca-node.is-done {
    border-color: var(--rca-success, #1a8f60);
    background: var(--rca-success-bg, rgba(26, 143, 96, 0.10));
}
.rca-node.is-done .rca-node-badge {
    background: var(--rca-success, #1a8f60);
    color: var(--rca-success-fg, #ffffff);
}
.rca-node.is-done .rca-node-label {
    color: var(--rca-success-label, #0f5b3d);
}
.rca-node.is-skipped {
    border-style: dashed;
    border-color: var(--rca-border, rgba(28, 62, 112, 0.16));
    opacity: 0.5;
}
.rca-node.is-failed {
    border-color: var(--rca-danger, #c4302b);
    background: var(--rca-danger-bg, rgba(196, 48, 43, 0.09));
}
.rca-node.is-failed .rca-node-badge {
    background: var(--rca-danger, #c4302b);
    color: var(--rca-danger-fg, #ffffff);
}
.rca-node.is-running {
    border-color: var(--rca-accent, #1565d8);
    background: var(--rca-running-bg, rgba(21, 101, 216, 0.10));
    box-shadow: 0 0 0 1px var(--rca-accent-soft, rgba(21, 101, 216, 0.12));
}
.rca-node.is-running .rca-node-label {
    color: var(--rca-running-label, #0b1d34);
}
.rca-node.is-running .rca-node-meta {
    color: var(--rca-accent-text, #12559c);
}
.rca-node.is-running .rca-node-badge {
    background: transparent;
    border: 2px solid var(--rca-track, rgba(28, 62, 112, 0.12));
    border-top-color: var(--rca-accent, #1565d8);
    animation: rca-spin 0.9s linear infinite;
}
.rca-node.is-running .rca-node-meta::after {
    content: "";
    display: inline-block;
    margin-left: 0.3rem;
    width: 0.32rem;
    height: 0.32rem;
    border-radius: 999px;
    background: var(--rca-accent, #1565d8);
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
