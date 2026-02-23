#!python3
'''
Convert information from an Atom-2 flight log into a Telemetry Overlay CSV

TODO: Add a mode that replaces errors with blank data instead of skipping the
      record.

TODO: Do a test to try and corrolate camera modes with fc2 data. Could be
      done without even flying...
'''

import os
import re
import argparse
import sys
import struct
import math
import datetime
import csv
import mwhlogging
from mwhlogging import MWHLogger

my_logger = MWHLogger("csv_extractor")

# This is a hack - we need to extract the start time of the data from the
# file name - but it needs to be used inside code that can't see the value
# unless it is passed globally.
time_stamp: float = None

class BadData(Exception):
    """
    Baby's first exception...
    Used to indicate when an FLFD field fails to parse.
    """

class FLFD:
    """
    Defines one field in the atom flight log data file.

    name:
            The name of the field. Will be used as the column header in the
            CSV output file. If the field uses specific units, they should
            be specified in parens. For example, "lat (deg)" is a
            latitude, in degrees.
    fmt_string
            The Python struct format string used to unpack the field.
    start_pos
            The starting offset of the field in the record.
    length
            The number of bytes in the field.
    scale
            An optional conversion or formatting function.
    """
    def __init__(self, name, fmt_string, start_pos, length, scale=None):
        self.name = name
        self.fmt_string = fmt_string
        self.start_pos = start_pos
        self.length = length
        self.scale = scale

    @staticmethod
    def radian_heading_to_degrees(data) -> float:
        """radians to decimal degrees."""
        result = round((360 + data * 180/math.pi) % 360, 3)
        if math.isnan(result):
            raise BadData(f"Bad radian value {data!r}.", data)
        return result

    @staticmethod
    def radians_to_degrees(data) -> float:
        """radians to decimal degrees."""
        result = round(data * 180/math.pi, 3)
        if math.isnan(result):
            raise BadData(f"Bad radian value {data!r}.", data)
        return result

    @staticmethod
    def fix_lat_lon(data):
        """Convert Atom 2 lat/lon integers to floating point."""
        if data == 0:
            return "" # Treat as missing data.
        return data / 1e7

    @staticmethod
    def fix_alt(data) -> float:
        """Sometimes the altitude appears as a negative number. No idea why."""
        return abs(round(data,3))

    @staticmethod
    def fix_hdop(data) -> float:
        """Scale the HDOP value."""
        return data/100.0

    @staticmethod
    def fix_time(data) -> str:
        """Convert the relative timestamp to an absolute timestamp."""
        #global time_stamp
        if time_stamp is None:
            return None # error case.
        dt = time_stamp + data/1000
        return dt

    @staticmethod
    def flight_mode(data) -> str:
        """Convert the flight mode value to a readable string."""
        f_mode = { 7: "Video", 8: "Normal", 9: "Sport"}
        value = f_mode.get(data,None)
        if value is None:
            raise BadData(f"\"{data}\" is not a valid positioning mode.")
        return value

    @staticmethod
    def drone_mode(data) -> str:
        """Convert the drone mode value to a readable string."""
        d_mode = { 0: "Idle/Off", 1: "Launching", 2: "Flying", 3: "Landing"}
        value = d_mode.get(data,None)
        if value is None:
            raise BadData(f"\"{data}\" is not a valid drone mode.")
        return value

    @staticmethod
    def positioning_mode(data) -> str:
        """Convert the position mode value to a readable string."""
        p_mode = {1: "ATTI", 2: "OPTI", 3: "GPS"}
        value = p_mode.get(data,None)
        if value is None:
            raise BadData(f"\"{data}\" is not a valid positioning mode.")
        return value

    @staticmethod
    def motor_state(data) -> str:
        """Convert the motor state value to a readable string."""
        m_state = {3: "Off", 4: "Idle", 5: "Low", 6: "Medium", 7: "High"}
        value = m_state.get(data,None)
        if value is None:
            raise BadData(f"\"{data}\" is not a valid motor state.")
        return value

    @staticmethod
    def gps_lock(data) -> str:
        """Convert the gps lock value to a readable string."""
        return "Yes" if data > 0 else "No"

    # These are used when trying to investigate unknown parts of the record.
    @staticmethod
    def bin_dump(data) -> str:
        """Convert an arbitrary value to a 1-byte binary number."""
        return f"\"0b{data:08b}\""

    @staticmethod
    def hex_dump(data) -> str:
        """Convert an arbitrary value to a 1-byte hexadecimal number."""
        return f"\"0x{data:02x}\""

    @staticmethod
    def hex_dump2(data) -> str:
        """Convert an arbitrary value to a 2-byte hexadecimal number."""
        return f"\"0x{data:04x}\""

    @staticmethod
    def hex_dump4(data) -> str:
        """Convert an arbitrary value to a 4-byte hexadecimal number."""
        return f"\"0x{data:08x}\""

    def hex_dump8(data) -> str:
        """Convert an arbitrary value to a 8-byte hexadecimal number."""
        return f"\"0x{data:08x}\""

    @staticmethod
    def round3(data):
        """ Round the value to two digits after the decimal."""
        return round(data,3)

    @staticmethod
    def rc_quality(data):
        """ Scale the RC quality field to 0-100. """
        return data/35

    def get_field(self,record) -> str:
        """Extract a field from the binary record."""
        data = struct.unpack(
            self.fmt_string,
            record[self.start_pos:self.start_pos+self.length]
        )
        if not data:
            return None
        data = data[0]

        if self.scale is not None:
            data = self.scale(data)
        return data

