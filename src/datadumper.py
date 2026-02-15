#!python3
'''
Exploring the fc2 file format.
'''

import os
import re
import argparse
import sys
import struct
import math
import datetime
import mwhlogging
from mwhlogging import mwhLogger

timeStamp: float

class FLFD:
    def __init__(self, name, fmt_string, start_pos, length, scale=None):
        # This will be the header in the CSV. If it uses specific units, include
        # it in parens. For example, "lat (deg)" is the latitude, in decimal degrees.
        self.name = name
        # how to unpack the data in the flight log.
        self.fmt_string = fmt_string
        # Where the data starts in the flight log record.
        self.start_pos = start_pos
        # the length of the field in the flight log.
        self.length = length
        # A numeric multiplier or parsing function for adjusting the data.
        self.scale = scale

    # radians to decimal degrees.
    def _r2d(data) -> float:
        result = round((360 + data * 180/math.pi) % 360, 3)
        if math.isnan(result):
            # TODO: Figure out better handling of bad records.
            mwhLogger.critical(f"Bad heading value {data} found.");
            sys.exit(-1)
        return result

    # Atom 2 use integers to store the decimal lat/long with 7 digits of precision.
    def _fix_lat_lon(data) -> float:
        if data == 0:
            return "" # Treat this as missing data.
        return data / 1e7

    # No idea why the altitude appears to be a negative number...
    def _fix_alt(data) -> float:
        return abs(round(data,3))

    # Convert the relative timestamp to an absolute timestamp.
    def _fix_time(data) -> str:
        global timeStamp
        if timeStamp == None:
            return None # error case.
        dt = timeStamp + data/1000
        return dt

    def _flight_mode(data) -> str:
        if data == 7: return "Video"
        if data == 8: return "Normal"
        if data == 9: return "Sport"
        return f"{data} Unknown"

    def _drone_mode(data) -> str:
        if data == 0: return "Idle/Off"
        if data == 1: return "Launching"
        if data == 2: return "Flying"
        if data == 3: return "Landing"
        return f"{data} Unknown"

    def positioning_mode(data) -> str:
        if data == 1: return "ATTI"
        if data == 2: return "OPTI"
        if data == 3: return "GPS"
        return f"{data} Unknown"

    def _motor_state(data) -> str:
        if data == 3: return "Off"
        if data == 4: return "Idle"
        if data == 5: return "Low"
        if data == 6: return "Medium"
        if data == 7: return "High"
        return f"{data} Unknown"

    def _gps_lock(data) -> str:
        if data > 0: return "Yes"
        return "No"

    # These are used when trying to investigate unknown parts of the record.
    def _hex_dump(data) -> str:
        return hex(data)

    def _hex_dump2(data) -> str:
        return f"0x{data:04x}"

    def _hex_dump4(data) -> str:
        return f"0x{data:08x}"

    def _hex_dump8(data) -> str:
        return f"0x{data:016x}"

    def _round2(data):
        return round(data*100)/100;

    def getField(self,record) -> str:
        data = struct.unpack(self.fmt_string,record[self.start_pos:self.start_pos+self.length])
        if data == ():
            return None
        data = data[0]
        if isinstance(self.scale,int) or isinstance(self.scale,float):
            data = data * self.scale
        elif self.scale != None:
            data = self.scale(data)
        return data

#
# Field definitions for an Atom2 log.
# NOTE: fields that are used in derived fields are omitted.
#
ATOM2_FORMAT = [
    # fields listed in the order they will appear in the CSV file.
    # Capitalization is inconsistent because Telemetry Overlay requires certain
    # specific field names in order to understand some fields. So, "standard"
    # fields are in lower case while custom fields are in upper case so that
    # their labels on TO gauges look right.
    FLFD("rid", "<i", 0, 4), # Record id.
    FLFD("z4", "<b", 4, 1), # always zero.
    FLFD("elapsed (ms)", "<Q", 5, 8), # Relative time in ms.
    FLFD("u13", "<H", 13, 2), # unknown.
    FLFD("u15", "<H", 13, 2), # unknown.
    FLFD("Flight Counter", "<H", 17, 2), 
    # byte 19. unknown region 26 bytes long.
    FLFD("GPS Lock", "<B", 45, 1, FLFD._gps_lock),
    FLFD("Satellites","<B", 46, 1), # how many sats were visible
    FLFD("lat (deg)", "<i", 47, 4, FLFD._fix_lat_lon), # drone latitude * 1e7
    FLFD("lon (deg)", "<i", 51, 4, FLFD._fix_lat_lon), # drone longitude * 1e7
    FLFD("GPS Quality", "<i", 55, 4), # higher is better.
    FLFD("confidence1", "<f", 59, 4), 
    FLFD("confidence2", "<f", 63, 4), 
    FLFD("confidence3", "<f", 67, 4), 
    # byte 71. unknown region 225 bytes long.
    FLFD("Motor 1 Data", "<B", 296, 1),
    FLFD("Motor 1 State", "<B", 297, 1, FLFD._motor_state), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
    FLFD("Motor 2 Data", "<B", 298, 1),
    FLFD("Motor 2 State", "<B", 299, 1, FLFD._motor_state), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
    FLFD("Motor 3 Data", "<B", 300, 1),
    FLFD("Motor 3 State", "<B", 301, 1, FLFD._motor_state), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
    FLFD("Motor 4 Data", "<B", 302, 1),
    FLFD("Motor 4 State", "<B", 303, 1, FLFD._motor_state), # 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high
    FLFD("Position X (m)", "<f", 304,4, FLFD._round2), 
    FLFD("Position Y (m)", "<f", 308,4, FLFD._round2),
    FLFD("Pitch (deg)", "<f", 312, 4, FLFD._round2),
    FLFD("Roll (deg)", "<f", 316, 4, FLFD._round2),
    FLFD("Pitch Rate", "<f", 320, 4, FLFD._round2),
    FLFD("Roll Rate", "<f", 324, 4, FLFD._round2),
    FLFD("alt (m)", "<f", 328, 4, FLFD._fix_alt), # Altitude above controller(?)
    FLFD("heading (deg)", "<f", 376, 4, FLFD._r2d), # compass heading.
    FLFD("Delta X (m)", "<f", 380,4, FLFD._round2),
    FLFD("Delta Y (m)", "<f", 384,4, FLFD._round2),
    FLFD("Delta Z (m)", "<f", 388,4, FLFD._round2),
    FLFD("Speed (m/s)", "<f", 392,4),
    FLFD("F396", "<f", 396,4),
    FLFD("C5050", "<f", 400,4),
    FLFD("F404", "<f", 404,4),
    FLFD("Wind (deg)", "<f", 408, 4, FLFD._r2d), # wind direction
    FLFD("Thrust", "<f", 412, 4, FLFD._round2), # A unitless representation of how hard the motors are working.
    FLFD("dist (m)", "<f", 416, 4, FLFD._fix_alt), # Distance to home in meters. Using fixAlt to round the number.
    FLFD("Home Lat (deg)", "<i", 420, 4, FLFD._fix_lat_lon), # home latitude * 1e7
    FLFD("Home Lon (deg)", "<i", 424, 4, FLFD._fix_lat_lon), # home longitude * 1e7
    FLFD("Flight Mode (text)", "<B", 433, 1, FLFD._flight_mode), # Flight Mode: Video, Normal, Sports.
    FLFD("Battery V1 (mv)", "<h", 440, 2), # Voltage 1
    FLFD("Battery V2 2 (mv)", "<h", 442, 2), # Voltage 2
    FLFD("Battery Current (ma)", "<h", 444, 2, abs), # Current drain.
    FLFD("Battery Temp (c)", "<B", 446, 1), # Temperature in Celcius.
    FLFD("Battery Level (%)", "<B", 451, 1), # Current battery charge.
    FLFD("Positioning Mode (text)", "<B", 457, 1, FLFD.positioning_mode), # 3 = GPS, OPTI = 2, Other values unclear.
]

