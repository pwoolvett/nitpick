"""Main package."""
import itertools
from typing import Optional, Tuple, Type, Any, Dict, Generator

import os
import attr
from pathlib import Path

import requests
import toml

from flake8_nitpick.__version__ import __version__
from flake8_nitpick.generic import get_subclasses, flatten, unflatten, climb_directory_tree

# Types
NitpickError = Tuple[int, int, str, Type]

# Constants
NAME = "flake8-nitpick"
ERROR_PREFIX = "NIP"
CACHE_DIR: Path = Path(os.getcwd()) / ".cache" / NAME
PYPROJECT_TOML = "pyproject.toml"
NITPICK_STYLE_TOML = "nitpick-style.toml"
ROOT_PYTHON_FILES = ("setup.py", "manage.py", "autoapp.py")
ROOT_FILES = (PYPROJECT_TOML, "setup.cfg", "requirements*.txt", "Pipfile") + ROOT_PYTHON_FILES


def nitpick_error(error_number: int, error_message: str) -> NitpickError:
    """Return a nitpick error as a tuple."""
    return 1, 0, f"{ERROR_PREFIX}{error_number} {error_message}", NitpickChecker


class NitpickCache:
    """A cache file in the current dir (in .toml format), to store data that will be reused by the plugin."""

    def __init__(self, key: str) -> None:
        """Init the cache file."""
        self.cache_file: Path = CACHE_DIR / "variables.toml"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.touch(exist_ok=True)
        self.toml_dict = toml.load(str(self.cache_file))

        self.key = key

    def load(self) -> Optional[str]:
        """Load the key from the cache file."""
        return self.toml_dict.get(self.key)

    def load_path(self) -> Optional[Path]:
        """Load the key and resolve the path."""
        value = self.load()
        if value is None:
            return value
        return Path(value).resolve()

    def dump(self, value: Any) -> Any:
        """Save the value (as a string) to the cache file."""
        self.toml_dict[self.key] = str(value)
        toml.dump(self.toml_dict, self.cache_file.open("w"))
        return value

    def dump_path(self, path: Path) -> Path:
        """Save the path relative to the current working dir."""
        value = path.resolve().relative_to(os.getcwd())
        self.dump(value)
        return path


class NitpickConfig:
    """Plugin configuration, read from the project config."""

    def __init__(self, root_dir: Path) -> None:
        """Init instance."""
        self.root_dir = root_dir

        self.pyproject_toml = toml.load(str(self.root_dir / PYPROJECT_TOML))
        self.tool_nitpick_toml = self.pyproject_toml.get("tool", {}).get("nitpick", {})

        style_path = self.find_style()
        self.style_toml = toml.load(str(style_path))

        self.files: Dict[str, bool] = self.style_toml.get("files", {})

    def find_style(self) -> Optional[Path]:
        """Search for a style file."""
        cache = NitpickCache("style")
        style_path = cache.load_path()
        if style_path is not None:
            return style_path

        style: str = self.pyproject_toml.get("style", "")
        if style.startswith("http"):
            # If the style is a URL, save the contents in the cache dir
            response = requests.get(style)
            if not response.ok:
                raise RuntimeError(f"Error {response} fetching style URL {style}")
            contents = response.text
            style_path = CACHE_DIR / "style.toml"
            style_path.write_text(contents)
        elif style:
            style_path = Path(style)
            if not style_path.exists():
                raise RuntimeError(f"Style file does not exist: {style}")
        else:
            paths = climb_directory_tree(self.root_dir, [NITPICK_STYLE_TOML])
            if not paths:
                raise RuntimeError(
                    f"Style not configured on {PYPROJECT_TOML} and {NITPICK_STYLE_TOML} not found in directory tree"
                )
            style_path = paths[0]

        cache.dump_path(style_path)
        return style_path


