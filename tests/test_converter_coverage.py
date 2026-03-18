"""Additional coverage tests for the knowledge converter module.

Targets uncovered lines: 182, 240-241, 246-247, 250, 257, 263, 292-293,
384-386, 393-398, 412-414, 445-477.
"""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

from device_use.knowledge.converter import (
    _CommandPageParser,
    _extract_commands_and_descriptions,
    _format_markdown,
    _RedirectParser,
    _resolve_redirect,
    build_index,
    convert_all_commands,
    convert_topspin_command,
    main,
)

# ===========================================================================
# _resolve_redirect
# ===========================================================================


class TestResolveRedirect:
    def test_url_without_enUS_pattern_returns_none(self, tmp_path):
        """Line 182: redirect URL that doesn't match the en-US regex."""
        stub = tmp_path / "stub.html"
        stub.write_text('<meta http-equiv="refresh" content="0;url=/some/other/path/page.html">')
        result = _resolve_redirect(stub)
        assert result is None

    def test_url_with_uppercase_english(self, tmp_path):
        """_resolve_redirect handles /English/ (capital E) in URL."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content = en_dir / "abc.html"
        content.write_text("<html><body>content</body></html>")

        stub = tmp_path / "stub.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        result = _resolve_redirect(stub)
        assert result is not None
        assert result == content

    def test_url_with_lowercase_english(self, tmp_path):
        """_resolve_redirect handles /english/ (lowercase e) in URL."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content = en_dir / "def.html"
        content.write_text("<html><body>content</body></html>")

        stub = tmp_path / "stub.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/english/topspin/html/en-US/def.html">'
        )
        result = _resolve_redirect(stub)
        assert result is not None
        assert result == content

    def test_fallback_parent_path_resolution(self, tmp_path):
        """_resolve_redirect tries parent/../English/topspin/html/en-US/... path."""
        # Candidate: html_dir.parent / "English" / "topspin" / "html" / "en-US" / file
        # html_dir = stub.parent, so we need stub.parent.parent / "English" / ...
        base = tmp_path / "base"
        base.mkdir()
        stub_dir = base / "html"
        stub_dir.mkdir()

        eng_dir = base / "English" / "topspin" / "html" / "en-US"
        eng_dir.mkdir(parents=True)
        content = eng_dir / "fallback.html"
        content.write_text("<html><body>content</body></html>")

        stub = stub_dir / "stub.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/fallback.html">'
        )
        result = _resolve_redirect(stub)
        assert result is not None
        assert result == content

    def test_no_redirect_meta_at_all(self, tmp_path):
        """_resolve_redirect returns None when there is no meta refresh."""
        stub = tmp_path / "plain.html"
        stub.write_text("<html><head></head><body>Hello</body></html>")
        result = _resolve_redirect(stub)
        assert result is None


# ===========================================================================
# convert_topspin_command
# ===========================================================================


