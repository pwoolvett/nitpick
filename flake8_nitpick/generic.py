"""Generic functions and classes."""
import collections
from pathlib import Path
from typing import Iterable, Optional


def get_subclasses(cls):
    """Recursively get subclasses of a parent class."""
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses += get_subclasses(subclass)
    return subclasses


def flatten(dict_, parent_key="", separator="."):
    """Flatten a nested dict."""
    items = []
    for key, value in dict_.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, collections.MutableMapping):
            items.extend(flatten(value, new_key, separator=separator).items())
        else:
            items.append((new_key, value))
    return dict(items)


def unflatten(dict_, separator="."):
    """Turn back a flattened dict into a nested dict."""
    items = {}
    for k, v in dict_.items():
        keys = k.split(separator)
        sub_items = items
        for ki in keys[:-1]:
            try:
                sub_items = sub_items[ki]
            except KeyError:
                sub_items[ki] = {}
                sub_items = sub_items[ki]

        sub_items[keys[-1]] = v

    return items


def climb_directory_tree(starting_path: Path, file_patterns: Iterable[str]) -> Optional[Iterable[Path]]:
    """Climb the directory tree looking for file patterns."""
    current_dir: Path = Path(starting_path).resolve()
    if current_dir.is_file():
        current_dir = current_dir.parent

    while current_dir.root != str(current_dir):
        for root_file in file_patterns:
            found_files = list(current_dir.glob(root_file))
            if found_files:
                return found_files
        current_dir = current_dir.parent
    return None