@attr.s(hash=False)
class NitpickChecker:
    """Main plugin class."""

    # Plugin config
    name = NAME
    version = __version__

    # Plugin arguments passed by Flake8
    tree = attr.ib(default=None)
    filename = attr.ib(default="(none)")

    def run(self):
        """Run the check plugin."""
        root_dir = self.find_root_dir(self.filename)
        if not root_dir:
            yield nitpick_error(100, "No root dir found (is this a Python project?)")
            return

        current_python_file = Path(self.filename)
        main_python_file = self.find_main_python_file(root_dir, current_python_file)
        if not main_python_file:
            yield nitpick_error(100, f"No Python file was found in the root dir {root_dir}")
            return
        if current_python_file.resolve() != main_python_file.resolve():
            # Only report warnings once, for the main Python file of this project.
            return

        try:
            config = NitpickConfig(root_dir)
        except RuntimeError as err:
            yield nitpick_error(100, str(err))
            return

        for checker_class in get_subclasses(BaseChecker):
            checker = checker_class(config)
            for error in itertools.chain(checker.check_exists(), checker.check_rules()):
                yield error

        return []

    @staticmethod
    def find_root_dir(python_file: str) -> Optional[Path]:
        """Find the root dir of the Python project: the dir that has one of the `ROOT_FILES`."""
        cache = NitpickCache("root_dir")
        root_dir = cache.load_path()
        if root_dir is not None:
            return root_dir

        found_files = climb_directory_tree(python_file, ROOT_FILES)
        if not found_files:
            return None
        root_dir = found_files[0].parent
        cache.dump_path(root_dir)
        return root_dir

    def find_main_python_file(self, root_dir: Path, current_file: Path) -> Path:
        """Find the main Python file in the root dir, the one that will be used to report Flake8 warnings."""
        cache = NitpickCache("main_python_file")
        main_python_file = cache.load_path()
        if main_python_file is not None:
            return main_python_file

        for the_file in itertools.chain(
            [root_dir / root_file for root_file in ROOT_PYTHON_FILES], root_dir.glob("*.py")
        ):
            if the_file.exists():
                found = the_file
                break
        else:
            found = current_file
        return cache.dump_path(found)


class BaseChecker:
    """Base class for file checkers."""

    file_name: str
    should_exist_default: bool

    def __init__(self, config: NitpickConfig) -> None:
        """Init instance."""
        self.config = config
        self.file_path: Path = self.config.root_dir / self.file_name
        self.file_toml = self.config.style_toml.get(self.file_name, {})

    def check_exists(self) -> Generator[NitpickError, Any, Any]:
        """Check if the file should exist or not."""
        should_exist = self.config.files.get(self.file_name, self.should_exist_default)
        file_exists = self.file_path.exists()

        if should_exist and not file_exists:
            yield nitpick_error(102, f"Missing file {self.file_name!r}")
        elif not should_exist and file_exists:
            yield nitpick_error(103, f"File {self.file_name!r} should be deleted")

    def check_rules(self):
        """Check rules for this file. It should be overridden by inherited class if they need."""
        return []


class PyProjectTomlChecker(BaseChecker):
    """Check pyproject.toml."""

    file_name = "pyproject.toml"
    should_exist_default = True

    def check_rules(self):
        """Check missing key/value pairs in pyproject.toml."""
        project = flatten(self.config.pyproject_toml)
        style = flatten(self.file_toml)
        if style.items() <= project.items():
            return []

        missing_dict = unflatten({k: v for k, v in style.items() if k not in project})
        missing_toml = toml.dumps(missing_dict)
        yield nitpick_error(104, f"Missing values in {self.file_name!r}:\n{missing_toml}")


class SetupCfgChecker(BaseChecker):
    """Check setup.cfg."""

    file_name = "setup.cfg"
    should_exist_default = True


class PipfileChecker(BaseChecker):
    """Check Pipfile."""

    file_name = "Pipfile"
    should_exist_default = False


class PipfileLockChecker(BaseChecker):
    """Check Pipfile.lock."""

    file_name = "Pipfile.lock"
    should_exist_default = False
