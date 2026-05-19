"""
    Parses an Atom Eve FC2 file and returns it as a dictionary.
"""

import os
import struct
import re
import math
import datetime
from logging import Logger

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

    "rc elevator",
    "rc rudder",
    "rc throttle",
    "rc aileron",
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

    "Battery V1 (mv)",
    "Battery V2 (mv)",
    "Battery Current (ma)",
    "Battery Temp (c)",
    "Battery Cycles",

    "Auto",
]

""" These are derived from data in the file in order to compare results. """
DERIVED_DATA = [
    "Battery (mv)", # Total battery voltage.
    "2d Derived Distance (m)", # 2d distance, derived from position and altitude.
    "3d Derived Distance (m)", # 3d distance, derived from position and altitude.
    "2d Travelled Distance (m)", # 2d distance, derived from position and altitude.
    "3d Travelled Distance (m)", # 3d distance, derived from position and altitude.
    "2d Derived Speed (m/s)", # derived from delta X and delta Y.
    "3d Derived Speed (m/s)", # derived from delta X, Y, Z.
    "Date/Time", # derived from elapsed.
]

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
    __slots__ = ("name", "fmt_string", "start_pos", "length", "scale")

    def __init__(self, name, fmt_string, start_pos, length, scale=None):
        self.name = name
        self.fmt_string = fmt_string
        self.start_pos = start_pos
        self.length = length
        self.scale = scale

    @staticmethod
    def radian_heading_to_degrees(data) -> float:
        """radian compass heading to decimal degrees."""
        if not math.isfinite(data):
            raise BadData(f"Bad radian value {data}.")
        result = round((360 + data * 180/math.pi) % 360, 3)
        return result

    @staticmethod
    def radians_to_degrees(data) -> float:
        """radians to decimal degrees."""
        if not math.isfinite(data):
            raise BadData(f"Bad radian value {data}.")
        result = round(data * 180/math.pi, 3)
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
    def flight_mode(data) -> str:
        """Convert the flight mode value to a readable string."""
        f_mode = { 7: "Video", 8: "Normal", 9: "Sport"}
        value = f_mode.get(data,None)
        if value is None:
            raise BadData(f"\"{data}\" is not a valid flight mode.")
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

    # This is used when trying to investigate unknown parts of the record.
    @staticmethod
    def hex_dump(data, width: int = 1) -> str:
        """Convert an arbitrary value to a hexadecimal number."""
        return f"\"0x{data:0{width*2}x}\""

    @staticmethod
    def round3(data):
        """ Round the value to two digits after the decimal."""
        return round(data,3)

    @staticmethod
    def rc_quality(data):
        """ Scale the RC quality field to 0-100. """
        return data/35

    @staticmethod
    def rc_stick_scale(data):
        """ Scale the RC stick fields to 0-2048. """
        return round(data*1024.0+1024.0,3)

    @staticmethod
    def rc_neg_stick_scale(data):
        """ Scale the RC stick fields to 0-2048. """
        return round(data*-1024.0+1024.0,3)

    def get_field(self,record) -> str:
        """Extract a field from the binary record."""
        (data,) = struct.unpack(
            self.fmt_string,
            record[self.start_pos:self.start_pos+self.length]
        )

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
    FLFD("utc (ms)", "<Q", 5, 8), # Absolute time in ms.
    FLFD("elapsed (us)", "<Q", 5, 8), # Relative time in microseconds.
    FLFD("Flight Counter", "<H", 17, 2), # Number of flights.
    FLFD("Drone Mode (text)", "<B", 428, 1, FLFD.drone_mode),
    FLFD("Auto", "<B", 429, 1),
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
    FLFD("Wind Speed (m/s)", "<f", 404, 4, FLFD.round3),
    FLFD("Wind (deg)", "<f", 408, 4, FLFD.radian_heading_to_degrees),
    FLFD("Thrust", "<f", 412, 4, FLFD.round3),

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
    FLFD("Battery Cycles", "<H", 494, 2),

    #
    # Controls. Raw values range frrom -1.0 to 1.0 but that Telemetry Overlay
    # requires them to be scaled 0-2048.
    #
    FLFD("rc throttle","<f",89,4, FLFD.rc_neg_stick_scale),
    FLFD("rc rudder","<f",93,4, FLFD.rc_stick_scale),
    FLFD("rc elevator","<f",97,4, FLFD.rc_neg_stick_scale),
    FLFD("rc aileron","<f",101,4, FLFD.rc_stick_scale),
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