class TestConvertTopspinCommandEdgeCases:
    def _make_valid_stub(self, stub_path: Path, content_path: Path) -> None:
        """Write a redirect stub pointing at content_path.

        The URL format must match what _resolve_redirect expects:
        /prog/docu/English/topspin/html/en-US/{filename}.html
        The filename is extracted from content_path's name.
        """
        filename = content_path.name
        stub_path.write_text(
            f'<meta http-equiv="refresh"'
            f' content="0;url=/prog/docu/English/topspin/html/en-US/{filename}">'
        )

    def test_oserror_reading_content(self, tmp_path):
        """Lines 240-241: OSError when reading the resolved content path."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_file = en_dir / "unreadable.html"
        content_file.write_text("should not be readable")

        stub = tmp_path / "stub.html"
        self._make_valid_stub(stub, content_file)

        # Make the file unreadable
        content_file.chmod(0o000)

        try:
            result = convert_topspin_command(stub)
            assert result is None
        finally:
            content_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_parser_exception_returns_none(self, tmp_path):
        """Lines 246-247: Exception during parser.feed returns None."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_file = en_dir / "bad.html"
        content_file.write_text("<html><head><title>test</title></head><body>ok</body></html>")

        stub = tmp_path / "stub.html"
        self._make_valid_stub(stub, content_file)

        with patch.object(_CommandPageParser, "feed", side_effect=RuntimeError("parse error")):
            result = convert_topspin_command(stub)
        assert result is None

    def test_empty_title_returns_none(self, tmp_path):
        """Line 250: parser.title is empty falsy, returns None."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_html = """
        <html><head><title></title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <h2>NAME</h2><p>cmd - desc</p>
        </article>
        </body></html>
        """
        content_file = en_dir / "notitle.html"
        content_file.write_text(content_html)

        stub = tmp_path / "notitle.html"
        self._make_valid_stub(stub, content_file)

        result = convert_topspin_command(stub)
        assert result is None

    def test_no_name_and_not_command_returns_none(self, tmp_path):
        """Line 257: has no NAME section and no Commands breadcrumb."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_html = """
        <html><head><title>RandomPage</title></head><body>
        <article>
        <li class="breadcrumb-item">Settings</li>
        <h2>DESCRIPTION</h2><p>Some setting page</p>
        </article>
        </body></html>
        """
        content_file = en_dir / "random.html"
        content_file.write_text(content_html)

        stub = tmp_path / "random.html"
        self._make_valid_stub(stub, content_file)

        result = convert_topspin_command(stub)
        assert result is None

    def test_breadcrumb_last_equals_title_is_removed(self, tmp_path):
        """Line 263: breadcrumb[-1] == parser.title triggers removal."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        content_html = """
        <html><head><title>efp</title></head><body>
        <article>
        <li class="breadcrumb-item">TopSpin Help</li>
        <li class="breadcrumb-item">Commands</li>
        <li class="breadcrumb-item">Processing</li>
        <li class="breadcrumb-item">efp</li>
        <h2>NAME</h2><p>efp - Fourier transform</p>
        </article>
        </body></html>
        """
        content_file = en_dir / "efp.html"
        content_file.write_text(content_html)

        stub = tmp_path / "efp.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/efp.html">'
        )

        result = convert_topspin_command(stub)
        assert result is not None
        # The last breadcrumb "efp" should be removed since it equals the title
        assert result["breadcrumb"] == "Commands > Processing"
        assert "efp" not in (result["breadcrumb"] or "").split(" > ")

    def test_description_fallback_summary(self, tmp_path):
        """Lines 292-293: no cmd_pairs but description exists, summary from description[:200]."""
        en_dir = tmp_path / "en-US"
        en_dir.mkdir()
        # NAME section text has no dash-pattern commands, so cmd_pairs will be []
        content_html = """
        <html><head><title>somepage</title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <h2>NAME</h2><p>no dash here</p>
        <h2>DESCRIPTION</h2><p>This is a detailed description for the command page.</p>
        </article>
        </body></html>
        """
        content_file = en_dir / "somepage.html"
        content_file.write_text(content_html)

        stub = tmp_path / "somepage.html"
        self._make_valid_stub(stub, content_file)

        result = convert_topspin_command(stub)
        assert result is not None
        assert result["summary"] == "This is a detailed description for the command page."
        assert result["commands"] == []

    def test_convert_missing_enUS_dir(self, tmp_path):
        """convert_topspin_command returns None when en-US dir is missing."""
        stub = tmp_path / "missing.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/nofile.html">'
        )
        result = convert_topspin_command(stub)
        assert result is None


# ===========================================================================
# convert_all_commands
# ===========================================================================


class TestConvertAllCommandsCoverage:
    def test_exception_in_convert_is_caught(self, tmp_path, capsys):
        """Lines 384-386: exception during convert_topspin_command is caught."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        # Create an en-US dir so redirect resolves, but content will cause error
        en_dir = html_dir / "en-US"
        en_dir.mkdir()
        (en_dir / "err.html").write_text("will trigger error")

        (html_dir / "err.html").write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/err.html">'
        )

        with patch.object(
            convert_topspin_command,
            "__wrapped__" if hasattr(convert_topspin_command, "__wrapped__") else "feed",
            side_effect=RuntimeError("boom"),
            create=True,
        ):
            # Simulate exception by patching _resolve_redirect to return a path
            # and making convert_topspin_command raise
            pass

        # More direct approach: patch convert_topspin_command itself
        original = convert_topspin_command
        with patch(
            "device_use.knowledge.converter.convert_topspin_command",
            side_effect=RuntimeError("boom"),
        ):
            entries = convert_all_commands(html_dir, out_dir)
        assert entries == []
        captured = capsys.readouterr()
        assert "0/" in captured.out

    def test_valid_command_generates_markdown(self, tmp_path):
        """Lines 393-398: successful conversion writes markdown and returns entry."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        en_dir = html_dir / "en-US"
        en_dir.mkdir()

        content_html = """
        <html><head><title>ftest</title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <h2>NAME</h2><p>ftest - Fourier test</p>
        <h2>DESCRIPTION</h2><p>Performs Fourier test.</p>
        </article>
        </body></html>
        """
        (en_dir / "ftest.html").write_text(content_html)

        stub = html_dir / "ftest.html"
        stub.write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/ftest.html">'
        )

        entries = convert_all_commands(html_dir, out_dir)
        assert len(entries) == 1
        assert entries[0]["title"] == "ftest"
        assert entries[0]["tags"] == ["ftest"]

        # Verify markdown was written
        md_file = out_dir / "ftest.md"
        assert md_file.exists()
        md_content = md_file.read_text()
        assert "# ftest" in md_content
        assert "## NAME" in md_content

    def test_multiple_valid_html_files(self, tmp_path):
        """convert_all_commands processes multiple valid files."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        en_dir = html_dir / "en-US"
        en_dir.mkdir()

        for name in ["cmda", "cmdb"]:
            content_html = f"""
            <html><head><title>{name}</title></head><body>
            <article>
            <li class="breadcrumb-item">Commands</li>
            <h2>NAME</h2><p>{name} - Test command</p>
            </article>
            </body></html>
            """
            (en_dir / f"{name}.html").write_text(content_html)
            (html_dir / f"{name}.html").write_text(
                f'<meta http-equiv="refresh"'
                f' content="0;url=/prog/docu/English/topspin/html/en-US/{name}.html">'
            )

        entries = convert_all_commands(html_dir, out_dir)
        assert len(entries) == 2
        assert (out_dir / "cmda.md").exists()
        assert (out_dir / "cmdb.md").exists()

    def test_errors_print_first_10(self, tmp_path, capsys):
        """Lines 412-414: error printing shows first 10 errors."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        # Create 15 files that will all cause exceptions
        for i in range(15):
            (html_dir / f"err{i}.html").write_text("bad content")

        with patch(
            "device_use.knowledge.converter.convert_topspin_command",
            side_effect=RuntimeError(f"error {i}"),
        ):
            entries = convert_all_commands(html_dir, out_dir)

        assert entries == []
        captured = capsys.readouterr()
        assert "Errors (first 10):" in captured.out
        # Only first 10 errors should be listed
        error_lines = [line for line in captured.out.split("\n") if line.strip().startswith("-")]
        assert len(error_lines) == 10


# ===========================================================================
# _format_markdown
# ===========================================================================


class TestFormatMarkdownEdgeCases:
    def test_commands_present_without_description(self):
        """Markdown includes NAME section even when description is empty."""
        data = {
            "title": "cmd",
            "breadcrumb": None,
            "commands": [("cmd", "desc")],
            "description": "",
            "input_parameters": "",
            "input_files": "",
            "output_files": "",
            "au_usage": "",
            "see_also": "",
        }
        md = _format_markdown(data)
        assert "## NAME" in md
        assert "**cmd** - desc" in md
        assert "## DESCRIPTION" not in md

    def test_all_optional_sections_present(self):
        """When all optional fields have values, all sections appear."""
        data = {
            "title": "full",
            "breadcrumb": "Category > Sub",
            "commands": [("full", "Full command")],
            "description": "Full description text",
            "input_parameters": "param1, param2",
            "input_files": "input.dat",
            "output_files": "output.dat",
            "au_usage": "XCMD",
            "see_also": "apk, efp",
        }
        md = _format_markdown(data)
        assert "**Category:** Category > Sub" in md
        assert "## INPUT PARAMETERS" in md
        assert "## INPUT FILES" in md
        assert "## OUTPUT FILES" in md
        assert "## USAGE IN AU PROGRAMS" in md
        assert "## SEE ALSO" in md
        assert "apk, efp" in md


# ===========================================================================
# _CommandPageParser edge cases
# ===========================================================================


class TestCommandPageParserEdgeCases:
    def test_malformed_html_unclosed_tags(self):
        """Parser handles malformed HTML with unclosed tags gracefully."""
        html = """
        <html><head><title>test</title></head><body>
        <article>
        <h2>NAME</h2><p>cmd - description
        <h2>DESCRIPTION</h2><p>No closing tags here
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert parser.title == "test"
        assert "NAME" in parser.sections

    def test_nested_tags_in_section(self):
        """Parser handles nested tags within sections."""
        html = """
        <html><head><title>nested</title></head><body>
        <article>
        <h2>DESCRIPTION</h2>
        <p>Some <b>bold</b> and <i>italic</i> text</p>
        <p>Another paragraph</p>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "DESCRIPTION" in parser.sections
        text = "".join(parser.sections["DESCRIPTION"])
        assert "bold" in text
        assert "italic" in text

    def test_multiple_h2_sections_finalized(self):
        """The last section gets finalized on article close."""
        html = """
        <html><head><title>multi</title></head><body>
        <article>
        <h2>NAME</h2><p>multi - multiple sections</p>
        <h2>DESCRIPTION</h2><p>Description text here</p>
        <h2>SEE ALSO</h2><p>apk efp</p>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert "SEE ALSO" in parser.sections
        assert "apk efp" in "".join(parser.sections["SEE ALSO"])

    def test_h1_without_preceding_title(self):
        """h1 sets title when title tag was absent or empty."""
        html = """
        <html><body>
        <article>
        <h1>CommandName</h1>
        <h2>NAME</h2><p>CommandName - desc</p>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        assert parser.title == "CommandName"

    def test_li_with_value_attribute(self):
        """List items with value= attribute get numbered prefix."""
        html = """
        <html><head><title>listval</title></head><body>
        <article>
        <h2>DESCRIPTION</h2>
        <li value="1">first</li>
        <li value="2">second</li>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        text = "".join(parser.sections.get("DESCRIPTION", []))
        assert "1." in text
        assert "2." in text

    def test_li_without_value_gets_dash(self):
        """List items without value attribute get dash prefix."""
        html = """
        <html><head><title>listdash</title></head><body>
        <article>
        <h2>DESCRIPTION</h2>
        <li>item one</li>
        <li>item two</li>
        </article>
        </body></html>
        """
        parser = _CommandPageParser()
        parser.feed(html)
        text = "".join(parser.sections.get("DESCRIPTION", []))
        assert "- item one" in text
        assert "- item two" in text


