import logging
import logging.handlers
import signal
import sys
import traceback


def configurelogging():
    _LOGGER.setLevel(logging.DEBUG)
    streamhandler = logging.StreamHandler(sys.stderr)
    streamhandler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        'xscontainer[%(process)d] - %(levelname)s - %(message)s')
    streamhandler.setFormatter(formatter)
    _LOGGER.addHandler(streamhandler)
    handler = logging.handlers.SysLogHandler(
        address='/dev/log', facility=logging.handlers.SysLogHandler.LOG_DAEMON)
    handler.setLevel(logging.DEBUG)
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


def handle_unhandled_exceptions(exception_type, exception_value,
                                exception_traceback):
    if not issubclass(exception_type, KeyboardInterrupt):
        _LOGGER.error("Nobody caught exception: %s" % (exception_type))
        _LOGGER.error(traceback.format_exception(exception_type,
                                                  exception_value,
                                                  exception_traceback))
    sys.__excepthook__(exception_type, exception_value, exception_traceback)

_LOGGER = logging.getLogger()
configurelogging()
sys.excepthook = handle_unhandled_exceptions