ATOM_RECORD_LEN = 512

"""
Field definitions for an Atom2 log. Omits fields that are not needed.

    * For a list of all fields and their descriptions see README.md.

    * Capitalization is inconsistent because Telemetry Overlay requires certain
      specific field names in order to understand some fields. So, "standard"
      fields are in lower case while custom fields are capitalized so that
      their labels on TO gauges look right.
"""
ATOM2_FIELDS = [

    #
    # Basic Data
    # 
    # (0-3) Record id.
    FLFD("rid", "<i", 0, 4),
    FLFD("utc (ms)", "<Q", 5, 8, FLFD.fix_time), # Absolute time in ms.
    FLFD("elapsed (us)", "<Q", 5, 8), # Relative time in microseconds.
    FLFD("Flight Counter", "<H", 17, 2), # Number of flights.
    FLFD("Drone Mode (text)", "<B", 428, 1, FLFD.drone_mode),
    FLFD("RTH", "<B", 429, 1),
    FLFD("Positioning Mode (text)", "<B", 430, 1, FLFD.positioning_mode),
    FLFD("Flight Mode (text)", "<B", 433, 1, FLFD.flight_mode),

    #
    # Inertial Measurement Unit
    #
    FLFD("Accelerometer X (m/s2)", "<f", 19, 4, FLFD.round3),
    FLFD("Accelerometer Y (m/s2)", "<f", 23, 4, FLFD.round3),
    FLFD("Accelerometer Z (m/s2)", "<f", 27, 4, FLFD.round3),
    FLFD("Gyroscope X (deg/s)", "<f", 31, 4, FLFD.radians_to_degrees),
    FLFD("Gyroscope Y (deg/s)", "<f", 35, 4, FLFD.radians_to_degrees),
    FLFD("Gyroscope Z (deg/s)", "<f", 39, 4, FLFD.radians_to_degrees),
    FLFD("Barometer", "<h", 43, 2),

    #
    # GNSS & Positioning Data
    #
    FLFD("GPS Lock", "<B", 45, 1, FLFD.gps_lock),
    FLFD("Satellites","<B", 46, 1),
    FLFD("lat (deg)", "<i", 47, 4, FLFD.fix_lat_lon),
    FLFD("lon (deg)", "<i", 51, 4, FLFD.fix_lat_lon),
    FLFD("Air Pressure (pascals)", "<f", 71, 4, FLFD.round3),
    FLFD("HDOP", "<h", 75, 2),
    FLFD("Position X (m)", "<f", 304,4, FLFD.round3),
    FLFD("Position Y (m)", "<f", 308,4, FLFD.round3),
    FLFD("alt (m)", "<f", 328, 4, FLFD.fix_alt),
    FLFD("bank (deg)", "<f", 368, 4, FLFD.radians_to_degrees),
    FLFD("pitch angle (deg)", "<f", 372, 4, FLFD.radians_to_degrees),
    FLFD("heading (deg)", "<f", 376, 4, FLFD.radian_heading_to_degrees),
    FLFD("distance (m)", "<f", 416, 4, FLFD.round3),
    FLFD("Home Lat (deg)", "<i", 420, 4, FLFD.fix_lat_lon),
    FLFD("Home Lon (deg)", "<i", 424, 4, FLFD.fix_lat_lon),

    #
    # Velocity
    #
    FLFD("delta Y (m/s)", "<f", 312, 4, FLFD.round3),
    FLFD("delta X (m/s)", "<f", 316, 4, FLFD.round3),
    FLFD("delta Z (m/s)", "<f", 332, 4, FLFD.round3),
    FLFD("speed (m/s)", "<f", 392,4, FLFD.round3),
    FLFD("Wind Speed (m/s)", "<f", 404, 4, FLFD.round3),
    FLFD("Wind (deg)", "<f", 408, 4, FLFD.radian_heading_to_degrees),
    FLFD("Thrust", "<f", 412, 4, FLFD.round3),
    FLFD("Wind Speed 2 (m/s)", "<f", 458, 4, FLFD.round3),

    # 
    # Compass
    #
    FLFD("Magnetometer X", "<h", 79, 2),
    FLFD("Magnetometer Y", "<h", 83, 2),

    #
    # Motor
    #
    FLFD("Motor 1 State", "<B", 297, 1, FLFD.motor_state),
    FLFD("Motor 2 State", "<B", 299, 1, FLFD.motor_state),
    FLFD("Motor 3 State", "<B", 301, 1, FLFD.motor_state),
    FLFD("Motor 4 State", "<B", 303, 1, FLFD.motor_state),
    FLFD("Motor 1 RPM", "<H", 474, 2),
    FLFD("Motor 2 RPM", "<H", 476, 2),
    FLFD("Motor 3 RPM", "<H", 478, 2),
    FLFD("Motor 4 RPM", "<H", 480, 2),


    #
    # Battery related fields.
    #
    FLFD("Battery V1 (mv)", "<h", 440, 2),
    FLFD("Battery V2 (mv)", "<h", 442, 2),
    FLFD("Battery Current (ma)", "<h", 444, 2, abs),
    FLFD("Battery Temp (c)", "<B", 446, 1),
    FLFD("Battery Level (%)", "<B", 451, 1),

    #
    # Fields that are being tested.
    #
    FLFD("Battery State", "<b", 455, 1),
    FLFD("RC Signal", "<h", 462, 2), 
]


