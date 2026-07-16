"""
YAML Frontmatter Engine for BiliSum

Adapted from Bilibili-Obsidian-Clipper extension/content.js functions:
  - buildFrontMatter()       L4729-4758
  - getEnabledFrontmatterFields() L4760-4775
  - formatFixedPropertyYamlLine() L4906-4943
  - resolveFrontmatterTemplateValue() L4884-4893
  - escapeYaml()             L5198-5199

Usage:
    from yaml_frontmatter import YamlFrontmatter

    fm = YamlFrontmatter(
        title="某视频标题",
        bvid="BV1xx411c7mD",
        cid=123456,
        author="UP主名称",
        upload_date="2025-01-15",
        subtitle_lang="zh-CN",
        tags=["bilibili", "教程"],
        url="https://www.bilibili.com/video/BV1xx411c7mD",
    )

    # Full Obsidian frontmatter (9 default fields)
    yaml_str = fm.build(mode="obsidian")

    # Minimal (title + bvid + author only)
    yaml_str = fm.build(mode="minimal")

    # Template resolution (used internally by build)
    result = fm.resolve_template("Video by {{author}}", context)

    # Property formatting
    line = fm.format_property("score", "number", "95")
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional


class YamlFrontmatter:
    """Generate YAML frontmatter strings for Obsidian/BiliSum notes.

    Mirrors the logic in Bilibili-Obsidian-Clipper's buildFrontMatter()
    and its helper functions, ported to Python.
    """

    # Default ordered field set (mirrors the Obsidian Clipper default config)
    DEFAULT_FIELDS: List[str] = [
        "title",
        "url",
        "bvid",
        "cid",
        "author",
        "upload_date",
        "subtitle_lang",
        "created",
        "tags",
    ]

    # Fields used when mode="minimal"
    MINIMAL_FIELDS: List[str] = ["title", "bvid", "author"]

    # Regex for template variable substitution: {{variable_name}}
    _TEMPLATE_RE: re.Pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    # Regex for YYYY-MM-DD date validation
    _DATE_RE: re.Pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    # Valid keys that can appear in a template context
    _TEMPLATE_KEYS = frozenset({
        "title", "bvid", "author", "url", "upload_date",
        "created", "tags", "tags_csv", "tags_yaml",
    })

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        title: str = "",
        url: str = "",
        bvid: str = "",
        cid: Any = 0,
        author: str = "",
        upload_date: str = "",
        subtitle_lang: str = "",
        created: Optional[str] = None,
        tags: Any = None,
    ) -> None:
        """Initialise with video metadata.

        Parameters
        ----------
        title : str
            Video title.
        url : str
            Full Bilibili video URL.
        bvid : str
            Bilibili BV identifier.
        cid : int | str
            Subtitle/page cid.
        author : str
            Uploader name.
        upload_date : str
            Upload date string (YYYY-MM-DD preferred).
        subtitle_lang : str
            Language code of the selected subtitle (e.g. "zh-CN").
        created : str | None
            ISO-8601 creation timestamp. If None, defaults to today's date.
        tags : list[str] | str | None
            Tags as a list of strings or a pipe/comma-separated string.
        """
        self.title: str = str(title or "")
        self.url: str = str(url or "")
        self.bvid: str = str(bvid or "")
        self.cid: Any = cid
        self.author: str = str(author or "unknown")
        self.upload_date: str = str(upload_date or "unknown")
        self.subtitle_lang: str = str(subtitle_lang or "unknown")

        # created defaults to today's date in ISO format
        if created:
            self.created: str = str(created)
        else:
            self.created = date.today().isoformat()

        # Normalise tags to a list of strings
        self.tags: List[str] = self._normalise_tags(tags)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, mode: str = "obsidian") -> str:
        """Generate YAML frontmatter string delimited by ``---``.

        Parameters
        ----------
        mode : str
            ``"obsidian"`` — all 9 DEFAULT_FIELDS.
            ``"minimal"`` — title, bvid, author only.

        Returns
        -------
        str
            Multi-line YAML frontmatter string, or ``""`` if no fields
            produce output.
        """
        if mode == "minimal":
            fields = list(self.MINIMAL_FIELDS)
        else:
            fields = list(self.DEFAULT_FIELDS)

        return self._build_from_fields(fields)

    def format_property(self, key: str, field_type: str, value: Any) -> str:
        """Format a single YAML property line.

        Mirrors ``formatFixedPropertyYamlLine()`` in the Clipper.

        Parameters
        ----------
        key : str
            YAML key name.
        field_type : str
            One of ``"text"``, ``"number"``, ``"checkbox"``, ``"list"``,
            ``"date"``.
        value : Any
            Raw value (string, number, list, etc.).

        Returns
        -------
        str
            A single ``"key: value"`` line, or ``""`` if the value is
            invalid for the given type.
        """
        resolved = str(value if value is not None else "").strip()
        if not resolved:
            return ""

        ft = self._normalise_type(field_type)

        if ft == "number":
            try:
                num = float(resolved)
            except (ValueError, TypeError):
                return ""
            if not self._is_finite(num):
                return ""
            # Keep original string representation for integers
            if num == int(num) and "." not in resolved:
                return f"{key}: {int(num)}"
            return f"{key}: {resolved}"

        if ft == "checkbox":
            normalised = resolved.lower()
            if normalised not in ("true", "false"):
                return ""
            return f"{key}: {normalised}"

        if ft == "list":
            items = self._parse_array_items(resolved)
            quoted = ", ".join(f'"{self.escape(item)}"' for item in items)
            return f"{key}: [{quoted}]"

        if ft == "date":
            if not self._DATE_RE.match(resolved):
                return ""
            return f"{key}: {resolved}"

        # Default: text
        return f'{key}: "{self.escape(resolved)}"'

    def resolve_template(self, value: str, context: Optional[Dict[str, str]] = None) -> str:
        """Replace ``{{variable}}`` placeholders with values from *context*.

        Mirrors ``resolveFrontmatterTemplateValue()`` in the Clipper.

        Supported variables: ``{{title}}``, ``{{bvid}}``, ``{{author}}``,
        ``{{url}}``, ``{{upload_date}}``, ``{{created}}``, ``{{tags}}``
        (pipe-separated), ``{{tags_csv}}`` (comma-separated),
        ``{{tags_yaml}}`` (YAML list).

        Parameters
        ----------
        value : str
            Template string containing ``{{var}}`` placeholders.
        context : dict | None
            Mapping of variable names to their string values. If *None*,
            the instance's own metadata is used as context.

        Returns
        -------
        str
            *value* with all recognised placeholders replaced.
        """
        if context is None:
            context = self._build_context()

        def _replacer(match: re.Match) -> str:
            raw_key = match.group(1)
            key = raw_key.strip().lower() if raw_key else ""
            if not key:
                return ""
            resolved = context.get(key)
            return str(resolved) if resolved is not None else ""

        return self._TEMPLATE_RE.sub(_replacer, str(value or ""))

    @staticmethod
    def escape(value: Any) -> str:
        """Escape a YAML double-quoted string value.

        Mirrors ``escapeYaml()`` in the Clipper: backslash-first, then
        double-quote.

            >>> YamlFrontmatter.escape('hello "world"')
            'hello \\"world\\"'
        """
        s = str(value if value is not None else "")
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _build_from_fields(self, fields: List[str]) -> str:
        """Internal: iterate *fields*, collect non-empty lines, wrap with ``---``."""
        lines: List[str] = []
        for field in fields:
            line = self._field_line(field)
            if line:
                lines.append(line)

        if not lines:
            return ""

        return "---\n" + "\n".join(lines) + "\n---"

    def _field_line(self, field: str) -> str:
        """Return a single ``key: value`` line for a known default field."""
        if field == "title":
            return f'title: "{self.escape(self.title)}"'
        if field == "url":
            return f'url: "{self.escape(self.url)}"'
        if field == "bvid":
            return f'bvid: "{self.escape(self.bvid)}"'
        if field == "cid":
            cid_str = str(self.cid) if self.cid is not None else ""
            return f'cid: "{self.escape(cid_str)}"'
        if field == "author":
            return f'author: "{self.escape(self.author)}"'
        if field == "upload_date":
            return f'upload_date: "{self.escape(self.upload_date)}"'
        if field == "subtitle_lang":
            return f'subtitle_lang: "{self.escape(self.subtitle_lang)}"'
        if field == "created":
            return f'created: "{self.escape(self.created)}"'
        if field == "tags":
            return f"tags: {self._tags_yaml()}"
        return ""

    def _tags_yaml(self) -> str:
        """Return tags as a YAML inline list."""
        if not self.tags:
            return "[]"
        quoted = ", ".join(f'"{self.escape(t)}"' for t in self.tags)
        return f"[{quoted}]"

    def _tags_csv(self) -> str:
        """Return tags as a comma-separated string (no quoting)."""
        return ", ".join(self.tags)

    def _tags_pipe(self) -> str:
        """Return tags as a pipe-separated string."""
        return " | ".join(self.tags)

    def _build_context(self) -> Dict[str, str]:
        """Build a template-context dict from instance metadata."""
        return {
            "title": self.title,
            "bvid": self.bvid,
            "author": self.author,
            "url": self.url,
            "upload_date": self.upload_date,
            "created": self.created,
            "tags": self._tags_pipe(),
            "tags_csv": self._tags_csv(),
            "tags_yaml": self._tags_yaml(),
        }

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_tags(tags: Any) -> List[str]:
        """Convert *tags* into a deduplicated list of non-empty strings."""
        if tags is None:
            return []
        if isinstance(tags, list):
            items = [str(t).strip() for t in tags]
        elif isinstance(tags, str):
            # Split on pipe, comma, Chinese comma, or semicolon
            items = re.split(r"[,，;|]", tags)
            items = [t.strip() for t in items]
        else:
            items = [str(tags).strip()]
        seen: set = set()
        result: List[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @staticmethod
    def _normalise_type(raw: str) -> str:
        """Map arbitrary type strings to canonical short names."""
        mapping = {
            "text": "text",
            "string": "text",
            "number": "number",
            "float": "number",
            "int": "number",
            "integer": "number",
            "checkbox": "checkbox",
            "bool": "checkbox",
            "boolean": "checkbox",
            "list": "list",
            "array": "list",
            "date": "date",
        }
        return mapping.get(str(raw).strip().lower(), "text")

    @staticmethod
    def _parse_array_items(value: str) -> List[str]:
        """Split a delimited string into a list of trimmed non-empty items.

        Handles commas and Chinese commas (mirrors
        ``parseFrontmatterArrayItems()``).
        """
        return [
            item.strip()
            for item in re.split(r"[，,]", str(value or ""))
            if item.strip()
        ]

    @staticmethod
    def _is_finite(num: float) -> bool:
        """Return True if *num* is a finite number (not NaN or inf)."""
        import math
        return math.isfinite(num)


# ------------------------------------------------------------------
# Integration helper — callable from kb.py to produce a full markdown
# note with YAML frontmatter.
# ------------------------------------------------------------------

def build_obsidian_note(
    *,
    title: str = "",
    bvid: str = "",
    author: str = "",
    cid: Any = 0,
    upload_date: str = "",
    subtitle_lang: str = "",
    url: str = "",
    tags: Any = None,
    created: Optional[str] = None,
    mode: str = "obsidian",
    body_md: str = "",
    footer_md: str = "",
    extra_fields: Optional[Dict[str, str]] = None,
) -> str:
    """Produce a full Obsidian note with YAML frontmatter + body.

    This is the convenience entry-point for callers like ``kb.py`` that
    want a complete ``.md`` string in one shot.

    Parameters
    ----------
    title, bvid, author, cid, upload_date, subtitle_lang, url, tags, created :
        Forwarded to :class:`YamlFrontmatter`.
    mode : str
        ``"obsidian"`` or ``"minimal"``.
    body_md : str
        Markdown body placed after the frontmatter block.
    footer_md : str
        Optional footer appended at the very end (e.g. ``"*Synced by BiliSum*"``).
    extra_fields : dict | None
        Additional YAML key-value pairs injected into the frontmatter
        block (appended after the default fields). Values are written as
        YAML text (quoted + escaped).

    Returns
    -------
    str
        Complete Markdown string ready to write to a ``.md`` file.
    """
    fm = YamlFrontmatter(
        title=title,
        url=url or f"https://www.bilibili.com/video/{bvid}",
        bvid=bvid,
        cid=cid,
        author=author,
        upload_date=upload_date,
        subtitle_lang=subtitle_lang,
        created=created,
        tags=tags,
    )

    yaml_block = fm.build(mode=mode)

    # Inject extra fields before the closing ---
    if extra_fields:
        extra_lines: List[str] = []
        for k, v in extra_fields.items():
            if v is not None:
                extra_lines.append(f'{k}: "{fm.escape(str(v))}"')
        if extra_lines:
            # Insert before the trailing ---
            if yaml_block:
                yaml_block = yaml_block[:-3] + "\n".join(extra_lines)
                if extra_lines:
                    yaml_block += "\n"
                yaml_block += "---"
            else:
                yaml_block = "---\n" + "\n".join(extra_lines) + "\n---"

    parts: List[str] = []
    if yaml_block:
        parts.append(yaml_block)
    if body_md:
        parts.append(body_md)
    if footer_md:
        parts.append(footer_md)

    return "\n\n".join(parts)
