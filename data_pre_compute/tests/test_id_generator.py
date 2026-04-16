"""Tests for deterministic semantic ID generation — stability is critical."""

import pytest

from lecture_pipeline.curriculum.id_generator import (
    generate_chapter_uid,
    generate_concept_uid,
    generate_relationship_key,
    generate_subject_uid,
    generate_unit_uid,
    generate_visual_uid,
    slugify,
)


# ---------------------------------------------------------------------------
# Tests: slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert slugify("Simple Harmonic Motion") == "simple_harmonic_motion"

    def test_special_chars(self):
        assert slugify("F = ma (Newton's 2nd Law)") == "f_ma_newton_s_2nd_law"

    def test_unicode(self):
        assert slugify("Schrodinger's Equation") == "schrodinger_s_equation"

    def test_numbers_preserved(self):
        assert slugify("Chapter 12.3") == "chapter_12_3"

    def test_empty_string(self):
        assert slugify("") == ""

    def test_consecutive_specials(self):
        assert slugify("a --- b *** c") == "a_b_c"

    def test_leading_trailing_stripped(self):
        assert slugify("  --hello-- ") == "hello"

    def test_truncation(self):
        long_text = "a " * 100
        result = slugify(long_text)
        assert len(result) <= 80

    def test_deterministic(self):
        """Same input MUST produce same output every time."""
        text = "Energy in Simple Harmonic Motion"
        results = {slugify(text) for _ in range(100)}
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Tests: concept UIDs
# ---------------------------------------------------------------------------


class TestConceptUID:
    def test_basic_concept(self):
        uid = generate_concept_uid("physics", "Simple Harmonic Motion", "Energy in SHM")
        assert uid == "curriculum:physics:simple_harmonic_motion:energy_in_shm"

    def test_with_parent(self):
        uid = generate_concept_uid(
            "physics",
            "Simple Harmonic Motion",
            "Potential Energy Formula",
            parent_concept_name="Energy in SHM",
        )
        assert uid == (
            "curriculum:physics:simple_harmonic_motion"
            ":energy_in_shm:potential_energy_formula"
        )

    def test_deterministic_across_calls(self):
        """CRITICAL: same inputs must always produce same UID."""
        uids = set()
        for _ in range(100):
            uids.add(
                generate_concept_uid("physics", "Simple Harmonic Motion", "Energy in SHM")
            )
        assert len(uids) == 1

    def test_different_concepts_different_uids(self):
        uid1 = generate_concept_uid("physics", "SHM", "Energy")
        uid2 = generate_concept_uid("physics", "SHM", "Damping")
        assert uid1 != uid2

    def test_different_chapters_different_uids(self):
        uid1 = generate_concept_uid("physics", "SHM", "Force")
        uid2 = generate_concept_uid("physics", "Circular Motion", "Force")
        assert uid1 != uid2

    def test_different_subjects_different_uids(self):
        uid1 = generate_concept_uid("physics", "Waves", "Amplitude")
        uid2 = generate_concept_uid("mathematics", "Waves", "Amplitude")
        assert uid1 != uid2


# ---------------------------------------------------------------------------
# Tests: other UID generators
# ---------------------------------------------------------------------------


class TestOtherUIDs:
    def test_chapter_uid(self):
        uid = generate_chapter_uid("physics", "Simple Harmonic Motion")
        assert uid == "curriculum:physics:simple_harmonic_motion"

    def test_unit_uid(self):
        uid = generate_unit_uid("physics", "Oscillations & Waves")
        assert uid == "unit:physics:oscillations_waves"

    def test_subject_uid(self):
        uid = generate_subject_uid("physics")
        assert uid == "subject:physics"

    def test_visual_uid(self):
        concept_uid = "curriculum:physics:shm:energy_in_shm"
        visual_uid = generate_visual_uid(concept_uid)
        assert visual_uid == "visual:physics:shm:energy_in_shm"

    def test_visual_uid_non_curriculum(self):
        uid = generate_visual_uid("custom:something")
        assert uid == "visual:custom:something"

    def test_relationship_key(self):
        key = generate_relationship_key(
            "prerequisite",
            "curriculum:physics:shm:energy",
            "curriculum:physics:shm:math_desc",
        )
        assert key == "rel:prerequisite:curriculum:physics:shm:energy:curriculum:physics:shm:math_desc"

    def test_relationship_key_deterministic(self):
        keys = set()
        for _ in range(100):
            keys.add(
                generate_relationship_key("prerequisite", "a:b", "c:d")
            )
        assert len(keys) == 1
