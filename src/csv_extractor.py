#!python3
'''
Convert information from an Atom-2 flight log into a Telemetry Overlay CSV

TODO: Add code to specify the time stamp as an argument.
TODO: Add code to specify the output file name as an argument.
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
        return f_mode.get(data,None)

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
    def hex_dump(data) -> str:
        """Convert an arbitrary value to a hexadecimal number."""
        return hex(data)

    @staticmethod
    def hex_dump2(data) -> str:
        """Convert an arbitrary value to a 2 digit hexadecimal number."""
        return f"0x{data:04x}"

    @staticmethod
    def hex_dump4(data) -> str:
        """Convert an arbitrary value to a 4 digit hexadecimal number."""
        return f"0x{data:08x}"

    @staticmethod
    def hex_dump8(data) -> str:
        """Convert an arbitrary value to a 8 digit hexadecimal number."""
        return f"0x{data:016x}"

    @staticmethod
    def round3(data):
        """ Round the value to two digits after the decimal."""
        return round(data,3)

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
Field definitions for an Atom2 log.
NOTE: fields that are used in derived fields are omitted.

    * Fields listed in the order they will appear in the CSV file. Not really
      necessary but useful for this analysis.
    * Capitalization is inconsistent because Telemetry Overlay requires certain
      specific field names in order to understand some fields. So, "standard"
      fields are in lower case while custom fields are in upper case so that
      their labels on TO gauges look right.
"""
ATOM2_FIELDS = [
    # (0-3) Record id.
    FLFD("rid", "<i", 0, 4),

    # (4) Always zero.

    # (5-12) elapsed time since logging began, in ms.
    # We extract this twice, once as the relative time, once as the absolute
    # time, which is required by Telemetry Overlay.
    FLFD("utc (ms)", "<Q", 5, 8, FLFD.fix_time), # Absolute time in ms.
    FLFD("elapsed (ms)", "<Q", 5, 8), # Relative time in ms.

    # (13-14) Starts as zero but occasionally changes to one of a few distinct
    # values. Observed values are 0, 25, 30, 35, 40, 120. Initially zero, goes
    # to a non-zero value very early in the log. May occasionally change
    # during flight.
    FLFD("u13", "<H", 13, 2, FLFD.hex_dump4),

    # (15-16) Either zero or equals field 13.
    FLFD("u15", "<H", 15, 2, FLFD.hex_dump4),

    # (17-18) How many times the drone has landed.
    FLFD("Flight Counter", "<H", 17, 2), # Number of flights.

    # (19-44) Internal sensor data?
    FLFD("Accelerometer X (m/s2)", "<f", 19, 4, FLFD.round3),
    FLFD("Accelerometer Y (m/s2)", "<f", 23, 4, FLFD.round3),
    FLFD("Accelerometer Z (m/s2)", "<f", 27, 4, FLFD.round3),
    FLFD("Gyroscope X (deg/s)", "<f", 31, 4, FLFD.radians_to_degrees),
    FLFD("Gyroscope Y (deg/s)", "<f", 35, 4, FLFD.radians_to_degrees),
    FLFD("Gyroscope Z (deg/s)", "<f", 39, 4, FLFD.radians_to_degrees),
    FLFD("Barometer", "<h", 43, 2),

    # GPS data (45-58)
    FLFD("GPS Lock", "<B", 45, 1, FLFD.gps_lock),
    FLFD("Satellites","<B", 46, 1),
    FLFD("lat (deg)", "<i", 47, 4, FLFD.fix_lat_lon),
    FLFD("lon (deg)", "<i", 51, 4, FLFD.fix_lat_lon),
    FLFD("GPS Quality", "<i", 55, 4),

    # Position uncertainty estimates (59-70)
    # These vary by positioning mode:
    #  ATTI (IMU only): Conf2=5.0m, Conf3=10.0m
    #  OPTI (optical):  Conf2=4.0m, Conf3=8.0m
    #  GPS:             Conf2=0.35m, Conf3=0.47m
    #
    #  Note that the correlation here is that these values get lower
    #  as the drone progresses from ATTI to OPTI to GPS and drop further as
    #  "GPS Quality" increases. Since the drone never flies far in either
    #  ATTI or OPTI modes, it is possible that this is not entirely correct.
    FLFD("Confidence1", "<f", 59, 4, FLFD.round3),
    FLFD("Confidence2", "<f", 63, 4, FLFD.round3),
    FLFD("Confidence3", "<f", 67, 4, FLFD.round3),

    FLFD("Barometric Pressure (pascals)", "<f", 71, 4, FLFD.round3),

    # (75-93) Unknown. Probably sensor data.
    #FLFD("u75", "<I", 75, 4, FLFD.hex_dump8),
    #FLFD("u79", "<I", 79, 4, FLFD.hex_dump8),
    #FLFD("u83", "<I", 83, 4, FLFD.hex_dump8),
    #FLFD("Sensor 1", "<h", 87, 2),
    #FLFD("u89", "<H", 89, 2, FLFD.hex_dump4),
    #FLFD("Sensor 2", "<h", 91, 2),
    #FLFD("u93", "<H", 93, 2, FLFD.hex_dump4),

    # (95-295) Unknown.

    # Motor states are understood; the data fields are not.
    FLFD("Motor 1 Data", "<B", 296, 1),
    FLFD("Motor 1 State", "<B", 297, 1, FLFD.motor_state),
    FLFD("Motor 2 Data", "<B", 298, 1),
    FLFD("Motor 2 State", "<B", 299, 1, FLFD.motor_state),
    FLFD("Motor 3 Data", "<B", 300, 1),
    FLFD("Motor 3 State", "<B", 301, 1, FLFD.motor_state),
    FLFD("Motor 4 Data", "<B", 302, 1),
    FLFD("Motor 4 State", "<B", 303, 1, FLFD.motor_state),

    # Position and attitude (304-311) - relative to takeoff (home) point.
    # Not yet known if the position is affected by "dynamic home" mode.
    FLFD("Position X (m)", "<f", 304,4, FLFD.round3),
    FLFD("Position Y (m)", "<f", 308,4, FLFD.round3),

    # (312-327) Unknown. Floating point numbers.
    #FLFD("f312", "<f", 312, 4, FLFD.round3),
    #FLFD("f316", "<f", 316, 4, FLFD.round3),
    #FLFD("f320", "<f", 320, 4, FLFD.round3),
    #FLFD("f324", "<f", 324, 4, FLFD.round3),

    # Altitude above home point, AKA "Position Z".
    FLFD("alt (m)", "<f", 328, 4, FLFD.fix_alt),

    # Unknown region: 332-367. All appear to be valid floating point numbers.
    #FLFD("f332", "<f", 332, 4, FLFD.round3),
    #FLFD("f336", "<f", 336, 4, FLFD.round3),
    #FLFD("f340", "<f", 340, 4, FLFD.round3),
    #FLFD("f344", "<f", 344, 4, FLFD.round3),
    #FLFD("f348", "<f", 348, 4, FLFD.round3),
    #FLFD("f352", "<f", 352, 4, FLFD.round3),
    #FLFD("f356", "<f", 356, 4, FLFD.round3),
    #FLFD("f360", "<f", 360, 4, FLFD.round3),
    #FLFD("f364", "<f", 364, 4, FLFD.round3),

    # orientation and velocity (368-395)
    FLFD("bank (deg)", "<f", 368, 4, FLFD.radians_to_degrees),
    FLFD("pitch angle (deg)", "<f", 372, 4, FLFD.radians_to_degrees),
    FLFD("heading (deg)", "<f", 376, 4, FLFD.radian_heading_to_degrees),
    FLFD("Velocity X (m/s)", "<f", 380,4, FLFD.round3),
    FLFD("Velocity Y (m/s)", "<f", 384,4, FLFD.round3),
    FLFD("Velocity Z (m/s)", "<f", 388,4, FLFD.round3),

    # (392-396) Correlated with drone speed but not perfectly.
    # Consistently 0.25-0.28 m/s larger than sqrt(vx²+vy²+vz²)
    # Unlikely to be ground speed because that would be less than
    # the 3d speed of the drone. Can't be air speed because the
    # drone does not have an air speed indicator.
    FLFD("speed (m/s)", "<f", 392,4, FLFD.round3),

    # Unknown. Might be some sort of warning/detection field. Usually zero.
    # FLFD("f396", "<f", 396,4),

    # (400-403) Always a constant value of 5050.0. Possibly a format id?
    # FLFD("C5050", "<f", 400,4),

    # (404-407) Altitude-related metric? Increases with altitude but not linearly.
    # Possibly a GPS altitude, barometric error, or secondary altitude source.
    # FLFD("Altitude Metric", "<f", 404,4),

    # (408-411) Wind direction in radians.
    FLFD("Wind (deg)", "<f", 408, 4, FLFD.radian_heading_to_degrees),

    # (412-415) Appears to represent the total thrust produced by the drone.
    FLFD("Thrust", "<f", 412, 4, FLFD.round3),

    # (416-417) Ground distance to takeoff point (home) in meters.
    FLFD("distance (m)", "<f", 416, 4, FLFD.round3),

    # (420-427) Location of the takeoff/home point. Need to test if this
    # changes when the home point changes.
    FLFD("Home Lat (deg)", "<i", 420, 4, FLFD.fix_lat_lon), # home latitude * 1e7
    FLFD("Home Lon (deg)", "<i", 424, 4, FLFD.fix_lat_lon), # home longitude * 1e7

    # (428) Unknown.

    # (429) Flag that indicates return-to-home has been activated.
    FLFD("RTH", "<B", 429, 1),

    # (430-432) Unknown.

    # (433) Enumerated flight mode.
    FLFD("Flight Mode (text)", "<B", 433, 1, FLFD.flight_mode),

    # (434-439) Unknown.

    # (440-451) Battery related fields.
    FLFD("Battery V1 (mv)", "<h", 440, 2), # Voltage 1
    FLFD("Battery V2 (mv)", "<h", 442, 2), # Voltage 2
    FLFD("Battery Current (ma)", "<h", 444, 2, abs), # Current drain.
    FLFD("Battery Temp (c)", "<B", 446, 1), # Temperature in Celsius.
    FLFD("Battery Level (%)", "<B", 451, 1), # Current battery charge.

    # Unknown (452-455)

    FLFD("Drone Mode (text)", "<B", 456, 1, FLFD.drone_mode),
    FLFD("Positioning Mode (text)", "<B", 457, 1, FLFD.positioning_mode),

    # (458-511) Unknown.
]

""" The list of fields to include in the basic report. """
BASIC_DATA = [
    "rid",
    "utc (ms)",
    "elapsed (ms)",
    "Flight Counter",
    "GPS Lock",
    "Satellites",
    "lat (deg)",
    "lon (deg)",
    "alt (m)",
    "Distance (m)", # 2d distance from fc2 data.
    "Motor 1 State",
    "Motor 2 State",
    "Motor 3 State",
    "Motor 4 State",
    "Thrust",
    "bank (deg)",
    "pitch angle (deg)",
    "heading (deg)",
    "Wind (deg)",
    "Home Lat (deg)",
    "Home Lon (deg)",
    "Battery Level (%)",
    "Positioning Mode (text)",
    "Flight Mode (text)",
    "Drone Mode (text)",
]

""" These fields are only used in the extended report and may not be correct. """
EXTENDED_DATA = [
    "GPS Quality",
    "Confidence1",
    "Confidence2",
    "Confidence3",
    "Accelerometer X (m/s2)",
    "Accelerometer Y (m/s2)",
    "Accelerometer Z (m/s2)",
    "Gyroscope X (deg/s)",
    "Gyroscope Y (deg/s)",
    "Gyroscope Z (deg/s)",
    "Barometer",
    "Barometric Pressure (pascals)",
    "Position X (m)",
    "Position Y (m)",
    "Velocity X (m/s)",
    "Velocity Y (m/s)",
    "Velocity Z (m/s)",
    "Speed (m/s)", # from the fc2 file.
    "Battery V1 (mv)",
    "Battery V2 (mv)",
    "Battery Current (ma)",
    "Battery Temp (c)",
    "Motor 1 Data",
    "Motor 2 Data",
    "Motor 3 Data",
    "Motor 4 Data",
]

VALIDATION_DATA = [
    "2d Derived Distance (m)", # 2d distance, derived from position and altitude.
    "3d Derived Distance (m)", # 3d distance, derived from position and altitude.
    "Derived Speed (m/s)", # Derived from the velocities.
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
    Adds calculated fields or modifies existing fields.
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
        record["Derived Speed (m/s)"] = round(math.sqrt(
                record["Velocity X (m/s)"]**2 +
                record["Velocity Y (m/s)"]**2 +
                record["Velocity Z (m/s)"]**2
            ), 3)

def atom_parse(file_name, extended=False, validation=False):
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

    try:
        time_stamp = datetime.datetime.strptime(
            re.sub("-.*", "", base_name),
            "%Y%m%d%H%M%S"
        ).timestamp() * 1000
    except ValueError:
        my_logger.warning("Could not parse timestamp from filename: %s", base_name)
        sys.exit(-1)

    csv_name = f"{base_name}.csv"
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
                except (struct.error, BadData) as e:
                    my_logger.error(
                        "Skipping record %s due to error %s",
                        record_count,
                        e
                    )
                    error_count += 1
                    continue

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
        base_name
    )
    my_logger.info("Report %s complete.", csv_name)

def main() -> None:
    """ This is the main program. Duh."""
    parser = argparse.ArgumentParser(
        description="Extract telemetry from Potensic Atom 2 flight logs (.fc2)",
        epilog=(
            "Based on reverse engineering by Michael Heinz, Koen Aerts, and Rob Pitt. "
            "See README.md for detailed field documentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-l","--log",
        type=int,
        choices=[0, 1, 2, 3],
        default=2,
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
            atom_parse(f, extended=args.extended, validation=args.validation)
        else:
            my_logger.info("%s appears to be an unsupported file type.", f)
            sys.exit(-1)

if __name__ == '__main__':
    main()
