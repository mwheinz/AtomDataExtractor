"""
Adds simple color logging, formatted the way I like it.
"""
import logging
from logging.handlers import RotatingFileHandler
import sys

# Public constants for your CLI mapping
ERROR   = logging.ERROR
WARNING = logging.WARNING
INFO    = logging.INFO
DEBUG   = logging.DEBUG

class MWHFormatter(logging.Formatter):
    """ Adds some color to the log messages. """
    COLORS = {
        logging.DEBUG:    "\033[1;34m",  # Blue
        logging.INFO:     "\033[1;32m",  # Green
        logging.WARNING:  "\033[1;33m",  # Yellow
        logging.ERROR:    "\033[1;31m",  # Red
        logging.CRITICAL: "\033[1;41m",  # Red on background
    }

    # Used to restore the default colors.
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        # Compact, informative format; tweak as you like
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s:%(lineno)-4d %(message)s",
            datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        if self.use_color:
            color = self.COLORS.get(record.levelno, "")
            if color:
                # Colorize just the level word to keep logs readable when pasted
                levelname = record.levelname.ljust(8)
                base = base.replace(levelname, f"{color}{levelname}{self.RESET}", 1)
        return base

class MWHLogger(logging.Logger):
    """ Formats log messages the way I like them. """
    handler: logging.Handler = None

    def __init__(self, name: str = None):
        super().__init__(name=name)

        stream = sys.stderr
        self.handler = logging.StreamHandler(stream)
        self.handler.setFormatter(MWHFormatter(use_color=stream.isatty()))

        self.addHandler(self.handler)
        self.setLevel(INFO)
        self.propagate = False
        self.file_handle = None

    def configure_logging(self, level: int = None,
                          log_file: str = None,
                          file_handle = None) -> None:
        """
        Adjust the log level and optionally logs to console output, and/or a 
        log file, and/or a file_handle.
        """
        if file_handle:
            self.file_handle = file_handle

            h = logging.StreamHandler(file_handle)
            h.setFormatter(MWHFormatter(use_color=False))
            h.setLevel(self.level)
            self.addHandler(h)

        elif log_file:
            h = RotatingFileHandler(log_file, maxBytes=2_000_000,
                                    backupCount=3, encoding="utf-8")
            # File logs should be plain (no color), include module/line
            h.setFormatter(MWHFormatter(use_color=False))
            h.setLevel(self.level)
            self.addHandler(h)

        if level:
            self.setLevel(level)

    def setLevel(self, level:int):
        self.level = level
        super().setLevel(level)
        for h in self.handlers:
            h.setLevel(self.level)

    def print(self, msg):
        """
        This was added so that adv could report the name of the output file.
        """
        if self.file_handle is not None:
            print(msg, file=self.file_handle)
