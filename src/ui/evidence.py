"""Evidence rendering shared by both apps.

The popover shows whatever provenance a source actually carries, so the same
renderer serves a GitHub code reference and a ServiceNow incident with an
extracted root cause.
"""

from html import escape


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