""" The list of fields to include in the basic report. """
BASIC_DATA = [
    "rid",
    "utc (ms)",
    "elapsed (us)",
    "Flight Counter",
    "Drone Mode (text)",
    "Positioning Mode (text)",
    "Flight Mode (text)",

    "GPS Lock",
    "Satellites",
    "lat (deg)",
    "lon (deg)",
    "alt (m)",
    "bank (deg)",
    "pitch angle (deg)",
    "heading (deg)",
    "distance (m)",
    "Home Lat (deg)",
    "Home Lon (deg)",

    "speed (m/s)",
    "Wind Speed (m/s)",
    "Wind (deg)",
    "Thrust",

    "Motor 1 State",
    "Motor 2 State",
    "Motor 3 State",
    "Motor 4 State",
    "Motor 1 RPM",
    "Motor 2 RPM",
    "Motor 3 RPM",
    "Motor 4 RPM",

    "Battery Level (%)",

    "RC Signal",
]

""" These fields are only used in the extended report. """
EXTENDED_DATA = [
    "HDOP",

    "Accelerometer X (m/s2)",
    "Accelerometer Y (m/s2)",
    "Accelerometer Z (m/s2)",
    "Gyroscope X (deg/s)",
    "Gyroscope Y (deg/s)",
    "Gyroscope Z (deg/s)",
    "Barometer",
    "Air Pressure (pascals)",

    "Magnetometer X",
    "Magnetometer Y",

    "delta Y (m/s)",
    "delta X (m/s)",
    "delta Z (m/s)",
    "Position X (m)",
    "Position Y (m)",
    "Wind Speed 2 (m/s)",

    "Battery V1 (mv)",
    "Battery V2 (mv)",
    "Battery Current (ma)",
    "Battery Temp (c)",
    "Battery State",
]

