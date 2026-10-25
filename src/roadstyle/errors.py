"""The errors of roadstyle's Rust engine (docs/design/t4_python_binding.md, section 3). Each is a ValueError, so code that catches
ValueError keeps working. The class says what the caller does; the message is the engine's text."""


class DataError(ValueError):
    """The input data is not correct: a column (also a column that a keyword names and the roads do not have), a geometry, the
    contents of a file, or more roads than the engine draws. Skip the input or correct it."""


class OptionsError(ValueError):
    """The call's options are not correct: the look, a keyword, a page or tile option. Correct the call."""


class LevelsError(ValueError):
    """The drawing levels: the edits, the pairs or the heads are not correct, the hard rules have no solution, or the stored levels
    are not for these edges. Correct the edits or solve again."""


class FileError(ValueError):
    """A file that is not read or written: a stage's file, a level area's file, a CRS that is not read. Correct the path or the file."""


class UnsupportedError(ValueError):
    """A part that the Rust engine does not draw. Use another option or engine="python"."""
