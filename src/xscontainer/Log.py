import logging
import logging.handlers
import signal
import sys

logger = None
loggerconfigured = False


def configurelogging():
    global loggerconfigured
    if loggerconfigured:
        return
    global logger
    logger = logging.getLogger()
    loggerconfigured = True
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        'xscontainer[%(process)d] - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    handler = logging.handlers.SysLogHandler(
        address='/dev/log', facility=logging.handlers.SysLogHandler.LOG_DAEMON)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def debug(message):
    configurelogging()
    logger.debug(message)


def info(message):
    configurelogging()
    logger.info(message)


def warning(message):
    configurelogging()
    logger.warning(message)


def error(message):
    configurelogging()
    logger.error(message)


def critical(message):
    configurelogging()
    logger.critical(message)


def exception(message):
    configurelogging()
    logger.exception(message)


def handle_unhandled_exceptions(exception_type, exception_value, exception_traceback):
    if not issubclass(exception_type, KeyboardInterrupt):
        logger.error("Unhandled exception", exc_info=(
            exception_type, exception_value, exception_traceback))
    sys.__excepthook__(exception_type, exception_value, exception_traceback)

sys.excepthook = handle_unhandled_exceptions
