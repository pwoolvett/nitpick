"""Custom Marshmallow fields and validators."""
import json

from marshmallow import ValidationError, fields
from marshmallow.fields import Dict, Field, List, Nested, String
from marshmallow.validate import Length

from nitpick.generic import pretty_exception

__all__ = ("Dict", "List", "String", "Nested", "Field")


def is_valid_json(json_string: str) -> bool:
    """Validate the string as JSON."""
    try:
        json.loads(json_string)
    except json.JSONDecodeError as err:
        raise ValidationError(pretty_exception(err, "Invalid JSON"))
    return True


class TrimmedLength(Length):  # pylint: disable=too-few-public-methods
    """Trim the string before validating the length."""

    def __call__(self, value):
        """Validate the trimmed string."""
        return super().__call__(value.strip())


class FilledString(fields.String):
    """A string field that must not be empty even after trimmed."""

    def __init__(self, **kwargs):
        super().__init__(validate=TrimmedLength(min=1), **kwargs)


class JSONString(fields.String):
    """A string field with valid JSON content."""

    def __init__(self, **kwargs):
        validate = kwargs.pop("validate", [])
        validate.append(is_valid_json)
        super().__init__(validate=validate, **kwargs)


def string_or_list_field(object_dict, parent_object_dict):  # pylint: disable=unused-argument
    """Detect if the field is a string or a list."""
    if isinstance(object_dict, list):
        return fields.List(FilledString(required=True, allow_none=False))
    return FilledString()


def validate_section_dot_field(section_field: str) -> bool:
    """Validate if the combinatio section/field has a dot separating them."""
    # FIXME: add tests for these situations
    common = "Use this format: section_name.field_name"
    if "." not in section_field:
        raise ValidationError("Dot is missing. {}".format(common))
    parts = section_field.split(".")
    if len(parts) > 2:
        raise ValidationError("There's more than one dot. {}".format(common))
    if not parts[0].strip():
        raise ValidationError("Empty section name. {}".format(common))
    if not parts[1].strip():
        raise ValidationError("Empty field name. {}".format(common))
    return True


def boolean_or_dict_field(object_dict, parent_object_dict):  # pylint: disable=unused-argument
    """Detect if the field is a boolean or a dict."""
    if isinstance(object_dict, dict):
        return fields.Dict
    return fields.Bool