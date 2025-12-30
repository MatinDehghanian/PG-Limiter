"""
Enhanced logging configuration for the application.
Provides structured logging with different levels, colors, and contextual information.
"""

import asyncio
import functools
import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler
from typing import Callable

# Log level from environment (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD + Colors.RED,
    }

    def format(self, record):
        # Add color to level name for console
        color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)
        record.levelname_colored = f"{color}{record.levelname:8}{Colors.RESET}"
        record.message_colored = f"{color}{record.getMessage()}{Colors.RESET}"
        return super().format(record)


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that adds context information to log messages."""

    def process(self, msg, kwargs):
        extra = self.extra.copy() if self.extra else {}
        extra.update(kwargs.get("extra", {}))
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str = None, context: dict = None) -> logging.Logger:
    """
    Get a logger with optional context.

    Args:
        name: Logger name (usually __name__)
        context: Additional context to include in logs

    Returns:
        Logger instance
    """
    log = logging.getLogger(name or "limiter")
    if context:
        return ContextLogger(log, context)
    return log


def setup_logging():
    """Configure the root logger with file and console handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler - detailed logs (with error handling)
    try:
        # Try to create log file in current directory or /var/lib/pg-limiter/logs
        log_paths = ["app.log", "/var/lib/pg-limiter/logs/app.log", "/tmp/pg-limiter.log"]
        file_handler = None
        
        for log_path in log_paths:
            try:
                log_dir = os.path.dirname(log_path)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                file_handler = RotatingFileHandler(
                    log_path,
                    maxBytes=10 * 10**6,  # 10MB per file
                    backupCount=5,
                    encoding="utf-8",
                )
                break
            except (PermissionError, OSError):
                continue
        
        if file_handler:
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)-20s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_format)
            root_logger.addHandler(file_handler)
    except Exception:
        # If file logging fails, continue with console only
        pass

    # Console handler - colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Use colors if terminal supports it
    if sys.stdout.isatty():
        console_format = ColoredFormatter(
            "%(asctime)s │ %(levelname_colored)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        console_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    console_handler.setFormatter(console_format)

    root_logger.addHandler(console_handler)

    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


# Initialize logging on module import
setup_logging()

# Main logger instance for backward compatibility
logger = get_logger("limiter")


def log_function_call(func: Callable) -> Callable:
    """
    Decorator to log function entry, exit, and exceptions.

    Usage:
        @log_function_call
        async def my_function(arg1, arg2):
            ...
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_logger = get_logger(func.__module__)
        start_time = time.perf_counter()

        # Log function entry with arguments (truncate long args)
        args_repr = [repr(a)[:100] for a in args]
        kwargs_repr = [f"{k}={v!r}"[:100] for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        func_logger.debug(f"→ ENTER {func.__name__}({signature[:200]})")

        try:
            result = await func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000
            result_repr = repr(result)[:100] if result is not None else "None"
            func_logger.debug(
                f"← EXIT  {func.__name__} [{elapsed:.1f}ms] → {result_repr}"
            )
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            func_logger.error(
                f"✗ ERROR {func.__name__} [{elapsed:.1f}ms]: {type(e).__name__}: {e}"
            )
            func_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_logger = get_logger(func.__module__)
        start_time = time.perf_counter()

        args_repr = [repr(a)[:100] for a in args]
        kwargs_repr = [f"{k}={v!r}"[:100] for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        func_logger.debug(f"→ ENTER {func.__name__}({signature[:200]})")

        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000
            result_repr = repr(result)[:100] if result is not None else "None"
            func_logger.debug(
                f"← EXIT  {func.__name__} [{elapsed:.1f}ms] → {result_repr}"
            )
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            func_logger.error(
                f"✗ ERROR {func.__name__} [{elapsed:.1f}ms]: {type(e).__name__}: {e}"
            )
            func_logger.debug(f"Traceback:\n{traceback.format_exc()}")
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


def log_api_request(
    method: str,
    url: str,
    status: int = None,
    duration_ms: float = None,
    error: str = None,
):
    """
    Log an API request with structured information.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        url: Request URL
        status: HTTP status code (if successful)
        duration_ms: Request duration in milliseconds
        error: Error message (if failed)
    """
    api_logger = get_logger("api")

    if error:
        msg = f"🌐 {method:6} {url} → ERROR: {error}"
        if duration_ms:
            msg += f" [{duration_ms:.0f}ms]"
        api_logger.error(msg)
    elif status:
        emoji = "✓" if 200 <= status < 300 else "⚠" if 300 <= status < 400 else "✗"
        msg = f"🌐 {method:6} {url} → {emoji} {status}"
        if duration_ms:
            msg += f" [{duration_ms:.0f}ms]"
        api_logger.info(msg)
    else:
        api_logger.debug(f"🌐 {method:6} {url} → pending...")


def log_user_action(
    action: str, username: str, details: str = None, success: bool = True
):
    """
    Log a user-related action.

    Args:
        action: Action name (disable, enable, warn, etc.)
        username: Username affected
        details: Additional details
        success: Whether the action was successful
    """
    user_logger = get_logger("user_action")
    emoji = "✓" if success else "✗"
    msg = f"{emoji} {action.upper():12} │ {username}"
    if details:
        msg += f" │ {details}"

    if success:
        user_logger.info(msg)
    else:
        user_logger.warning(msg)


def log_monitoring_event(event: str, username: str = None, details: dict = None):
    """
    Log a monitoring system event.

    Args:
        event: Event type (warning_issued, monitoring_started, user_disabled, etc.)
        username: Username if applicable
        details: Additional details as dict
    """
    mon_logger = get_logger("monitoring")
    msg = f"📡 {event}"
    if username:
        msg += f" │ {username}"
    if details:
        details_str = " │ ".join(f"{k}={v}" for k, v in details.items())
        msg += f" │ {details_str}"
    mon_logger.info(msg)


def log_startup_info(component: str, details: str = None):
    """Log component startup."""
    startup_logger = get_logger("startup")
    msg = f"🚀 {component} starting"
    if details:
        msg += f": {details}"
    startup_logger.info(msg)


def log_shutdown_info(component: str, reason: str = None):
    """Log component shutdown."""
    shutdown_logger = get_logger("shutdown")
    msg = f"🛑 {component} stopping"
    if reason:
        msg += f": {reason}"
    shutdown_logger.info(msg)


def log_crash_info(exc_type, exc_value, exc_tb, component: str = "Unknown"):
    """
    Log detailed crash information with exact file and line number.
    
    Args:
        exc_type: Exception type
        exc_value: Exception value
        exc_tb: Exception traceback
        component: Name of the component that crashed
    """
    crash_logger = get_logger("crash")
    
    crash_logger.error("")
    crash_logger.error("╔═══════════════════════════════════════════════════════════════╗")
    crash_logger.error("║                    💥 CRASH DETECTED 💥                        ║")
    crash_logger.error("╚═══════════════════════════════════════════════════════════════╝")
    crash_logger.error(f"Component: {component}")
    crash_logger.error("")
    
    # Extract the exact error location from traceback
    if exc_tb:
        # Walk to the last frame (actual error location)
        tb = exc_tb
        while tb.tb_next:
            tb = tb.tb_next
        
        filename = tb.tb_frame.f_code.co_filename
        lineno = tb.tb_lineno
        func_name = tb.tb_frame.f_code.co_name
        
        # Try to read the actual line of code
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if 0 < lineno <= len(lines):
                    error_line = lines[lineno - 1].strip()
                else:
                    error_line = '<line not available>'
        except (FileNotFoundError, IOError):
            error_line = '<could not read file>'
    else:
        filename = 'unknown'
        lineno = 0
        func_name = 'unknown'
        error_line = '<no traceback>'
    
    crash_logger.error(f"Error Type: {exc_type.__name__}")
    crash_logger.error(f"Error Message: {exc_value}")
    crash_logger.error(f"File: {filename}")
    crash_logger.error(f"Line: {lineno}")
    crash_logger.error(f"Function: {func_name}")
    crash_logger.error(f"Code: {error_line}")
    crash_logger.error("")
    crash_logger.error("─── Full Traceback ───")
    
    # Log full traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    for line in tb_lines:
        for subline in line.rstrip().split('\n'):
            crash_logger.error(subline)
    
    crash_logger.error("───────────────────────")
    crash_logger.error("")
    
    # Also write to crash log file
    try:
        import datetime
        crash_log_path = "/var/lib/pg-limiter/logs/crash.log"
        # Ensure directory exists
        os.makedirs(os.path.dirname(crash_log_path), exist_ok=True)
        
        with open(crash_log_path, 'a', encoding='utf-8') as crash_file:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            crash_file.write(f"\n")
            crash_file.write(f"═══════════════════════════════════════════════════════════════\n")
            crash_file.write(f"CRASH REPORT - {timestamp}\n")
            crash_file.write(f"Component: {component}\n")
            crash_file.write(f"═══════════════════════════════════════════════════════════════\n")
            crash_file.write(f"Error Type: {exc_type.__name__}\n")
            crash_file.write(f"Error Message: {exc_value}\n")
            crash_file.write(f"File: {filename}\n")
            crash_file.write(f"Line: {lineno}\n")
            crash_file.write(f"Function: {func_name}\n")
            crash_file.write(f"Code: {error_line}\n")
            crash_file.write(f"\n--- Full Traceback ---\n")
            for line in tb_lines:
                crash_file.write(line)
            crash_file.write(f"───────────────────────\n\n")
        crash_logger.info(f"Crash details saved to: {crash_log_path}")
    except Exception as log_err:
        crash_logger.warning(f"Could not write crash log: {log_err}")


class PerformanceTimer:
    """Context manager for timing code blocks."""

    def __init__(self, operation: str, log_level: int = logging.DEBUG):
        self.operation = operation
        self.log_level = log_level
        self.start_time = None
        self.logger = get_logger("perf")

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.perf_counter() - self.start_time) * 1000
        if exc_type:
            self.logger.error(
                f"⏱ {self.operation} failed after {elapsed:.1f}ms: {exc_val}"
            )
        else:
            self.logger.log(
                self.log_level, f"⏱ {self.operation} completed in {elapsed:.1f}ms"
            )
        return False
