#!/usr/bin/python3

########################################################
# import python module
import logging, logging.handlers
from logging.handlers import TimedRotatingFileHandler


########################################################
# import application module


########################################################
# define
LEV_CRITICAL = logging.CRITICAL
LEV_ERROR = logging.ERROR
LEV_WARN = logging.WARNING
LEV_INFO = logging.INFO
LEV_DEBUG = logging.DEBUG

LEV_CURRENT = LEV_DEBUG

########################################################
# global value


########################################################
# function


########################################################
# class
class CLog():
    def __init__(self, level, log_file):
        self.level = level
        self.log_file = log_file        # common.PROJECT_PATH + 'data/log/log.txt'
        self.logger = None
        #self.log_format = logging.Formatter(fmt='[%(asctime)s-%(name)s-%(levelname)s] %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')
        self.log_format = logging.Formatter(fmt='[%(asctime)s - %(process)s - %(levelname)s] %(message)s', datefmt=None)
        self.log_handlers = \
            [
                #TimedRotatingFileHandler(self.log_file, when="d", interval=1, backupCount=7)
                logging.StreamHandler()
            ]

    def create_logger(self, logger_name):
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(self.level)
        for h in self.log_handlers:
            h.setFormatter(self.log_format)
            h.setLevel(self.level)
            self.logger.addHandler(h)

    def destroy_logger(self):
        logging.shutdown()

        if None != self.logger:
            del self.logger

    def debug(self, log_data):
        if None != self.logger:
            self.logger.debug(log_data)

    def info(self, log_data):
        if None != self.logger:
            #self.logger.info("\r\n{}".format(log_data))
            print("\r\n{}".format(log_data))

    def warn(self, log_data):
        if None != self.logger:
            self.logger.warn(log_data)

    def error(self, log_data):
        if None != self.logger:
            self.logger.error(log_data)

    def exception(self, log_data):
        if None != self.logger:
            #self.logger.exception(log_data)
            self.logger.error(log_data)

    def critical(self, log_data):
        if None != self.logger:
            self.logger.critical(log_data)