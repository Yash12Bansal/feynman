"""Question generation + multi-model judge.

Per topic, we generate 3-5 questions (mix of mcq and solved_example).
Each question is then judged by N models (typically 1 cloud + 2 local Ollama).
If 2/3+ agree on the answer → solution_confidence ≥ 0.66 → ship.
Otherwise → needs_review = true, not served at runtime.

The judge models are configured in config.validation.judge_models.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from ...config import JudgeModelConfig, LLMConfig
from ...llm.base import LLMProvider
from ...llm.factory import create_llm_provider
from ..id_generator import generate_question_uid
from ..models import Question, QuestionSource, QuestionType, Topic

logger = logging.getLogger(__name__)


QUESTION_GEN_SYSTEM_PROMPT = """You are a teacher writing practice questions for a textbook section.

Given the topic's explanation and examples, produce 3-5 questions that test real understanding (not memorisation). Each question must have a definite, correct answer that you commit to.

Return a JSON object with exactly one key "questions" — an array. Each element:

For MCQ:
{
  "name": "short identifier, 1-3 words",
  "type": "mcq",
  "q_text": "the question, written as a teacher would ask it aloud",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer": "the correct option letter only — A, B, C, or D"
}

For a solved-example problem:
{
  "name": "short identifier",
  "type": "solved_example",
  "q_text": "the problem statement",
  "options": [],
  "answer": "the full worked-out solution, walking through the reasoning step by step"
}

Rules:
- The answer must be definitively correct. If you're not sure, don't include the question.
- For MCQ: the correct option must be unambiguously the only right one. Distractors should be plausible but wrong.
- Questions speak in plain English. No symbolic math — say "x squared" not "x^2".
- Mix difficulty across the set: 1-2 conceptual checks, 1-2 application problems, 1 deeper question.
- Return ONLY the JSON. No markdown. No commentary."""


JUDGE_SYSTEM_PROMPT = """You are a careful examiner. You will be given a question and a proposed answer from a textbook. Decide whether the proposed answer is correct.

Return a JSON object with exactly these fields:
- "verdict": "correct" or "incorrect"
- "my_answer": your independently-derived answer (the letter A/B/C/D for MCQ, or a brief solution for problems)
- "reason": one sentence explaining your verdict

