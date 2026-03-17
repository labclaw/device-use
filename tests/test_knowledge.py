"""Tests for the knowledge module — converter and retriever."""

from __future__ import annotations

import pytest
import yaml

from device_use.knowledge.converter import (
    _CommandPageParser,
    _extract_commands_and_descriptions,
    _format_markdown,
    _RedirectParser,
    _section_text,
    build_index,
    convert_all_commands,
    convert_topspin_command,
)
from device_use.knowledge.retriever import (
    DocPage,
    DocRetriever,
    _extract_keywords,
    _score_page,
    load_index,
    retrieve_docs,
)

# ===========================================================================
# converter tests
# ===========================================================================


class TestRedirectParser:
    def test_extracts_redirect_url(self):
        html = (
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url == "/prog/docu/English/topspin/html/en-US/abc.html"

    def test_no_redirect(self):
        html = "<html><body>No redirect here</body></html>"
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url is None

    def test_non_refresh_meta(self):
        html = '<meta charset="utf-8">'
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url is None


class TestCommandPageParser:
    def test_extracts_title_from_title_tag(self):
        html = "<html><head><title>efp</title></head><body></body></html>"
        parser = _CommandPageParser()
        parser.feed(html)
        assert parser.title == "efp"

    def test_extracts_title_from_h1(self):
        html = "<html><body><h1>Command efp</h1></body></html>"
        parser = _CommandPageParser()
        parser.feed(html)
        assert parser.title == "Command efp"

    def test_extracts_sections(self):
        html = """
        <html><head><title>efp</title></head><body>
        <article>
        <h2>NAME</h2><p>efp - Fourier transform</p>
        <h2>DESCRIPTION</h2><p>Performs exponential multiplication and FFT.</p>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "NAME" in parser.sections
        assert "DESCRIPTION" in parser.sections

    def test_extracts_breadcrumb(self):
        html = """
        <html><body>
        <li class="breadcrumb-item">Commands</li>
        <li class="breadcrumb-item">Processing</li>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "Commands" in parser.breadcrumb_parts
        assert "Processing" in parser.breadcrumb_parts

    def test_handles_list_items_in_section(self):
        html = """
        <html><head><title>test</title></head><body>
        <article>
        <h2>NAME</h2>
        <li value="1">first item</li>
        <li>second item</li>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "NAME" in parser.sections

    def test_handles_br_and_p_in_section(self):
        html = """
        <html><head><title>test</title></head><body>
        <article>
        <h2>DESCRIPTION</h2>
        line1<br>line2<p>paragraph</p>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "DESCRIPTION" in parser.sections

    def test_sub_heading_within_section(self):
        html = """
        <html><head><title>abs</title></head><body>
        <article>
        <h2>DESCRIPTION</h2>
        Some text
        <h2>SubHeading</h2>
        More text
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        text = "".join(parser.sections.get("DESCRIPTION", []))
        assert "### SubHeading" in text


class TestSectionText:
    def test_joins_and_cleans(self):
        parts = ["Hello", "\n\n\n\n", "World"]
        result = _section_text(parts)
        assert result == "Hello\n\nWorld"


class TestExtractCommandsAndDescriptions:
    def test_extracts_command_dash_description(self):
        text = "efp - Fourier transform\napk - Auto phase correction"
        pairs = _extract_commands_and_descriptions(text)
        assert len(pairs) == 2
        assert pairs[0] == ("efp", "Fourier transform")

    def test_empty_text(self):
        assert _extract_commands_and_descriptions("") == []


class TestConvertTopspinCommand:
    def test_returns_none_for_no_redirect(self, tmp_path):
        (tmp_path / "test.html").write_text("<html><body>No redirect</body></html>")
        result = convert_topspin_command(tmp_path / "test.html")
        assert result is None

    def test_returns_none_for_missing_content(self, tmp_path):
        stub = tmp_path / "efp.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        result = convert_topspin_command(stub)
        assert result is None

    def test_parses_valid_command_page(self, tmp_path):
        # Create en-US dir with content page
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_html = """
        <html><head><title>efp</title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <li class="breadcrumb-item">Processing</li>
        <h2>NAME</h2><p>efp - Fourier transform</p>
        <h2>DESCRIPTION</h2><p>Performs FFT.</p>
        </article>
        </body></html>
        """
        (en_dir / "content.html").write_text(content_html)

        # Create redirect stub
        stub = tmp_path / "efp.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/content.html">'
        )
        result = convert_topspin_command(stub)
        assert result is not None
        assert result["name"] == "efp"
        assert result["title"] == "efp"


class TestFormatMarkdown:
    def test_formats_all_sections(self):
        data = {
            "title": "efp",
            "breadcrumb": "Processing",
            "commands": [("efp", "FFT")],
            "description": "Full desc",
            "input_parameters": "param1",
            "input_files": "file1",
            "output_files": "file2",
            "au_usage": "XCMD",
            "see_also": "apk",
        }
        md = _format_markdown(data)
        assert "# efp" in md
        assert "**Category:** Processing" in md
        assert "## NAME" in md
        assert "## DESCRIPTION" in md
        assert "## INPUT PARAMETERS" in md
        assert "## INPUT FILES" in md
        assert "## OUTPUT FILES" in md
        assert "## USAGE IN AU PROGRAMS" in md
        assert "## SEE ALSO" in md

    def test_formats_minimal(self):
        data = {
            "title": "test",
            "breadcrumb": None,
            "commands": [],
            "description": "",
            "input_parameters": "",
            "input_files": "",
            "output_files": "",
            "au_usage": "",
            "see_also": "",
        }
        md = _format_markdown(data)
        assert "# test" in md


class TestConvertAllCommands:
    def test_converts_directory(self, tmp_path):
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        # Create a dummy HTML file (will be skipped as non-parseable)
        (html_dir / "dummy.html").write_text("<html><body>No command</body></html>")
        entries = convert_all_commands(html_dir, out_dir)
        assert entries == []

    def test_handles_errors(self, tmp_path):
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        # Create a file that will cause a parsing error
        (html_dir / "broken.html").write_bytes(b"\x00\x01\x02")
        entries = convert_all_commands(html_dir, out_dir)
        assert entries == []


class TestBuildIndex:
    def test_writes_yaml_index(self, tmp_path):
        entries = [
            {
                "path": "commands/efp.md",
                "title": "efp",
                "tags": ["efp", "processing"],
                "summary": "FFT",
                "category": "Processing",
            }
        ]
        output_path = tmp_path / "docs" / "index.yaml"
        build_index(entries, "5.0.0", output_path)
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert data["version"] == "5.0.0"
        assert len(data["pages"]) == 1


# ===========================================================================
# retriever tests
# ===========================================================================


class TestExtractKeywords:
    def test_filters_stopwords(self):
        kw = _extract_keywords("the quick brown fox and the lazy dog")
        assert "the" not in kw
        assert "and" not in kw
        assert "quick" in kw
        assert "brown" in kw

    def test_filters_short_words(self):
        kw = _extract_keywords("I am a single x test")
        assert "x" not in kw  # too short

    def test_empty_input(self):
        assert _extract_keywords("") == []

    def test_extracts_numbers(self):
        kw = _extract_keywords("proton 1h spectrum at 400mhz")
        assert "proton" in kw
        assert "1h" in kw
        assert "400mhz" in kw


class TestScorePage:
    def test_scores_tag_match(self):
        page = DocPage(path="efp.md", title="efp", tags=["efp", "processing"], summary="FFT")
        score = _score_page(page, ["efp"])
        assert score == 2.0 + 1.0  # tag + title match

    def test_scores_summary_match(self):
        page = DocPage(path="a.md", title="Other", tags=[], summary="perform fourier transform")
        score = _score_page(page, ["fourier"])
        assert score == 0.5

    def test_no_match(self):
        page = DocPage(path="a.md", title="Unrelated", tags=["abc"], summary="xyz")
        score = _score_page(page, ["efp"])
        assert score == 0.0


class TestDocRetriever:
    def test_query_returns_results(self, tmp_path):
        # Create docs dir with index and a doc file
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "commands").mkdir()

        index_data = {
            "version": "5.0.0",
            "software": "Bruker TopSpin",
            "pages": [
                {
                    "path": "commands/efp.md",
                    "title": "efp",
                    "tags": ["efp", "fourier"],
                    "summary": "Fourier transform",
                }
            ],
        }
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        (docs_dir / "commands" / "efp.md").write_text("# efp\nFourier transform")

        retriever = DocRetriever(docs_dir)
        result = retriever.query("run fourier transform")
        assert "efp" in result
        assert "Bruker TopSpin" in result

    def test_query_no_results(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        index_data = {"version": "5.0.0", "software": "TopSpin", "pages": []}
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        retriever = DocRetriever(docs_dir)
        result = retriever.query("nonexistent command xyz123")
        assert result == ""

    def test_query_empty_keywords(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        index_data = {"version": "5.0.0", "software": "TopSpin", "pages": []}
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        retriever = DocRetriever(docs_dir)
        result = retriever.query("the and is")
        assert result == ""

    def test_query_missing_file(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        index_data = {
            "version": "5.0.0",
            "software": "TopSpin",
            "pages": [
                {
                    "path": "commands/missing.md",
                    "title": "missing command",
                    "tags": ["missing"],
                    "summary": "should be missing",
                }
            ],
        }
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        retriever = DocRetriever(docs_dir)
        result = retriever.query("missing command")
        assert "File not found" in result

    def test_query_max_chars_limit(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "commands").mkdir()

        pages = []
        for i in range(5):
            pages.append(
                {
                    "path": f"commands/cmd{i}.md",
                    "title": f"Command test{i}",
                    "tags": ["test"],
                    "summary": "test command",
                }
            )
            (docs_dir / "commands" / f"cmd{i}.md").write_text("A" * 5000)

        index_data = {"version": "5.0.0", "software": "TopSpin", "pages": pages}
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        retriever = DocRetriever(docs_dir)
        result = retriever.query("test command", max_chars=6000)
        # Should be truncated
        assert len(result) < 30000


class TestLoadIndex:
    def test_loads_valid_index(self, tmp_path):
        index_data = {"version": "5.0.0", "software": "TopSpin", "pages": []}
        with open(tmp_path / "index.yaml", "w") as f:
            yaml.dump(index_data, f)

        idx = load_index(tmp_path)
        assert idx.version == "5.0.0"
        assert idx.software == "TopSpin"

    def test_missing_index(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_index(tmp_path)


class TestRetrieveDocs:
    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = retrieve_docs("nonexistent", "task", skills_dir=tmp_path)
        assert result == ""

    def test_returns_docs_when_present(self, tmp_path):
        docs_dir = tmp_path / "devices" / "my-device" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "commands").mkdir()

        index_data = {
            "version": "1.0",
            "software": "MyDevice",
            "pages": [
                {
                    "path": "commands/cmd.md",
                    "title": "test command",
                    "tags": ["test"],
                    "summary": "a test command",
                }
            ],
        }
        with open(docs_dir / "index.yaml", "w") as f:
            yaml.dump(index_data, f)
        (docs_dir / "commands" / "cmd.md").write_text("# Test\nContent here")

        result = retrieve_docs("my-device", "run test command", skills_dir=tmp_path)
        assert "test command" in result
