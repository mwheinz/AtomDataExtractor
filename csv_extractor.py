#!python3
'''
Convert information from an Atom flight log into a Telemetry Overlay CSV
'''

import os
import argparse
import sys
import struct
import math
import datetime
import logging

class FLFD:
	def __init__(self, name, fmtString, startPos, length, scale=0):
		self.name = name # This will be the header in the CSV.
		self.fmtString = fmtString # how to unpack the data in the flight log.
		self.startPos = startPos # Where the data starts in the flight log.
		self.length = length # the length of the field in the flight log.
		self.scale = scale # A multiplier for adjusting the data.

	def getField(self,record) -> str:
		data = struct.unpack(self.fmtString,record[self.startPos:self.startPos+self.length])
		if data == ():
			return None
		data = data[0]
		if self.scale != 0:
			data = data * self.scale
		if isinstance(data,float):
			return f"{data:.3f}"
		return str(data)
	
#
# Field specs for an Atom2 log.
#
ATOM2_FORMAT = [
	# fields appear in the order they should be in the CSV file.
	FLFD("time (ms)", "<Q", 5, 8, 1e-3), # elapsed time since the drone started.
	FLFD("lat (deg)", "<i", 47, 4, 1e-7), # drone latitude * 1e7
	FLFD("lon (deg)", "<i", 51, 4, 1e-7), # drone latitude * 1e7
	FLFD("dist (m)", "<i", 416, 4), # Distance to home in meters ?
	FLFD("hlat (deg)", "<i", 420, 4, 1e-7), # drone latitude * 1e7
	FLFD("hlon (deg)", "<i", 424, 4, 1e-7), # drone latitude * 1e7
	FLFD("EOD","",0,0,0) # Flags the end of the list.
]

#
# Colorize our logging output.
#
class ColorFormatter(logging.Formatter):
	COLORS= {
		'DEBUG': "\033[1;34m",		# Blue
		'INFO': "\033[1;32m",		# Green
		'WARNING': "\033[1;33m",	# Yellow
		'ERROR': "\033[1;31m",		# Red
		'CRITICAL': "\033[1;41m",	# Red on background
    }

	def format(self, record):
		color= self.COLORS.get(record.levelname,"\033[0m")
		return f"{color}{record.levelname:<8}\033[0m{super().format(record)}"

#
# The global logger.
#
cHandler = logging.StreamHandler()
cHandler.setFormatter(ColorFormatter())
logging.basicConfig(level=logging.DEBUG)
logger=logging.getLogger(sys.argv[0])
logger.addHandler(cHandler)
logger.propagate = False

def atomParse(fieldList, fileName):
	baseName, extension = os.path.splitext(fileName)
	cname=f"{baseName}.csv"

	logger.debug(f"Creating {cname}.")

	try:
		csvFile = open(cname, mode="w")
	except:
		logger.critical(f"Unable to create {cname}. Terminating.")
		sys.exit(-1)

	header=""
	for flfd in fieldList:
		header=header+f"{flfd.name}, "
	print(header, file=csvFile)

	with open(fileName, mode="rb") as flightFile:
		rCount = 0
		eCount = 0

		while True:
			record = flightFile.read(512)
			if len(record) < 512:
				break
			rCount += 1
			
			line=""
			for flfd in fieldList:
				#logger.debug(f"extracting {flfd.name}")
				data = flfd.getField(record)
				line=line+f"{data}, "
			print(line, file=csvFile)

	logger.info(f"{rCount} valid records in {fileName}. {eCount} bad records in file.")
	
def main() -> None:
	parser = argparse.ArgumentParser(
		description="Convert Potensic Flight Log files to Telemetry Overlay format.",
		epilog="Written by Michael Heinz, based on information provided by potdrownflightparser by koen-arts.")
	parser.add_argument("-l","--log", type=int, help="Set log level. 0=error, higher values increase logging.", default=0)
	parser.add_argument("files", nargs="+", help="One or more FlightLog files to convert.")
	args = parser.parse_args()

	match args.log:
		case 0:
			ll = logging.ERROR
		case 1: 
			ll = logging.WARNING
		case 2:
			ll = logging.INFO
		case _:
			ll = logging.DEBUG

	logger.setLevel(ll)

	print(f"Atom Flight Log to Telemetry Overlay Converter.")

	for f in args.files:
		baseName, extension = os.path.splitext(f)
		if not os.path.exists(f):
			logger.error(f"{f} does not exist.")
			sys.exit(-1)
		elif extension == ".fc2":
			logger.info(f"Parsing {f} as an Atom2 log file.")
			atomParse(ATOM2_FORMAT, f)
		elif extension == ".fc":
			logger.error(f"Sorry, I can't handle Atom1 log files yet. Can't parse {f}.")
			sys.exit(-1)
		else:
			logger.info(f"{f} appears to be an unsupported file type.")
			sys.exit(-1)

if __name__ == '__main__':
	main()