Return ONLY the JSON. No markdown. No commentary."""


@dataclass
class QuestionGenerationReport:
    topics_seen: int = 0
    questions_generated: int = 0
    questions_judged: int = 0
    questions_needs_review: int = 0
    topics_skipped_existing: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"Questions — {self.questions_generated} generated from {self.topics_seen} topics, "
            f"{self.questions_judged} judged, "
            f"{self.questions_needs_review} flagged for review, "
            f"{self.topics_skipped_existing} topics skipped, "
            f"{len(self.failures)} failures, "
            f"{self.elapsed_seconds:.1f}s"
        )


class QuestionGenerator:
    def __init__(
        self,
        author_llm: LLMProvider,
        judge_models: list[JudgeModelConfig],
        *,
        concurrency: int = 5,
        agreement_threshold: float = 0.66,
    ):
        self.author = author_llm
        self.judge_models = judge_models
        self.concurrency = concurrency
        self.agreement_threshold = agreement_threshold
        self._judges: list[LLMProvider] | None = None

    def _build_judges(self) -> list[LLMProvider]:
        if self._judges is None:
            self._judges = []
            for jm in self.judge_models:
                cfg = LLMConfig(provider=jm.provider, model=jm.model, temperature=0.0)
                try:
                    self._judges.append(create_llm_provider(cfg))
                except Exception as e:
                    logger.warning("Could not init judge %s/%s: %s", jm.provider, jm.model, e)
        return self._judges

    async def generate_for_topics(
        self,
        topics: list[Topic],
        existing_question_ids: set[str] | None = None,
    ) -> tuple[list[Question], QuestionGenerationReport]:
        existing = existing_question_ids or set()
        report = QuestionGenerationReport(topics_seen=len(topics))
        start = time.monotonic()

        if not topics:
            report.elapsed_seconds = time.monotonic() - start
            return [], report

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._generate_for_one(topic, existing, semaphore, report) for topic in topics]
        results = await asyncio.gather(*tasks)

        questions: list[Question] = []
        for r in results:
            questions.extend(r)
        report.questions_generated = len(questions)

        if questions and self.judge_models:
            await self._judge_all(questions, report)

        report.elapsed_seconds = time.monotonic() - start
        logger.info(report.summary())
        return questions, report

    async def _generate_for_one(
        self,
        topic: Topic,
        existing: set[str],
        semaphore: asyncio.Semaphore,
        report: QuestionGenerationReport,
    ) -> list[Question]:
        async with semaphore:
            try:
                user_prompt = self._build_user_prompt(topic)
                response = await asyncio.to_thread(
                    self.author.generate_json, QUESTION_GEN_SYSTEM_PROMPT, user_prompt,
                )
                data = json.loads(response.content)
                out: list[Question] = []
                for q in data.get("questions", []):
                    name = (q.get("name") or "").strip()
                    q_text = (q.get("q_text") or "").strip()
                    answer = (q.get("answer") or "").strip()
                    type_raw = (q.get("type") or "").strip().lower()
                    options = q.get("options") or []
                    if not (name and q_text and answer):
                        continue
                    if type_raw not in ("mcq", "solved_example"):
                        continue
                    question_id = generate_question_uid(topic.topic_id, name)
                    if question_id in existing:
                        continue
                    out.append(Question(
                        question_id=question_id,
                        q_text=q_text,
                        answer=answer,
                        options=[str(o) for o in options],
                        type=QuestionType(type_raw),
                        source=QuestionSource.GENERATED,
                        linked_topic_ids=[topic.topic_id],
                    ))
                return out
            except Exception as e:
                logger.warning("Question gen failed for %s: %s", topic.topic_id, e)
                report.failures.append(f"{topic.topic_id}: {e}")
                return []

    def _build_user_prompt(self, topic: Topic) -> str:
        return (
            f"## Topic: {topic.topic_name}\n\n"
            f"## Explanation\n{topic.our_understanding}\n\n"
            f"## Examples\n{chr(10).join('- ' + ex for ex in topic.examples)}\n\n"
            f"Generate 3-5 questions. Return JSON with 'questions' array."
        )

    async def _judge_all(
        self, questions: list[Question], report: QuestionGenerationReport
    ) -> None:
        judges = self._build_judges()
        if not judges:
            logger.warning("No judges available — skipping question judgement")
            return

        semaphore = asyncio.Semaphore(self.concurrency)
        await asyncio.gather(
            *[self._judge_one(q, judges, semaphore, report) for q in questions]
        )

    async def _judge_one(
        self,
        question: Question,
        judges: list[LLMProvider],
        semaphore: asyncio.Semaphore,
        report: QuestionGenerationReport,
    ) -> None:
        async with semaphore:
            user_prompt = self._build_judge_prompt(question)
            verdicts: list[bool] = []

            async def _vote(judge: LLMProvider) -> bool | None:
                try:
                    response = await asyncio.to_thread(
                        judge.generate_json, JUDGE_SYSTEM_PROMPT, user_prompt,
                    )
                    data = json.loads(response.content)
                    return (data.get("verdict") or "").strip().lower() == "correct"
                except Exception as e:
                    logger.debug("Judge failed for %s: %s", question.question_id, e)
                    return None

            results = await asyncio.gather(*[_vote(j) for j in judges])
            for r in results:
                if r is not None:
                    verdicts.append(r)

            report.questions_judged += 1
            if not verdicts:
                question.solution_confidence = 0.0
                question.needs_review = True
                return

            correct_count = sum(1 for v in verdicts if v)
            confidence = correct_count / len(verdicts)
            question.solution_confidence = round(confidence, 3)
            if confidence < self.agreement_threshold:
                question.needs_review = True
                report.questions_needs_review += 1

    def _build_judge_prompt(self, q: Question) -> str:
        options_block = ""
        if q.options:
            options_block = "\n\nOptions:\n" + "\n".join(q.options)
        return (
            f"Question:\n{q.q_text}{options_block}\n\n"
            f"Proposed answer:\n{q.answer}\n\n"
            f"Decide whether the proposed answer is correct."
        )
