#!python3
'''
Convert information from an Atom flight log into a Telemetry Overlay CSV
'''

import os
import re
import argparse
import sys
import struct
import math
import datetime
import logging

timeStamp: float

class FLFD:
	def __init__(self, name, fmtString, startPos, length, scale=None):
		# This will be the header in the CSV. If it has specific unit, include
		# it in parens. For example, "lat (deg)" is the latitude, in decimal degrees.
		self.name = name
		# how to unpack the data in the flight log.
		self.fmtString = fmtString
		# Where the data starts in the flight log record.
		self.startPos = startPos
		# the length of the field in the flight log.
		self.length = length
		# A numeric multiplier or parsing function for adjusting the data.
		self.scale = scale

	# radians to decimal degrees. 
	def r2d(data) -> float:
		result = round((360 + data * 180/math.pi) % 360, 3)
		if math.isnan(result):
			# TODO: Figure out better handling of bad records.
			logger.critical(f"Bad heading value {data} found.");
			sys.exit(-1)
		return result

	# Atom 2 use integers to store the decimal lat/long with 7 digits of precision.
	def fixLatLong(data) -> float:
		if data == 0:
			return None # error case.
		return data / 1e7

	# No idea why the altitude appears to be a negative number...
	def fixAlt(data) -> float:
		return abs(round(data,3))

	# Convert the relative timestamp to an absolute timestamp.
	def fixTime(data) -> str:
		global timeStamp
		if timeStamp == None:
			return None
		dt = timeStamp + data/1000
		return dt

	def getField(self,record) -> str:
		data = struct.unpack(self.fmtString,record[self.startPos:self.startPos+self.length])
		if data == ():
			return None
		data = data[0]
		if isinstance(self.scale,int) or isinstance(self.scale,float):
			data = data * self.scale
		elif self.scale != None:
			data = self.scale(data)
		return data

	def flightMode(data) -> str:
		if data == 7: return "Video"
		if data == 8: return "Normal"
		if data == 9: return "Sport"
		return f"{data} Unknown"
	
	def droneMode(data) -> str:
		if data == 0: return "Idle/Off"
		if data == 1: return "Launching"
		if data == 2: return "Flight Mode"
		return f"{data} Unknown"
	
#
# Field specs for an Atom2 log.
#
ATOM2_FORMAT = [
	# fields appear in the order they should be in the CSV file.
	FLFD("utc (ms)", "<Q", 5, 8, FLFD.fixTime), # elapsed time since the drone started.
	FLFD("lat (deg)", "<i", 47, 4, FLFD.fixLatLong), # drone latitude * 1e7
	FLFD("lon (deg)", "<i", 51, 4, FLFD.fixLatLong), # drone latitude * 1e7
	FLFD("alt (m)", "<f", 328, 4, FLFD.fixAlt), # No idea if this is right...
	FLFD("dist (m)", "<f", 416, 4), # Distance to home in meters ?
	FLFD("heading (deg)", "<f", 376, 4, FLFD.r2d), # compass heading.
	FLFD("FCOUNTER", "<H", 17, 2), # how many times the drone has flown
	FLFD("Satellites","<B", 46, 1), # how many sats were visible
	FLFD("Controller Lat (deg)", "<i", 144, 4, FLFD.fixLatLong), # relative controller latitude? Not needed
	FLFD("Controller Lon (deg)", "<i", 148, 4, FLFD.fixLatLong), # relative controller longitude? Not needed
	#FLFD("HLAT", "<i", 420, 4, FLFD.fixLatLong), # home latitude * 1e7 Not needed.
	#FLFD("HLONG", "<i", 424, 4, FLFD.fixLatLong), # home longitude * 1e7 Not needed.
	#FLFD("GPS","<f",269, 4), # GPS status. float?!?
	FLFD("ACTIVE", "<B", 280, 1), # 0 = active, 1 = idle.
	FLFD("M1STATE", "<B", 297, 1), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
	FLFD("M2STATE", "<B", 298, 1), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
	FLFD("M3STATE", "<B", 299, 1), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
	FLFD("M4STATE", "<B", 300, 1), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
	FLFD("Battery V1 (mv)", "<h", 440, 2), # Voltage 1
	FLFD("Battery V2 2 (mv)", "<h", 442, 2), # Voltage 2
	FLFD("Battery Current (ma)", "<h", 444, 2, abs), # Current drain.
	FLFD("Battery Level", "<B", 451, 1), # Current battery charge.
	FLFD("Battery Temp (c)", "<B", 462, 1), # Temperature in Celcius.
	FLFD("Flight Mode (text)", "<B", 433, 1, FLFD.flightMode), # Flight Mode: Video, Normal, Sports.
	FLFD("Drone Mode (text)", "<B", 456, 1, FLFD.droneMode), # 0 = motors off, 1 = grounded/launching, 2 = flying, 3 = landing.
	FLFD("Positioning Mode", "<B", 457, 1) # 3 = GPS, OPTI = 2, Other values unclear.
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
		return f"{color}{record.levelname:<8}\033[0m {super().format(record)}"

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
	global timeStamp
	baseName = os.path.basename(fileName)
	baseName, extension = os.path.splitext(baseName)
	timeStamp = datetime.datetime.strptime(re.sub("-.*", "", baseName), "%Y%m%d%H%M%S").timestamp()*1000
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
			error = 0
			for flfd in fieldList:
				#logger.debug(f"extracting {flfd.name}")
				data = flfd.getField(record)
				if data == None:
					#logging.warning(f"Illegal value for {flfd.name}. Skipping.")
					error = 1
					eCount += 1
					break
				line=line+f"{data}, "
			if error == 0:
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

