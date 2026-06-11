"""Tests for the inline narration-marker splitter + target resolver."""

from __future__ import annotations

from feynman.agent.doubt_resolution.narration_markers import (
    FocusFragment,
    TextFragment,
    TraceFragment,
    UnfocusFragment,
    resolve_target,
    split_narration,
    strip_markers,
)


def test_split_orders_text_and_highlights():
    frags = split_narration("A <<FOCUS:x>>here and <<TRACE:y>>there. <<UNFOCUS>>done")
    assert frags == [
        TextFragment("A"),
        FocusFragment(("x",)),
        TextFragment("here and"),
        TraceFragment("y"),
        TextFragment("there."),
        UnfocusFragment(),
        TextFragment("done"),
    ]


def test_focus_co_highlight_splits_on_plus():
    [frag] = split_narration("<<FOCUS:a+b+c>>")
    assert frag == FocusFragment(("a", "b", "c"))


def test_focus_ignores_text_attr_keeps_target():
    [frag] = split_narration("<<FOCUS:hyp|text=the hypotenuse>>")
    assert frag == FocusFragment(("hyp",))


def test_plain_narration_is_one_text_fragment():
    assert split_narration("Just words, no markers.") == [TextFragment("Just words, no markers.")]
    assert split_narration("") == []


def test_strip_markers_leaves_clean_spoken_text():
    assert (
        strip_markers("A <<FOCUS:x>>here and <<TRACE:y>>there. <<UNFOCUS>>done")
        == "A here and there. done"
    )


def test_resolve_target_by_element_id_and_by_role():
    dictionary = {"el_1": {"role": "hypotenuse"}, "el_2": {"role": "opposite"}}
    assert resolve_target("el_1", dictionary) == "el_1"  # direct id
    assert resolve_target("hypotenuse", dictionary) == "el_1"  # role → id
    assert resolve_target("HYPOTENUSE", dictionary) == "el_1"  # case-insensitive role
    assert resolve_target("nope", dictionary) is None  # unknown → dropped
    assert resolve_target("hypotenuse", {}) is None