""" These are derived from data in the file in order to compare results. """
VALIDATION_DATA = [
    "2d Derived Distance (m)", # 2d distance, derived from position and altitude.
    "3d Derived Distance (m)", # 3d distance, derived from position and altitude.
    "2d Derived Speed (m/s)", # derived from delta X and delta Y.
    "3d Derived Speed (m/s)", # derived from delta X, Y, Z.
]

def is_valid_latlon(lat, lon) -> bool:
    """
    Some simple validation of some GPS coordinates.

    Duh.
    """
    if lat is None or lon is None or lat == "" or lon == "":
        return False
    # Non-finite?
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    # Range
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return True

def derived_fields(record, validation):
    """
    Adds calculated fields or modifies existing fields based on
    other information.
    """

    # Merge the rth flag and the drone mode.
    if record["RTH"] != 0 and record["Drone Mode (text)"] == "Flying":
        record["Drone Mode (text)"] = "RTH"

    if validation:
        record["2d Derived Distance (m)"] = round(math.sqrt(
                record["Position X (m)"]**2 +
                record["Position Y (m)"]**2
            ), 3)
        record["3d Derived Distance (m)"] = round(math.sqrt(
                record["Position X (m)"]**2 +
                record["Position Y (m)"]**2 +
                record["alt (m)"]**2
            ), 3)

        record["2d Derived Speed (m/s)"] = round(math.sqrt(
                record["delta X (m/s)"]**2 +
                record["delta Y (m/s)"]**2
            ), 3)
        record["3d Derived Speed (m/s)"] = round(math.sqrt(
                record["delta X (m/s)"]**2 +
                record["delta Y (m/s)"]**2 +
                record["delta Z (m/s)"]**2
            ), 3)

