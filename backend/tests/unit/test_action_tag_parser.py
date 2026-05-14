"""Tests for the Phase 4 inline action-tag stream parser."""

from __future__ import annotations

from feynman.agent.action_tag_parser import (
    ALLOWED_VERBS,
    ActionTag,
    ActionTagParser,
)

# ── Basic single-tag parsing ────────────────────────────────────


def test_feed_no_tags_passes_text_through() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed("Hello there.")
    assert clean == "Hello there."
    assert tags == []


def test_feed_empty_chunk_is_noop() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed("")
    assert clean == ""
    assert tags == []


def test_single_tag_in_one_chunk() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('Look at <highlight target="x"/> the side.')
    assert clean == "Look at  the side."
    assert tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_tag_at_start_of_chunk() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<pulse target="x"/> rest')
    assert clean == " rest"
    assert tags == [ActionTag(verb="pulse", attrs={"target": "x"})]


def test_tag_at_end_of_chunk() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('lead <pulse target="x"/>')
    assert clean == "lead "
    assert tags == [ActionTag(verb="pulse", attrs={"target": "x"})]


# ── Cross-chunk buffering ───────────────────────────────────────


def test_tag_split_across_two_chunks() -> None:
    parser = ActionTagParser()
    a_clean, a_tags = parser.feed("Look at <high")
    b_clean, b_tags = parser.feed('light target="x"/> the side.')
    assert a_clean == "Look at "
    assert a_tags == []
    assert b_clean == " the side."
    assert b_tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_tag_split_across_three_chunks() -> None:
    parser = ActionTagParser()
    parts = ["Look <hi", "ghlight ta", 'rget="x"/> done']
    out, all_tags = "", []
    for p in parts:
        c, t = parser.feed(p)
        out += c
        all_tags += t
    assert out == "Look  done"
    assert all_tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_tag_split_byte_by_byte() -> None:
    parser = ActionTagParser()
    src = 'a<pulse target="b"/>c'
    out, all_tags = "", []
    for ch in src:
        c, t = parser.feed(ch)
        out += c
        all_tags += t
    assert out == "ac"
    assert all_tags == [ActionTag(verb="pulse", attrs={"target": "b"})]


# ── Multiple tags ──────────────────────────────────────────────


def test_two_tags_in_one_chunk() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('see <highlight target="a"/> and <highlight target="b"/>.')
    assert clean == "see  and ."
    assert [t.attrs["target"] for t in tags] == ["a", "b"]
    assert all(t.verb == "highlight" for t in tags)


def test_adjacent_tags_no_separator() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<highlight target="a"/><pulse target="b"/>')
    assert clean == ""
    assert len(tags) == 2
    assert tags[0].verb == "highlight"
    assert tags[1].verb == "pulse"


# ── Syntax tolerance ───────────────────────────────────────────


def test_single_quote_attribute_values() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed("<highlight target='x'/>")
    assert clean == ""
    assert tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_extra_whitespace_inside_tag() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<highlight  target = "x"  />')
    assert clean == ""
    assert tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_verb_case_insensitive() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<HIGHLIGHT target="x"/>')
    assert clean == ""
    assert tags == [ActionTag(verb="highlight", attrs={"target": "x"})]


def test_attribute_name_case_preserved() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<highlight Target="x"/>')
    assert clean == ""
    # Attr names preserved as written; dispatcher does its own lookup.
    assert tags == [ActionTag(verb="highlight", attrs={"Target": "x"})]


def test_multiple_attributes() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<callout from="x" text="Hello!" direction="up"/>')
    assert clean == ""
    assert len(tags) == 1
    assert tags[0].verb == "callout"
    assert tags[0].attrs == {"from": "x", "text": "Hello!", "direction": "up"}


def test_attribute_value_containing_less_than() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('<callout from="x" text="if a < b"/>')
    assert clean == ""
    assert tags == [ActionTag(verb="callout", attrs={"from": "x", "text": "if a < b"})]


# ── Unknown verbs ──────────────────────────────────────────────


def test_unknown_verb_is_stripped_no_dispatch() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed('try <wave target="x"/> here')
    # The tag is stripped from TTS so it doesn't reach speech…
    assert clean == "try  here"
    # …but no dispatch is requested.
    assert tags == []


def test_allowlist_is_the_canonical_five() -> None:
    assert frozenset({"highlight", "pulse", "callout", "bracket", "pin"}) == ALLOWED_VERBS


# ── Malformed / orphan / stray ─────────────────────────────────


def test_orphan_open_tag_dropped_on_finalize() -> None:
    parser = ActionTagParser()
    a_clean, a_tags = parser.feed("Look at <high")
    assert a_clean == "Look at "
    assert a_tags == []
    tail = parser.finalize()
    # Orphan fragment is dropped — the LLM stopped mid-tag.
    assert tail == ""


def test_stray_less_than_passes_through_as_text() -> None:
    parser = ActionTagParser()
    clean, tags = parser.feed("if x < 5 then go")
    assert clean == "if x < 5 then go"
    assert tags == []


def test_consecutive_less_than_passes_through() -> None:
    """Stray `<` not followed by a verb letter flushes as text on the spot."""
    parser = ActionTagParser()
    clean, tags = parser.feed("a << b")
    # Both `<` chars are followed by non-letters (one by `<`, the other by ` `),
    # so neither starts a partial tag. Everything flows to TTS as-is.
    assert clean == "a << b"
    assert tags == []
    assert parser.finalize() == ""


# ── Buffer overflow ────────────────────────────────────────────


def test_buffer_overflow_flushes_as_text() -> None:
    parser = ActionTagParser()
    # 300 chars after an unmatched `<` with no closing `/>`.
    chunk = "<" + ("a" * 300)
    clean, tags = parser.feed(chunk)
    # Overflow triggered — the bad carry is flushed as text.
    assert clean.startswith("<")
    assert len(clean) >= 256
    assert tags == []


# ── Finalize ────────────────────────────────────────────────────


def test_finalize_flushes_pending_safe_text() -> None:
    # Confirms finalize doesn't drop trailing text that wasn't yet flushed.
    # In practice every feed() returns all safe text, so finalize on a
    # fresh-state parser is a no-op.
    parser = ActionTagParser()
    clean, _ = parser.feed("Hello.")
    assert clean == "Hello."
    assert parser.finalize() == ""


def test_finalize_on_empty_parser_is_empty() -> None:
    parser = ActionTagParser()
    assert parser.finalize() == ""


# ── Stream order preservation ──────────────────────────────────


def test_stream_order_three_tags_interleaved_with_text() -> None:
    parser = ActionTagParser()
    src = (
        'First <highlight target="a"/> middle <pulse target="b"/> and last <highlight target="c"/>.'
    )
    # Feed in three jagged pieces.
    pieces = [src[:25], src[25:55], src[55:]]
    clean_total = ""
    tag_targets: list[str] = []
    for p in pieces:
        c, t = parser.feed(p)
        clean_total += c
        tag_targets.extend(tag.attrs["target"] for tag in t)
    assert tag_targets == ["a", "b", "c"]
    # Sanity: tag substrings are not in the cleaned text.
    assert "highlight" not in clean_total
    assert "pulse" not in clean_total