# ===========================================================================
# _extract_commands_and_descriptions
# ===========================================================================


class TestExtractCommandsEdgeCases:
    def test_no_dash_on_line(self):
        """Lines without dash pattern are skipped."""
        text = "efp Fourier transform\napk Auto phase"
        pairs = _extract_commands_and_descriptions(text)
        assert pairs == []

    def test_multiple_spaces_around_dash(self):
        """Multiple spaces around the dash still match."""
        text = "efp    -    Fourier transform"
        pairs = _extract_commands_and_descriptions(text)
        assert len(pairs) == 1
        assert pairs[0] == ("efp", "Fourier transform")

    def test_em_dash_and_en_dash(self):
        """Unicode em-dash and en-dash are recognized as separators."""
        text = "efp \u2013 Fourier transform\napk \u2014 Auto phase"
        pairs = _extract_commands_and_descriptions(text)
        assert len(pairs) == 2
        assert pairs[0] == ("efp", "Fourier transform")
        assert pairs[1] == ("apk", "Auto phase")

    def test_only_whitespace_lines(self):
        """Lines that are only whitespace produce no pairs."""
        text = "   \n\n  \t  \n"
        pairs = _extract_commands_and_descriptions(text)
        assert pairs == []

    def test_single_word_no_dash(self):
        """A single word line with no dash produces no pairs."""
        text = "efp"
        pairs = _extract_commands_and_descriptions(text)
        assert pairs == []