def atom_parse(file_name, extended=False, validation=False, destination=None):
    """
    Parse Atom2 flight log and export to CSV.

    Args:
        file_name: Path to .fc2 file
        extended: Include the extended fields in the csv file.
        validation: Adds some calculated fields to compare against data pulled from the file.
    """

    global time_stamp

    # Extract timestamp from filename
    base_name, _ = os.path.splitext(os.path.basename(file_name))
    directory = (destination if destination is not None else os.path.dirname(file_name))

    try:
        time_stamp = datetime.datetime.strptime(
            re.sub("-.*", "", base_name),
            "%Y%m%d%H%M%S"
        ).timestamp() * 1000
    except ValueError:
        my_logger.warning("Could not parse timestamp from filename: %s", base_name)
        sys.exit(-1)

    csv_name = os.path.join(directory,f"{base_name}.csv")
    my_logger.debug("Creating %s", csv_name)
    with open(csv_name, mode="w", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        header = BASIC_DATA + \
            (EXTENDED_DATA if extended else []) + \
            (VALIDATION_DATA if validation else [])

        writer.writerow(header)

        with open(file_name, mode="rb") as flight_file:
            record_count = 0
            error_count = 0

            while True:
                record_count += 1
                data = flight_file.read(ATOM_RECORD_LEN)
                if len(data) == 0:
                    break
                if len(data) < ATOM_RECORD_LEN:
                    my_logger.warning("Record %s truncated.", record_count)
                    break

                record = {}
                try:
                    for field in ATOM2_FIELDS:
                        field_data = field.get_field(data)
                        if field_data is None:
                            raise BadData(f"Illegal value for {field.name}")
                        record[field.name] = field_data
                except BadData as e:
                    my_logger.warning(
                        "Skipping record %s due to error %s",
                        record_count,
                        e
                    )
                    error_count += 1
                    continue
                except struct.error as e:
                    my_logger.critical(
                        "Bad field %s due to error %s",
                        field.name,
                        e
                    )
                    sys.exit(-1)



                # Validation and derived fields follow.

                # GPS coordinates can be wildly wrong if the drone hasn't
                # achieved a lock yet.
                if record["GPS Lock"] != "Yes" and (
                    record["lat (deg)"] != "" or
                    record["lon (deg)"] != ""):
                    record["lat (deg)"] = ""
                    record["lon (deg)"] = ""
                    my_logger.debug(
                        "Suppressing GPS data before GPS lock in record %s",
                        record_count
                    )
                if record["GPS Lock"] == "Yes" and not is_valid_latlon(record["lat (deg)"],
                                     record["lon (deg)"]):
                    my_logger.warning(
                        "Skipping record %s due to invalid GPS data.",
                        record_count
                    )
                    error_count += 1
                    continue

                derived_fields(record, validation)

                row = [record.get(field,"") for field in header]
                writer.writerow(row)

    my_logger.info(
        "%s valid records and %s invalid record(s) in %s.",
        record_count,
        error_count,
        file_name
    )
    print(f"Report {csv_name} complete.")

def main() -> None:
    """ This is the main program. Duh."""
    parser = argparse.ArgumentParser(
        description="Extract telemetry from Potensic Atom 2 flight logs (.fc2)",
        epilog=(
            "Written by Michael Heinz. Based on work done by Michael Heinz, Koen Aerts,\n"
            "and Rob Pritt. See README.md for detailed field documentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-D","--destination",
        type=str,
        default=None,
        help="The directory to write the CSV files to. Defaults to the directory the telemetry file is in."
    )

    parser.add_argument(
        "-l","--log",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="Set log level. 0=error, 1=warning, 2=info, 3=debug."
    )

    parser.add_argument(
        "-L","--logfile",
        type=str,
        default=None,
        help="Redirect logging output to a file."
    )

    parser.add_argument(
        "-x","--extended",
        action="store_true",
        help="Include extended fields"
    )

    parser.add_argument(
        "-v","--validation",
        action="store_true",
        help="Calcuate some additional fields to compare against the raw data."
    )

    parser.add_argument(
        "files",
        nargs="+",
        help="One or more Atom 2 .fc2 files to convert."
    )

    args = parser.parse_args()

    log_levels = [
        mwhlogging.ERROR,
        mwhlogging.WARNING,
        mwhlogging.INFO,
        mwhlogging.DEBUG
    ]

    my_logger.configure_logging(log_levels[args.log], args.logfile)

    print("Atom 2 Flight Log to CSV Converter.")

    for f in args.files:
        _, extension = os.path.splitext(f)
        if not os.path.exists(f):
            my_logger.error("%s does not exist.", f)
            sys.exit(-1)
        elif extension == ".fc2":
            my_logger.info("Parsing %s", f)
            atom_parse(f, extended=args.extended, validation=args.validation, destination=args.destination)
        else:
            my_logger.info("%s appears to be an unsupported file type.", f)
            sys.exit(-1)

if __name__ == '__main__':
    main()
