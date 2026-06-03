"""
Centralized logging utility for the Financial News project.

Provides:
* Colored console output for developer-friendly local runs.
* JSON structured file logging for FluentBit → Loki → Grafana pipeline.
* Thread-safe contextual fields (source_name, ticker, keyword, news_id).
"""
import json
import logging
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# ---------------------------------------------------------------------------
# Thread-local storage for structured log context
# ---------------------------------------------------------------------------
_log_context = threading.local()


def set_log_context(**kwargs: Any) -> None:
    """
    Attach key-value pairs to the current thread's log context.

    These fields are automatically included in every JSON log line emitted
    from the same thread until cleared.

    Args:
        **kwargs: Arbitrary context fields (e.g., source_name, ticker_symbol,
                  keyword, run_id).
    """
    if not hasattr(_log_context, "fields"):
        _log_context.fields = {}
    _log_context.fields.update(kwargs)


def clear_log_context() -> None:
    """Remove all contextual fields from the current thread."""
    _log_context.fields = {}


def get_log_context() -> Dict[str, Any]:
    """Return a *copy* of the current thread's context fields."""
    return dict(getattr(_log_context, "fields", {}))


class Colors:
    """Color constants for easy access."""

    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    BLUE = Fore.LIGHTBLUE_EX
    CYAN = Fore.CYAN
    MAGENTA = Fore.MAGENTA
    WHITE = Fore.WHITE
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
    DIM = Style.DIM
    
class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for different log levels."""

    COLORS = {
        "DEBUG": Colors.CYAN,
        "INFO": Colors.BLUE,
        "SUCCESS": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": Colors.RED + Colors.BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with appropriate color."""
        log_color = self.COLORS.get(record.levelname, Fore.WHITE)
        record.msg = f"{log_color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """
    Outputs each log record as a single JSON line.

    Designed for ingestion by FluentBit which parses JSON and ships to Loki.
    Includes thread-local context fields (source_name, ticker_symbol, etc.)
    alongside standard record attributes.

    Note: Uses ``record.getMessage()`` on the *original* format args to avoid
    picking up ANSI color codes injected by :class:`ColoredFormatter`.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Serialize the log record to a JSON string.

        The output schema:
            {
                "timestamp": "2024-07-14T12:00:00.000Z",
                "level": "INFO",
                "logger": "src.scraper.page_scraper",
                "message": "...",
                "source_name": "cafef",   # from context
                "ticker_symbol": "BCM",   # from context
                ...
            }
        """
        # Extract the clean message before any formatter mutates record.msg
        # record.msg might have been mutated by ColoredFormatter, so we
        # reconstruct from the original args if possible.
        raw_msg = record.msg
        # Strip ANSI escape codes if present
        clean_message = re.sub(r"\x1b\[[0-9;]*m", "", str(raw_msg))
        if record.args:
            try:
                clean_message = clean_message % record.args
            except (TypeError, ValueError):
                pass

        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": clean_message,
        }

        # Merge thread-local context
        log_entry.update(get_log_context())

        # Include extra fields passed via `logger.info("msg", extra={...})`
        # Only include explicitly passed extras, not internal LogRecord fields.
        _standard_keys = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())
        for key, value in record.__dict__.items():
            if key not in _standard_keys and key not in log_entry:
                log_entry[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ProjectLogger:
    """
    Centralized logger for the project with colored console output
    and optional JSON file output for log aggregation.

    Usage:
        from src.utils.logger import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started")
        logger.success("Task completed!")
        logger.error("Something went wrong")

    For structured logging to FluentBit:
        logger = get_logger(__name__, json_log_file="logs/scraper/run.log")
    """

    # Add custom SUCCESS level (between INFO and WARNING)
    SUCCESS_LEVEL = 25

    _loggers: Dict[str, logging.Logger] = {}  # Cache loggers to avoid duplicates

    @classmethod
    def get_logger(
        cls,
        name: str,
        level: int = logging.DEBUG,
        log_file: Optional[str] = None,
        file_level: int = logging.INFO,
        json_log_file: Optional[str] = None,
    ) -> logging.Logger:
        """
        Get or create a logger with the specified configuration.

        Args:
            name: Logger name (usually __name__).
            level: Console logging level (default: DEBUG).
            log_file: Optional plain-text file path (human-readable format).
            file_level: File logging level (default: INFO).
            json_log_file: Optional JSON-structured file path for FluentBit
                           ingestion. Each line is a valid JSON object.

        Returns:
            Configured logger instance with .success() method.
        """
        # Return cached logger if exists
        if name in cls._loggers:
            return cls._loggers[name]

        # Add custom SUCCESS level
        logging.addLevelName(cls.SUCCESS_LEVEL, "SUCCESS")

        # Create logger
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)  # Capture all levels

        # Prevent duplicate handlers if logger already exists
        if logger.handlers:
            cls._loggers[name] = logger
            return logger

        # Only add a console handler when this logger is the "root" of the
        # application (i.e. a file sink is being configured).  Child module
        # loggers called without file arguments propagate to the parent and
        # should NOT get their own console handler – that causes every log
        # line to appear twice (once from the child, once from the parent).
        if log_file or json_log_file:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_formatter = ColoredFormatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        else:
            # Library-style: let propagation carry the record to whatever
            # handler the application has configured.  NullHandler silences
            # the "No handlers could be found" warning when used standalone.
            logger.addHandler(logging.NullHandler())

        # Plain-text File Handler (optional, no colors)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(file_level)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        # JSON File Handler (for FluentBit ingestion)
        if json_log_file:
            json_path = Path(json_log_file)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_handler = logging.FileHandler(json_log_file, encoding="utf-8")
            json_handler.setLevel(file_level)
            json_handler.setFormatter(JsonFormatter())
            logger.addHandler(json_handler)

        # Add success method
        def success(message, *args, **kwargs):
            logger.log(cls.SUCCESS_LEVEL, message, *args, **kwargs)

        logger.success = success

        # Cache and return
        cls._loggers[name] = logger
        return logger


def get_logger(
    name: Optional[str] = None,
    level: int = logging.DEBUG,
    log_file: Optional[str] = None,
    json_log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Convenience function to get a configured logger.

    Args:
        name: Logger name (defaults to calling module).
        level: Console logging level (default: DEBUG).
        log_file: Optional plain-text log file path.
        json_log_file: Optional JSON-structured log file path for FluentBit.

    Returns:
        Configured logger instance with .success() method.

    Example:
        logger = get_logger(__name__)
        logger.info("Starting process...")
        logger.success("Process completed!")

    For structured logging (FluentBit pipeline):
        logger = get_logger(__name__, json_log_file="logs/scraper/run.log")
    """
    if name is None:
        # Get the calling module's name
        import inspect

        frame = inspect.currentframe().f_back
        name = frame.f_globals.get("__name__", "root")

    return ProjectLogger.get_logger(name, level, log_file, json_log_file=json_log_file)


def colored(text: str, color: str) -> str:
    """
    Return colored text for manual formatting.

    Args:
        text: Text to color.
        color: Color from Colors class or colorama.Fore.

    Returns:
        Colored text string.

    Example:
        print(colored("Success!", Colors.GREEN))
    """
    return f"{color}{text}{Style.RESET_ALL}"


# For backward compatibility
def log_success(logger: logging.Logger, message: str) -> None:
    """Helper function to log success messages."""
    logger.success(message)