ATOM_RECORD_LEN = 512

def atom_parse(fieldList, fileName):
    global timeStamp
    baseName = os.path.basename(fileName)
    baseName, extension = os.path.splitext(baseName)
    timeStamp = datetime.datetime.strptime(re.sub("-.*", "", baseName), "%Y%m%d%H%M%S").timestamp()*1000
    csv_name=f"{baseName}.csv"

    mwhLogger.debug(f"Creating {csv_name}.")

    try:
        csv_file = open(csv_name, mode="w")
    except:
        mwhLogger.critical(f"Unable to create {csv_name}. Terminating.")
        sys.exit(-1)

    # These fields require special handling.
    dm = FLFD("Drone Mode (text)", "<B", 456, 1, FLFD._drone_mode)
    rth = FLFD("Return to Home", "<B", 429,1) # !0 if RTH is active.

    header=""
    for flfd in fieldList:
        header+=f"{flfd.name}, "
    header+=f"{dm.name}"
    print(header, file=csv_file)

    with open(fileName, mode="rb") as flight_file:
        rCount = 0
        eCount = 0

        while True:
            record = flight_file.read(ATOM_RECORD_LEN)
            if len(record) < 512:
                break
            rCount += 1

            line=""
            error = 0
            for flfd in fieldList:
                #mwhLogger.debug(f"extracting {flfd.name}")
                data = flfd.getField(record)
                if data == None:
                    mwhLogger.warning(f"Illegal value for {flfd.name}. Skipping.")
                    error = 1
                    eCount += 1
                    break
                line=line+f"{data}, "

            if error == 0:
                # We combine these two fields into one.
                dmode = dm.getField(record)
                rthome = rth.getField(record)
                if rthome != 0 and dmode == "Flying":
                    dmode = "RTH"
                line += f"{dmode}"

                print(line, file=csv_file)

    mwhLogger.info(f"{rCount} valid records in {csv_name}. {eCount} bad records in file.")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Potensic Flight Log files to Telemetry Overlay format.",
        epilog="Written by Michael Heinz, based on information provided by potdrownflightparser by koen-arts.")
    parser.add_argument("-l","--log", type=int, help="Set log level. 0=error, higher values increase logging.", default=2)
    parser.add_argument("files", nargs="+", help="One or more FlightLog files to convert.")
    args = parser.parse_args()

    match args.log:
        case 0:
            mwhLogger.setLevel(mwhlogging.ERROR)
        case 1:
            mwhLogger.setLevel(mwhlogging.WARNING)
        case 2:
            mwhLogger.setLevel(mwhlogging.INFO)
        case _:
            mwhLogger.setLevel(mwhlogging.DEBUG)

    print(f"Atom Flight Log to Telemetry Overlay Converter.")

    for f in args.files:
        baseName, extension = os.path.splitext(f)
        if not os.path.exists(f):
            mwhLogger.error(f"{f} does not exist.")
            sys.exit(-1)
        elif extension == ".fc2":
            mwhLogger.info(f"Parsing {f} as an Atom2 log file.")
            atom_parse(ATOM2_FORMAT, f)
        elif extension == ".fc":
            mwhLogger.error(f"Sorry, I can't handle Atom1 log files yet. Can't parse {f}.")
            sys.exit(-1)
        else:
            mwhLogger.info(f"{f} appears to be an unsupported file type.")
            sys.exit(-1)

if __name__ == '__main__':
    main()

