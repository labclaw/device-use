"""Convert TopSpin HTML documentation to markdown.

One-time conversion tool that parses Bruker TopSpin command reference HTML
pages and produces clean markdown files + a YAML index for the DocRetriever.

Usage::

    python -m device_use.knowledge.converter \\
        --html-dir /opt/topspin5.0.0/prog/docu/english/topspin/html \\
        --output-dir ./docs/commands \\
        --version 5.0.0 \\
        --index-output ./docs/index.yaml
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# HTML parser for TopSpin command pages
# ---------------------------------------------------------------------------

class _RedirectParser(HTMLParser):
    """Extract redirect URL from a TopSpin stub page."""

    def __init__(self) -> None:
        super().__init__()
        self.redirect_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            attr_dict = dict(attrs)
            if attr_dict.get("http-equiv", "").lower() == "refresh":
                content = attr_dict.get("content", "")
                match = re.search(r"url=(.+)", content, re.IGNORECASE)
                if match:
                    self.redirect_url = match.group(1).strip().rstrip('"').rstrip("'")


class _CommandPageParser(HTMLParser):
    """Parse a TopSpin command reference HTML page.

    Extracts: title, breadcrumb, and content sections (NAME, DESCRIPTION,
    INPUT FILES, OUTPUT FILES, USAGE IN AU PROGRAMS, SEE ALSO, INPUT PARAMETERS).
    """

    SECTIONS = {
        "NAME", "DESCRIPTION", "INPUT FILES", "OUTPUT FILES",
        "USAGE IN AU PROGRAMS", "SEE ALSO", "INPUT PARAMETERS",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title: str = ""
        self.breadcrumb_parts: list[str] = []
        self.sections: dict[str, list[str]] = {}

        # Parser state
        self._in_title = False
        self._in_breadcrumb = False
        self._in_h1 = False
        self._in_h2 = False
        self._current_section: str | None = None
        self._current_text: list[str] = []  # section content buffer
        self._heading_text: list[str] = []  # temporary buffer for h1/h2/title text
        self._breadcrumb_text: list[str] = []  # temporary buffer for breadcrumb
        self._tag_stack: list[str] = []
        self._in_li = False
        self._li_value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        self._tag_stack.append(tag)

        if tag == "title":
            self._in_title = True
            self._heading_text = []
        elif tag == "h1":
            self._in_h1 = True
            self._heading_text = []
        elif tag == "h2":
            self._in_h2 = True
            self._heading_text = []
        elif tag == "li" and "breadcrumb-item" in attr_dict.get("class", ""):
            self._in_breadcrumb = True
            self._breadcrumb_text = []
        elif tag == "li" and self._current_section:
            self._in_li = True
            self._li_value = attr_dict.get("value")
            self._current_text.append("\n")
            if self._li_value:
                self._current_text.append(f"{self._li_value}. ")
            else:
                self._current_text.append("- ")
        elif tag == "br":
            if self._current_section:
                self._current_text.append("\n")
        elif tag == "p" and self._current_section:
            self._current_text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if tag == "title":
            self._in_title = False
            self.title = "".join(self._heading_text).strip()
        elif tag == "h1":
            self._in_h1 = False
            if not self.title:
                self.title = "".join(self._heading_text).strip()
        elif tag == "h2":
            self._in_h2 = False
            heading = "".join(self._heading_text).strip()
            if heading.upper() in self.SECTIONS:
                # Save previous section content
                if self._current_section:
                    self.sections[self._current_section] = self._current_text[:]
                self._current_section = heading.upper()
                self._current_text = []
            elif self._current_section:
                # Sub-heading within a section (e.g. abs page has sub-headings in DESCRIPTION)
                self._current_text.append(f"\n### {heading}\n")
        elif tag == "li" and self._in_breadcrumb:
            self._in_breadcrumb = False
            text = "".join(self._breadcrumb_text).strip()
            if text:
                self.breadcrumb_parts.append(text)
        elif tag == "li" and self._in_li:
            self._in_li = False
        elif tag == "article":
            # Finalize last section
            if self._current_section:
                self.sections[self._current_section] = self._current_text[:]

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._heading_text.append(data)
        elif self._in_h1:
            self._heading_text.append(data)
        elif self._in_h2:
            self._heading_text.append(data)
        elif self._in_breadcrumb:
            self._breadcrumb_text.append(data)
        elif self._current_section is not None:
            self._current_text.append(data)


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def _resolve_redirect(html_path: Path) -> Path | None:
    """Resolve a redirect stub to the actual en-US content page.

    Handles case-insensitive path resolution: the redirect URL uses
    ``/prog/docu/English/...`` (capital E) but disk may have lowercase.
    """
    content = html_path.read_text(encoding="utf-8", errors="replace")
    parser = _RedirectParser()
    parser.feed(content)

    if not parser.redirect_url:
        return None

    # Extract the relative path from the URL
    # URL: /prog/docu/English/topspin/html/en-US/{hash}.html
    match = re.search(r"/prog/docu/[Ee]nglish/topspin/html/en-US/(.+\.html)", parser.redirect_url)
    if not match:
        return None

    filename = match.group(1)

    # Try both cases for the parent directory
    html_dir = html_path.parent
    candidates = [
        html_dir / "en-US" / filename,
        html_dir.parent / "English" / "topspin" / "html" / "en-US" / filename,
        html_dir.parent / "english" / "topspin" / "html" / "en-US" / filename,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _section_text(parts: list[str]) -> str:
    """Join text parts and clean up whitespace."""
    text = "".join(parts).strip()
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_commands_and_descriptions(name_text: str) -> list[tuple[str, str]]:
    """Extract (command, description) pairs from NAME section text."""
    pairs: list[tuple[str, str]] = []
    # Pattern: "command - description" on each line
    for line in name_text.split("\n"):
        line = line.strip()
        match = re.match(r"(\S+)\s*[-\u2013\u2014]\s*(.+)", line)
        if match:
            pairs.append((match.group(1), match.group(2).strip()))
    return pairs


def convert_topspin_command(html_path: Path) -> dict | None:
    """Parse a single TopSpin command page.

    Follows redirect stubs to the actual en-US content page, then extracts
    structured data.

    Args:
        html_path: Path to the redirect stub HTML file (e.g. ``efp.html``).

    Returns:
        Dict with command data, or None if the page couldn't be parsed.
    """
    # Resolve redirect to actual content
    content_path = _resolve_redirect(html_path)
    if content_path is None:
        return None

    try:
        content = content_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    parser = _CommandPageParser()
    try:
        parser.feed(content)
    except Exception:
        return None

    if not parser.title:
        return None

    # Check if this is a command page (has NAME section or is under Commands breadcrumb)
    has_name = "NAME" in parser.sections
    is_command = any("Commands" in part for part in parser.breadcrumb_parts)

    if not has_name and not is_command:
        return None

    # Build category from breadcrumb (skip "TopSpin Help" and the command name itself)
    breadcrumb = [p for p in parser.breadcrumb_parts if p not in ("TopSpin Help",)]
    # Remove the last item (the active page title)
    if breadcrumb and breadcrumb[-1] == parser.title:
        breadcrumb = breadcrumb[:-1]
    category = " > ".join(breadcrumb) if breadcrumb else None

    # Extract sections
    name_text = _section_text(parser.sections.get("NAME", []))
    description = _section_text(parser.sections.get("DESCRIPTION", []))
    input_files = _section_text(parser.sections.get("INPUT FILES", []))
    output_files = _section_text(parser.sections.get("OUTPUT FILES", []))
    au_usage = _section_text(parser.sections.get("USAGE IN AU PROGRAMS", []))
    see_also = _section_text(parser.sections.get("SEE ALSO", []))
    input_params = _section_text(parser.sections.get("INPUT PARAMETERS", []))

    # Extract individual commands and descriptions from NAME
    cmd_pairs = _extract_commands_and_descriptions(name_text)

    # Build tags from command names + category keywords
    tags: list[str] = []
    for cmd, _desc in cmd_pairs:
        tags.append(cmd.lower())
    if category:
        for part in category.split(" > "):
            tag = part.strip().lower()
            if tag and tag != "commands":
                tags.append(tag)

    # Build summary from first command description
    summary = ""
    if cmd_pairs:
        summary = cmd_pairs[0][1]
    elif description:
        summary = description[:200]

    # Use the stub filename (without .html) as the canonical name
    name = html_path.stem

    return {
        "name": name,
        "title": parser.title,
        "description": description,
        "breadcrumb": category,
        "input_files": input_files,
        "output_files": output_files,
        "input_parameters": input_params,
        "au_usage": au_usage,
        "see_also": see_also,
        "category": category,
        "tags": tags,
        "summary": summary,
        "commands": cmd_pairs,
    }


def _format_markdown(data: dict) -> str:
    """Format parsed command data as markdown."""
    lines: list[str] = []
    lines.append(f"# {data['title']}\n")

    if data.get("breadcrumb"):
        lines.append(f"**Category:** {data['breadcrumb']}\n")

    if data.get("commands"):
        lines.append("## NAME\n")
        for cmd, desc in data["commands"]:
            lines.append(f"**{cmd}** - {desc}\n")

    if data.get("description"):
        lines.append("\n## DESCRIPTION\n")
        lines.append(data["description"])
        lines.append("")

    if data.get("input_parameters"):
        lines.append("\n## INPUT PARAMETERS\n")
        lines.append(data["input_parameters"])
        lines.append("")

    if data.get("input_files"):
        lines.append("\n## INPUT FILES\n")
        lines.append(data["input_files"])
        lines.append("")

    if data.get("output_files"):
        lines.append("\n## OUTPUT FILES\n")
        lines.append(data["output_files"])
        lines.append("")

    if data.get("au_usage"):
        lines.append("\n## USAGE IN AU PROGRAMS\n")
        lines.append(data["au_usage"])
        lines.append("")

    if data.get("see_also"):
        lines.append("\n## SEE ALSO\n")
        lines.append(data["see_also"])
        lines.append("")

    return "\n".join(lines)


def convert_all_commands(html_dir: Path, output_dir: Path) -> list[dict]:
    """Convert all TopSpin command HTML pages to markdown.

    Args:
        html_dir: Directory containing the redirect stub HTML files
            (e.g. ``/opt/topspin5.0.0/prog/docu/english/topspin/html``).
        output_dir: Directory to write markdown files to.

    Returns:
        List of index entries for building the YAML index.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    errors: list[str] = []
    skipped = 0

    # Get all HTML files in the directory (excluding subdirectories)
    html_files = sorted(html_dir.glob("*.html"))

    for html_path in html_files:
        try:
            data = convert_topspin_command(html_path)
        except Exception as exc:
            errors.append(f"{html_path.name}: {exc}")
            continue

        if data is None:
            skipped += 1
            continue

        # Write markdown
        md_path = output_dir / f"{data['name']}.md"
        md_content = _format_markdown(data)
        md_path.write_text(md_content, encoding="utf-8")

        # Build index entry
        entries.append({
            "path": f"commands/{data['name']}.md",
            "title": data["title"],
            "tags": data["tags"],
            "summary": data["summary"],
            "category": data.get("category"),
        })

    total = len(html_files)
    converted = len(entries)
    print(f"Converted {converted}/{total} pages ({skipped} skipped, {len(errors)} errors)")
    if errors:
        print(f"Errors (first 10):")
        for err in errors[:10]:
            print(f"  - {err}")

    return entries


