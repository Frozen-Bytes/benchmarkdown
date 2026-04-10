import textwrap
from enum import Enum
from typing import Any


class AlertType(Enum):
    NOTE = 0,
    TIP = 1,
    IMPORTANT = 2,
    WARNING = 3,
    CAUTION = 4,

class MarkdownWriter:
    _lines: list[str] = []

    # Note: Used with details tag only
    _op_stack: list[tuple[str, bool]] = []
    _indent_level: int = 0

    # This is a hacky way to handle different state. It is fine for now, but most
    # likely will introduce bugs.
    #
    # TODO: Refactor
    _is_last_op_details = False
    _table_headers: list[str] = []
    _is_table_empty: bool = True

    def __str__(self) -> str:
        return "\n".join(self._lines)

    def to_string(self) -> str:
        return self.__str__()

    def text(self, text: str) -> None:
        self._lines.append(textwrap.indent(text, " " * self._indent_level))
        self._is_last_op_details = False

    def header(self, header: str, level: int = 1) -> None:
        self.text(f"{'#' * level} {header}")

        # Always add an empty line after a header
        self.text("")

        self._is_last_op_details = False

    def push_details(
        self,
        label: str,
        indent: bool = True,
        bold: bool = True,
        italic: bool = False,
        open: bool = False,
    ) -> None:
        if self._is_last_op_details:
            self.space()

        tmp_label = label
        if bold:
            tmp_label = f"<b>{label}</b>"

        if italic:
            tmp_label = f"<i>{label}</i>"

        self.text(f"- <details {'open' if open else ''}>")
        self.text(f"  <summary>{tmp_label}</summary>")
        self.text("")

        if indent:
            self._indent_level += 2

        self._op_stack.append((label, indent))
        self._is_last_op_details = True

    def pop_details(self) -> None:
        assert self._op_stack
        label, indent = self._op_stack.pop()

        self.text(f"</details> <!-- {label} -->")
        self.text("")

        if indent:
            self._indent_level -= 2

        self._is_last_op_details = False

    def begin_table(self, headers: list[str]) -> None:
        # Rest Table State
        self._is_table_empty = True
        self._table_headers = headers

        if self._is_last_op_details:
            self.space()

        self.text("| " + " | ".join(headers) + " |")
        self.text("|" + " --- |" * len(headers))

        self._is_last_op_details = False

    def end_table(self) -> None:
        if self._is_table_empty:
            self.text("| " + "  | " * len(self._table_headers) + " |")

        # Rest Table State
        self._is_table_empty = True
        self._table_headers = []

        # Always add an empty line after a table
        self.text("")

        self._is_last_op_details = False

    def table_row(self, rows: list[Any]) -> None:
        self.text("| " + " | ".join(map(str, rows)) + " |")
        self._is_table_empty = False

        self._is_last_op_details = False

    def space(self) -> None:
        self.text("<br>")
        self.text("")

        self._is_last_op_details = False

    def alert_block(self, text: str, type: AlertType = AlertType.NOTE) -> None:
        self.text(f"> [!{type.name}]")
        self.text(f"> {text}")

        # Always add an empty line after an alert block
        self.text("")

        self._is_last_op_details = False

    def comment_block(self, text: str) -> None:
        self.text(f"> {text}")

        # Always add an empty line after a comment block
        self.text("")

        self._is_last_op_details = False
