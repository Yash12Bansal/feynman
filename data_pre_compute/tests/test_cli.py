"""CLI smoke tests — no external dependencies (no Neo4j, no LLM)."""

from __future__ import annotations

from typer.testing import CliRunner

from lecture_pipeline.cli import app

runner = CliRunner()


class TestIngestBookCommand:
    def test_missing_pdf(self):
        result = runner.invoke(app, ["ingest-book", "/nonexistent.pdf", "--subject", "physics"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not found" in str(result.exception or "").lower()

    def test_help(self):
        result = runner.invoke(app, ["ingest-book", "--help"])
        assert result.exit_code == 0
        assert "--subject" in result.output
        assert "--skip-neo4j" in result.output
        assert "--skip-embeddings" in result.output
        assert "--chapters" in result.output

    def test_missing_subject(self):
        result = runner.invoke(app, ["ingest-book", "some.pdf"])
        assert result.exit_code != 0


class TestListChaptersCommand:
    def test_help(self):
        result = runner.invoke(app, ["list-chapters", "--help"])
        assert result.exit_code == 0
        assert "PDF" in result.output or "pdf" in result.output.lower()

    def test_missing_pdf(self):
        result = runner.invoke(app, ["list-chapters", "/nonexistent.pdf"])
        assert result.exit_code != 0


class TestStatsCommand:
    def test_help(self):
        result = runner.invoke(app, ["stats", "--help"])
        assert result.exit_code == 0
        assert "--config" in result.output


class TestQueryCommand:
    def test_help(self):
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output
        assert "Cypher" in result.output or "cypher" in result.output.lower()


class TestValidateCommand:
    def test_help(self):
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--semantic" in result.output

    def test_missing_file(self):
        result = runner.invoke(app, ["validate", "/nonexistent.json"])
        assert result.exit_code != 0