def build_index(entries: list[dict], version: str, output_path: Path) -> None:
    """Write a YAML index file from the conversion results.

    Args:
        entries: List of page entry dicts from convert_all_commands.
        version: Software version string.
        output_path: Path to write the index.yaml file.
    """
    index_data = {
        "version": version,
        "software": "Bruker TopSpin",
        "pages": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(index_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Index written to {output_path} ({len(entries)} entries)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for converting TopSpin docs."""
    parser = argparse.ArgumentParser(
        description="Convert TopSpin HTML command docs to markdown + YAML index."
    )
    parser.add_argument(
        "--html-dir",
        type=Path,
        required=True,
        help="Directory with TopSpin HTML redirect stubs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write markdown command files.",
    )
    parser.add_argument(
        "--version",
        default="5.0.0",
        help="TopSpin version string (default: 5.0.0).",
    )
    parser.add_argument(
        "--index-output",
        type=Path,
        default=None,
        help="Path to write index.yaml. Defaults to {output-dir}/../index.yaml.",
    )
    args = parser.parse_args()

    index_output = args.index_output or (args.output_dir.parent / "index.yaml")

    entries = convert_all_commands(args.html_dir, args.output_dir)
    if entries:
        build_index(entries, args.version, index_output)


if __name__ == "__main__":
    main()
