"""Text files."""
import logging
from typing import Optional, Set, Type

from marshmallow import Schema
from marshmallow.orderedset import OrderedSet

from nitpick import fields
from nitpick.plugins import hookimpl
from nitpick.plugins.base import NitpickPlugin
from nitpick.schemas import help_message
from nitpick.typedefs import YieldFlake8Error

LOGGER = logging.getLogger(__name__)

TEXT_FILE_RTFD_PAGE = "plugins.html#text-files"


class TextItemSchema(Schema):
    """Validation schema for the object inside ``contains``."""

    error_messages = {"unknown": help_message("Unknown configuration", TEXT_FILE_RTFD_PAGE)}
    line = fields.NonEmptyString()


class TextSchema(Schema):
    """Validation schema for the text file TOML configuration."""

    error_messages = {"unknown": help_message("Unknown configuration", TEXT_FILE_RTFD_PAGE)}
    contains = fields.List(fields.Nested(TextItemSchema))


class TextPlugin(NitpickPlugin):
    """Checker for text files.

    To check if ``some.txt`` file contains the lines ``abc`` and ``def`` (in any order):

    .. code-block:: toml

        [["some.txt".contains]]
        line = "abc"

        [["some.txt".contains]]
        line = "def"
    """

    error_base_number = 350
    identify_tags = {"text"}
    validation_schema = TextSchema

    #: All other files are also text files, and they already have a suggested content message
    # TODO: this is a hack to avoid rethinking the whole schema validation now (this will have to be done some day)
    skip_empty_suggestion = True

    def _expected_lines(self):
        return [obj.get("line") for obj in self.file_dict.get("contains", {})]

    def suggest_initial_contents(self) -> str:
        """Suggest the initial content for this missing file."""
        return "\n".join(self._expected_lines())

    def check_rules(self) -> YieldFlake8Error:
        """Check missing lines."""
        expected = OrderedSet(self._expected_lines())
        actual = OrderedSet(self.file_path.read_text().split("\n"))
        missing = expected - actual
        if missing:
            yield self.flake8_error(2, " has missing lines:", "\n".join(sorted(missing)))


@hookimpl
def plugin_class() -> Type["NitpickPlugin"]:
    """You should return your plugin class here."""
    return TextPlugin


@hookimpl
def handler(file_name: str, tags: Set[str]) -> Optional["NitpickPlugin"]:
    """Handle text files."""
    if "text" in tags:
        return TextPlugin(file_name)
    return None
