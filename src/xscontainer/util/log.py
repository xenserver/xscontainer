import logging
import logging.handlers
import os
import signal
import sys
import traceback

ENABLE_DEV_LOGGING_FILE = ("/opt/xensource/packages/files/xscontainer/"
                           "devlogging_enabled")

LOG_FILE = "/var/log/xscontainer.log"

M = 1024 * 1024

def configurelogging():
    _LOGGER.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - [%(process)d] - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S')

    handlers = []
    log_level = logging.INFO

    if os.access(os.path.dirname(LOG_FILE), os.W_OK):
        fileh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5*M, backupCount=5)
        handlers.append(fileh)

    if os.path.exists(ENABLE_DEV_LOGGING_FILE) or not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))
        log_level = logging.DEBUG

    # Configure and add all handlers
    for handler in handlers:
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        _LOGGER.addHandler(handler)

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def debug(message):
    _LOGGER.debug(message)


def info(message):
    _LOGGER.info(message)


def warning(message):
    _LOGGER.warning(message)


def error(message):
    _LOGGER.error(message)


def critical(message):
    _LOGGER.critical(message)


def exception(message):
    _LOGGER.exception(message)


def log_unhandled_exception(origin, exception_type, exception_value,
                           exception_traceback):
    _LOGGER.error("Nobody caught %s exception: %s" % (origin, exception_type))
    problem = traceback.format_exception(exception_type,
                                         exception_value,
                                         exception_traceback)
    for line in problem:
        error(line)


def handle_unhandled_exceptions(exception_type, exception_value,
                                exception_traceback):
    if not issubclass(exception_type, KeyboardInterrupt):
        log_unhandled_exception("standalone", exception_type, exception_value,
                                exception_traceback)
    sys.__excepthook__(exception_type, exception_value, exception_traceback)

_LOGGER = logging.getLogger()
configurelogging()
sys.excepthook = handle_unhandled_exceptions
