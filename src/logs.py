import os
import logging
import time
import sys
from datetime import date

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

LOGS_FILE_PATH = ROOT_DIR + "/logs"

if not os.path.exists(LOGS_FILE_PATH):
    os.mkdir(LOGS_FILE_PATH)


class StreamFilter():
    def __init__(self, debug_enabled):
        self.__debug_enabled = debug_enabled

    def filter(self, logRecord):
        return logRecord.levelno != 10 or self.__debug_enabled


def setup_logger(debug_enabled=False):
    formatter = logging.Formatter("[%(levelname)s] %(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    logging.Formatter.converter = time.gmtime

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    fileHandler = logging.FileHandler(f"{LOGS_FILE_PATH}/{date.today()}.log")
    streamHandler = logging.StreamHandler(sys.stdout)

    for handler in (fileHandler, streamHandler):
        handler.setFormatter(formatter)

    fileHandler.setLevel(logging.DEBUG)

    streamFilter = StreamFilter(debug_enabled)
    streamHandler.addFilter(streamFilter)

    logger.addHandler(fileHandler)
    logger.addHandler(streamHandler)

    return logger