def _add_derived_fields(record, prev):
    """
    Adds calculated fields or modifies existing fields based on
    other information.
    """

    # Merge the rth flag and the drone mode.
    if record["Auto"] > 0:
        if record["Drone Mode (text)"] == "Flying":
            if record["Auto"] == 1:
                record["Drone Mode (text)"] = "AI: RTH"
            elif record["Auto"] == 2:
                record["Drone Mode (text)"] = "AI: WPT"
            elif record["Auto"] == 6:
                record["Drone Mode (text)"] = "AI: QS"
            else:
                record["Drone Mode (text)"] = f"AI: ({record['Auto']})"
        elif record["Drone Mode (text)"] == "Launching":
            if record["Auto"] > 0:
                record["Drone Mode (text)"] = "AI: Launch"

    record["Battery (mv)"] = record["Battery V1 (mv)"] + \
        record["Battery V2 (mv)"]

    record["2d Derived Distance (m)"] = round(math.sqrt(
            record["Position X (m)"]**2 +
            record["Position Y (m)"]**2),3)
    record["3d Derived Distance (m)"] = round(math.sqrt(
            record["Position X (m)"]**2 +
            record["Position Y (m)"]**2 +
            record["alt (m)"]**2),3)

    if prev is None:
        record["3d Travelled Distance (m)"] = 0.0
        record["2d Travelled Distance (m)"] = 0.0
    else:
        dX2 = (record["Position X (m)"] - prev["Position X (m)"])**2
        dY2 = (record["Position Y (m)"] - prev["Position Y (m)"])**2
        dZ2 = (record["alt (m)"] - prev["alt (m)"])**2
        record["2d Travelled Distance (m)"] = round(
            prev["2d Travelled Distance (m)"] +
            math.sqrt(dX2 + dY2),3)
        record["3d Travelled Distance (m)"] = round(
            prev["3d Travelled Distance (m)"] +
            math.sqrt(dX2 + dY2 + dZ2),3)

    record["2d Derived Speed (m/s)"] = round(math.sqrt(
            record["delta X (m/s)"]**2 +
            record["delta Y (m/s)"]**2
        ), 3)
    record["3d Derived Speed (m/s)"] = round(math.sqrt(
            record["delta X (m/s)"]**2 +
            record["delta Y (m/s)"]**2 +
            record["delta Z (m/s)"]**2
        ), 3)

    record["Date/Time"] = datetime.datetime.utcfromtimestamp(record["utc (ms)"]/1000)

# Extract timestamp from filename
def parse_filename(file_name:str):
    base_name, _ = os.path.splitext(os.path.basename(file_name))
    timestamp_ms = None
    try:
        timestamp_ms = datetime.datetime.strptime(
            re.sub("-.*", "", base_name),
            "%Y%m%d%H%M%S"
        ).timestamp() * 1000
    except ValueError:
        raise BadData(f"Could not parse timestamp from filename: \"{base_name}\"")

    return timestamp_ms

def atom2_parser(file_name: str = None, fields: dict = ATOM2_FIELDS, logger: Logger = None) -> list[dict]:
    """
    Parse Atom2 flight log and return a list of flight log records.

    Args:
        file_name: Path to .fc2 file
        fields: the field definitions to use.
        logger: a running instance of the Logger class.
    """

    timestamp_ms = None
    def fix_time(data) -> str:
        """Convert the relative timestamp to an absolute timestamp."""
        if timestamp_ms is None:
            raise BadData("Absolute time stamp is unset.")
        dt = timestamp_ms + data/1000
        return dt

    if file_name is None:
        raise BadData("You must provide a file name.")
    if logger is None:
        raise BadData("You must specify the logger.")

    timestamp_ms = parse_filename(file_name)

    with open(file_name, mode="rb") as flight_file:
        record_count = 0
        error_count = 0

        elapsed = 0
        records = []
        prev_record = None

        # Replace any references to utc with a version that has
        # the timestamp conversion.
        corrected_fields = [
            FLFD(f.name, f.fmt_string, f.start_pos, f.length,
                 fix_time if f.name == "utc (ms)" else f.scale)
            for f in fields
        ]

        while True:
            data = flight_file.read(ATOM_RECORD_LEN)
            if len(data) == 0:
                break
            if len(data) < ATOM_RECORD_LEN:
                logger.warning("Record %s truncated.", record_count)
                break

            record_count += 1
            record = {}
            try:
                for field in corrected_fields:
                    field_data = field.get_field(data)
                    if field_data is None:
                        raise BadData(f"Illegal value for {field.name}")
                    record[field.name] = field_data
            except BadData as e:
                logger.debug(
                    "Skipping record %s due to error %s",
                    record_count,
                    e
                )
                error_count += 1
                continue
            except struct.error as e:
                logger.critical(
                    "Bad field %s due to error %s",
                    field.name,
                    e
                )
                raise

            # Validation and derived fields follow.

            # This seems to happen if you reboot the drone without
            # rebooting the controller?!?
            current = record["elapsed (us)"]
            if current < elapsed:
                logger.warning(
                    "Time went backwards at record %s. Trying to fix.",
                    record_count)
                timestamp_ms = timestamp_ms + elapsed/1000
                record["utc (ms)"] = timestamp_ms
                error_count += 1
            elapsed = current

            # GPS coordinates can be wildly wrong if the drone hasn't
            # achieved a lock yet.
            if record["GPS Lock"] != "Yes" and (
                record["lat (deg)"] != "" or
                record["lon (deg)"] != ""):
                record["lat (deg)"] = ""
                record["lon (deg)"] = ""
                logger.debug(
                    "Suppressing GPS data before GPS lock in record %s",
                    record_count
                )
                error_count += 1
                continue
            if record["GPS Lock"] == "Yes" and not is_valid_latlon(record["lat (deg)"],
                                    record["lon (deg)"]):
                logger.debug(
                    "Skipping record %s due to invalid GPS data.",
                    record_count
                )
                error_count += 1
                continue

            _add_derived_fields(record, prev_record)

            records.append(record)
            prev_record = record

    logger.info(
        "%s valid records and %s invalid record(s) in %s.",
        record_count,
        error_count,
        file_name
    )
    return records

def log_stats(logger:Logger, records):
    stats = {}

    # Build the min/max for every numeric field.
    for r in records:
        for field_name, value in r.items():
            if  value != "" and isinstance(value, (int, float)):
                field_min, field_max = stats.get(field_name, (value, value))
                stats[field_name] = (min(field_min, value), max(field_max, value))

    logger.info("Field                                     Min              Max")
    for field_name in stats:
        field_min, field_max = stats[field_name]
        logger.info(f"{field_name:25s}: {field_min:17} {field_max:17}")

