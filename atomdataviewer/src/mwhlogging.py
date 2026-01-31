import logging
import sys

ERROR = logging.ERROR
WARNING = logging.WARNING
INFO = logging.INFO
DEBUG = logging.DEBUG

#
# Colorize our logging output.
#
class MWHFormatter(logging.Formatter):
	COLORS= {
		'DEBUG': "\033[1;34m",		# Blue
		'INFO': "\033[1;32m",		# Green
		'WARNING': "\033[1;33m",	# Yellow
		'ERROR': "\033[1;31m",		# Red
		'CRITICAL': "\033[1;41m",	# Red on background
    }

	def format(self, record):
		color= self.COLORS.get(record.levelname,"\033[0m")
		return f"{color}{record.levelname:<8}\033[0m {super().format(record)}"

#
# The global logger.
#
mwhHandler = logging.StreamHandler()
mwhHandler.setFormatter(MWHFormatter())
logging.basicConfig(level=logging.DEBUG)
mwhLogger=logging.getLogger(sys.argv[0])
mwhLogger.addHandler(mwhHandler)
mwhLogger.propagate = False