# ===========================================================================
# _RedirectParser edge cases
# ===========================================================================


class TestRedirectParserEdgeCases:
    def test_uppercase_REFRESH(self):
        """http-equiv='REFRESH' (uppercase) is matched case-insensitively."""
        html = (
            '<meta http-equiv="REFRESH"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url == "/prog/docu/English/topspin/html/en-US/abc.html"

    def test_mixed_case_http_equiv(self):
        """Mixed case http-equiv is handled."""
        html = (
            '<meta http-equiv="Refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url == "/prog/docu/English/topspin/html/en-US/abc.html"

    def test_url_with_trailing_quote(self):
        """Trailing double-quote in URL is stripped."""
        html = (
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert not parser.redirect_url.endswith('"')

    def test_url_with_trailing_single_quote(self):
        """Trailing single-quote in URL is stripped."""
        html = (
            "<meta http-equiv='refresh'"
            " content='0;url=/prog/docu/English/topspin/html/en-US/abc.html'>"
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert not parser.redirect_url.endswith("'")

    def test_url_with_url_uppercase(self):
        """URL= in uppercase is matched (case-insensitive)."""
        html = (
            '<meta http-equiv="refresh"'
            ' content="0;URL=/prog/docu/English/topspin/html/en-US/abc.html">'
        )
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url == "/prog/docu/English/topspin/html/en-US/abc.html"

    def test_no_url_in_content(self):
        """Meta refresh with content but no url= part."""
        html = '<meta http-equiv="refresh" content="5">'
        parser = _RedirectParser()
        parser.feed(html)
        assert parser.redirect_url is None


# ===========================================================================
# build_index
# ===========================================================================


class TestBuildIndexCoverage:
    def test_multiple_entries(self, tmp_path):
        """build_index writes all entries to YAML."""
        entries = [
            {
                "path": "commands/efp.md",
                "title": "efp",
                "tags": ["efp", "processing"],
                "summary": "FFT",
                "category": "Processing",
            },
            {
                "path": "commands/apk.md",
                "title": "apk",
                "tags": ["apk", "processing"],
                "summary": "Auto phase",
                "category": "Processing",
            },
        ]
        output_path = tmp_path / "docs" / "index.yaml"
        build_index(entries, "5.0.0", output_path)
        assert output_path.exists()
        import yaml

        data = yaml.safe_load(output_path.read_text())
        assert len(data["pages"]) == 2
        assert data["software"] == "Bruker TopSpin"

    def test_creates_parent_dirs(self, tmp_path):
        """build_index creates parent directories if they don't exist."""
        output_path = tmp_path / "a" / "b" / "c" / "index.yaml"
        build_index([], "1.0", output_path)
        assert output_path.exists()


# ===========================================================================
# main() CLI
# ===========================================================================


class TestMainCLI:
    def test_main_with_valid_files(self, tmp_path, capsys):
        """Lines 445-477: main() CLI entry point."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        en_dir = html_dir / "en-US"
        en_dir.mkdir()

        content_html = """
        <html><head><title>clidemo</title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <h2>NAME</h2><p>clidemo - CLI demo command</p>
        </article>
        </body></html>
        """
        (en_dir / "clidemo.html").write_text(content_html)
        (html_dir / "clidemo.html").write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/clidemo.html">'
        )

        with patch(
            "sys.argv",
            [
                "converter",
                "--html-dir",
                str(html_dir),
                "--output-dir",
                str(out_dir),
                "--version",
                "5.0.0",
            ],
        ):
            main()

        captured = capsys.readouterr()
        assert "Converted 1/1" in captured.out
        assert (out_dir / "clidemo.md").exists()
        # Default index output is output_dir.parent / "index.yaml"
        assert (tmp_path / "index.yaml").exists()

    def test_main_with_index_output_flag(self, tmp_path, capsys):
        """main() --index-output flag sets custom index path."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"
        custom_index = tmp_path / "custom" / "index.yaml"

        # Add a valid command so entries are produced and index is written
        en_dir = html_dir / "en-US"
        en_dir.mkdir()
        content_html = """
        <html><head><title>idxcmd</title></head><body>
        <article>
        <li class="breadcrumb-item">Commands</li>
        <h2>NAME</h2><p>idxcmd - Index test</p>
        </article>
        </body></html>
        """
        (en_dir / "idxcmd.html").write_text(content_html)
        (html_dir / "idxcmd.html").write_text(
            '<meta http-equiv="refresh"'
            ' content="0;url=/prog/docu/English/topspin/html/en-US/idxcmd.html">'
        )

        with patch(
            "sys.argv",
            [
                "converter",
                "--html-dir",
                str(html_dir),
                "--output-dir",
                str(out_dir),
                "--index-output",
                str(custom_index),
            ],
        ):
            main()

        captured = capsys.readouterr()
        assert custom_index.exists()

    def test_main_no_entries_no_index(self, tmp_path, capsys):
        """main() with no valid pages does not write an index."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        out_dir = tmp_path / "output"

        (html_dir / "empty.html").write_text("<html><body>no redirect</body></html>")

        with patch(
            "sys.argv",
            [
                "converter",
                "--html-dir",
                str(html_dir),
                "--output-dir",
                str(out_dir),
            ],
        ):
            main()

        captured = capsys.readouterr()
        assert "0/1" in captured.out
        # Index should not be written when there are no entries
        assert not (tmp_path / "index.yaml").exists()
