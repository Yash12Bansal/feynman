# TODO(DEADCODE): tests parked/dead modules (Group 1/2/3); see docs/engineering/13-redundant-code-audit.md. Safe to delete.
# """Tests for lesson plan data models."""

# from feynman.agent.lesson_plan import ConceptNode, LessonPlan
# from feynman.common.types import Subject


# def _make_concept(title: str = "Test Concept", **kwargs) -> ConceptNode:
#     return ConceptNode(
#         title=title,
#         description=kwargs.get("description", "Teach the basics"),
#         key_points=kwargs.get("key_points", ["point 1", "point 2"]),
#         visual_suggestions=kwargs.get("visual_suggestions", ["show equation"]),
#         estimated_minutes=kwargs.get("estimated_minutes", 5.0),
#     )


# def _make_plan(num_concepts: int = 3) -> LessonPlan:
#     return LessonPlan(
#         topic="Quadratic Equations",
#         subject=Subject.MATH,
#         grade_level="Grade 10",
#         objective="Understand and solve quadratic equations",
#         concepts=[_make_concept(f"Concept {i + 1}") for i in range(num_concepts)],
#     )


# class TestConceptNode:
#     def test_creation(self):
#         c = _make_concept("Newton's Second Law")
#         assert c.title == "Newton's Second Law"
#         assert len(c.key_points) == 2
#         assert len(c.visual_suggestions) == 1

#     def test_defaults(self):
#         c = ConceptNode(
#             title="X",
#             description="Y",
#             key_points=["a"],
#             visual_suggestions=[],
#         )
#         assert c.estimated_minutes == 5.0


# class TestLessonPlan:
#     def test_concept_at_valid(self):
#         plan = _make_plan(3)
#         assert plan.concept_at(0) is not None
#         assert plan.concept_at(0).title == "Concept 1"
#         assert plan.concept_at(2).title == "Concept 3"

#     def test_concept_at_out_of_bounds(self):
#         plan = _make_plan(3)
#         assert plan.concept_at(-1) is None
#         assert plan.concept_at(3) is None
#         assert plan.concept_at(100) is None

#     def test_total_concepts(self):
#         assert _make_plan(0).total_concepts == 0
#         assert _make_plan(1).total_concepts == 1
#         assert _make_plan(5).total_concepts == 5

#     def test_fields(self):
#         plan = _make_plan()
#         assert plan.topic == "Quadratic Equations"
#         assert plan.subject == Subject.MATH
#         assert plan.grade_level == "Grade 10"
#         assert plan.objective == "Understand and solve quadratic equations"

#     def test_optional_fields(self):
#         plan = LessonPlan(
#             topic="Fractions",
#             objective="Learn fractions",
#             concepts=[],
#         )
#         assert plan.subject is None
#         assert plan.grade_level == ""
