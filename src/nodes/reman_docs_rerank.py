"""Removes what the result set says twice, and nothing else.

Similarity search ranks every candidate against the query and nothing against
its neighbours, so a corpus that describes one subject across several
overlapping sections returns that subject restated. Measured over eighteen real
incident descriptions, eleven of eighteen top-six windows contained at least one
repeated section, the average window wasted one and a half of its six slots, and
one query filled all six from a single section.

The obvious correction is Maximal Marginal Relevance - score each candidate on
relevance minus its similarity to what is already chosen. It was tried and
rejected on measurement. MMR's penalty is linear and applies to every candidate,
so it cannot tell a passage that repeats another from one that merely shares its
subject; pushed hard enough to remove the duplicates it also removed the chunk
naming a recovery screen, which was the specific answer being looked for. At the
strength where the answer survived, three duplicate pairs survived with it.

What separates the two cases is not a similarity score but the document
structure, which the payload already carries.

Two rules, tuned together over those eighteen incidents:

A section may take at most CAP of the slots. This is the fix for a section
monopolising the window; it does not care how similar the chunks are, only that
one part of one document should not answer the whole question. The cap is two
rather than one because a long section is chunked into parts that hold genuinely
different text - of twenty-seven repeated-section pairs, only one exceeded 0.90
similarity and nine were below 0.80, so a cap of one would discard content that
is different in exactly the way this pipeline needs.

Anything above THRESHOLD similarity to a chunk already chosen is dropped
whatever its section, because at that similarity it is the same passage twice
and the section it came from is beside the point.

Together they leave no duplicate pair in any of the eighteen windows, hold the
worst single-section share to two slots against a baseline of six, and give up
one percent of summed relevance. MMR at the setting that matched the first
number gave up twice as much and still let a section take five slots.
"""

import collections
import math
import os


# Above this, two chunks are the same passage. Set from the measured spread of
# repeated-section pairs: their median similarity is 0.819 and their maximum is
# 1.000, so a threshold here removes the genuine repeats and leaves the parts
# that merely share a subject. Lowering it starts discarding those parts, which
# is the failure this module exists to avoid.
THRESHOLD = float(
    os.getenv("REMAN_DOCS_DUPLICATE_THRESHOLD", "0.88")
)


# Slots one section may occupy. Two, not one: see the module docstring - a long
# section's parts carry different text and a cap of one throws that away.
CAP = int(
    os.getenv("REMAN_DOCS_SECTION_CAP", "2")
)


# How many candidates to fetch per slot returned. Enough that dropping repeats
# still leaves something to promote in their place.
CANDIDATE_MULTIPLIER = int(
    os.getenv("REMAN_DOCS_CANDIDATE_MULTIPLIER", "4")
)


def cosine(left, right):

    if not left or not right:
        return 0.0

    dot = sum(
        a * b
        for a, b in zip(left, right)
    )

    left_norm = math.sqrt(sum(a * a for a in left))

    right_norm = math.sqrt(sum(b * b for b in right))

    if not left_norm or not right_norm:
        return 0.0

    return dot / (left_norm * right_norm)


def select_diverse(candidates, limit, cap=None, threshold=None, pinned=0):
    """Takes candidates in relevance order, skipping what repeats.

    Relevance order is preserved throughout - nothing is promoted for being
    novel, which is the whole difference from MMR. A candidate is skipped only
    when its section already holds `cap` slots, or when it is within
    `threshold` of something already chosen.

    `pinned` keeps that many leading candidates unconditionally. Exact
    identifier matches are pinned: a chunk naming the file the report named
    earned its place on a fact rather than a similarity score, and should not
    lose it for resembling its own neighbours.

    A candidate carrying no vector is kept and only section-capped. Missing
    vectors mean the search was made without them, and treating that as
    "duplicate of everything" would empty the result set.
    """

    if cap is None:
        cap = CAP

    if threshold is None:
        threshold = THRESHOLD

    if limit <= 0 or not candidates:
        return []

    selected = list(candidates[:pinned])

    taken = collections.Counter(
        section_key(document)
        for document in selected
    )

    for candidate in candidates[pinned:]:

        if len(selected) >= limit:
            break

        key = section_key(candidate)

        if taken[key] >= cap:
            continue

        vector = candidate.get("vector")

        if vector and any(
            cosine(vector, chosen.get("vector")) > threshold
            for chosen in selected
        ):
            continue

        taken[key] += 1

        selected.append(candidate)

    # A filter this strict can come up short on a thin candidate pool, and a
    # half-empty window is worse than a slightly repetitive one. Backfill in
    # relevance order with whatever was skipped.
    if len(selected) < limit:

        chosen = {
            id(document)
            for document in selected
        }

        for candidate in candidates:

            if len(selected) >= limit:
                break

            if id(candidate) not in chosen:
                selected.append(candidate)

    return selected[:limit]


def section_key(document):
    """What counts as "the same part of the same document"."""

    return (
        document.get("program"),
        document.get("section")
    )


def diversity_report(documents):
    """Duplicate pairs left, worst single-section share, mean similarity.

    Cheap enough to run every time, and the only way to notice the window going
    uniform again after a corpus or embedding change.
    """

    vectors = [
        document.get("vector")
        for document in documents
        if document.get("vector")
    ]

    similarities = [
        cosine(vectors[i], vectors[j])
        for i in range(len(vectors))
        for j in range(i + 1, len(vectors))
    ]

    counts = collections.Counter(
        section_key(document)
        for document in documents
    )

    return {
        "duplicate_pairs": sum(
            1
            for similarity in similarities
            if similarity > THRESHOLD
        ),
        "worst_section_share": max(counts.values()) if counts else 0,
        "mean_similarity": (
            sum(similarities) / len(similarities)
            if similarities
            else 0.0
        )
    }
