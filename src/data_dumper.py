#!python3
'''
Version of Atom Data Extractor focused on exploring the unknown parts of the
record format.
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

my_logger = MWHLogger("data_dumper")

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
        """Scale the HDOP value. """
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
        return f"\"0b{data:08b}"

    @staticmethod
    def hex_dump(data) -> str:
        """Convert an arbitrary value to a 1-byte hexadecimal number."""
        return f"0x{data:02x}"

    @staticmethod
    def hex_dump2(data) -> str:
        """Convert an arbitrary value to a 2-byte hexadecimal number."""
        return f"0x{data:04x}"

    @staticmethod
    def hex_dump4(data) -> str:
        """Convert an arbitrary value to a 4-byte hexadecimal number."""
        return f"0x{data:08x}"

    def hex_dump8(data) -> str:
        """Convert an arbitrary value to a 8-byte hexadecimal number."""
        return f"0x{data:08x}"

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
    * Check the README.md for more descriptions of the fields.
    * Fields listed in the order they appear in the fc2 record. This makes
      it a bit harder to read the CSV but makes it a bit easier to check for
      related data adjacent to known fields.
"""
ATOM2_FIELDS = [
    # (0-3) Record id.
    FLFD("rid", "<i", 0, 4),

    # (4) Always zero.
    FLFD("z1", "<b", 4, 1),

    # (5-12) elapsed time since logging began, in microseconds.
    # We extract this twice, once as the relative time, once as the absolute
    # time, which is required by Telemetry Overlay.
    # (Data Dumper isn't meant for generating TO videos, but the videos are
    # very handy for comparing data with what the drone was doing at the
    # time...)
    FLFD("utc (ms)", "<Q", 5, 8, FLFD.fix_time), # Absolute time in ms.
    FLFD("elapsed (us)", "<Q", 5, 8), # Relative time in microseconds.

    # (13-14) Starts as zero but occasionally changes to one of a few distinct
    # values. Observed values are 0, 25, 30, 35, 40, 120. Initially zero, goes
    # to a non-zero value very early in the log. May occasionally change
    # during flight.
    FLFD("u13", "<H", 13, 2, FLFD.hex_dump2),

    # (15-16) Either zero or equals field 13.
    FLFD("u15", "<H", 15, 2, FLFD.hex_dump2),

    # (17-18) How many times the drone has landed.
    FLFD("Flight Counter", "<H", 17, 2), # Number of flights.

    # (19-44) IMU sensor data
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

    # Position uncertainty estimates? (59-70)
    # These vary by positioning mode:
    #  ATTI (IMU only): Conf2=5.0m, Conf3=10.0m
    #  OPTI (optical):  Conf2=4.0m, Conf3=8.0m
    #  GPS:             Conf2=0.35m, Conf3=0.47m
    #
    #  Note that the correlation here is that these values get lower
    #  as the drone progresses from ATTI to OPTI to GPS and drop further as
    #  "GPS Quality" increases. Since the drone never flies far in either
    #  ATTI or OPTI modes, it is possible that this is not correct.
    FLFD("f59", "<f", 59, 4, FLFD.round3),
    FLFD("f63", "<f", 63, 4, FLFD.round3),
    FLFD("f67", "<f", 67, 4, FLFD.round3),

    FLFD("Air Pressure (pascals)", "<f", 71, 4, FLFD.round3),

    # (75-76) HDOP * 100
    FLFD("HDOP", "<h", 75, 2, FLFD.fix_hdop),

    # (77-78) Unknown.
    FLFD("u77", "<h", 77, 2),

    # (79-80) Raw magnetometer X component?
    FLFD("Magnetometer X", "<h", 79, 2),

    # (81-82) Unknown.
    FLFD("u81","<b", 81, 1),
    FLFD("u82","<b",82,1),

    # (83-84) Raw magnetometer Y component?
    FLFD("Magnetometer Y", "<h", 83, 2),

    # (85-88) Unknown.
    FLFD("u85","<i",85,4, FLFD.hex_dump4),

    # (89-104) The positions of the control sticks (when in mode-2?)
    # Review of videos and data confirm a strong match.
    FLFD("Elevator","<f",89,4),
    FLFD("Rudder","<f",93,4),
    FLFD("Throttle","<f",97,4),
    FLFD("Aileron","<f",101,4),

    # (105-295) Unknown.
    FLFD("u105","<b",105,1),
    FLFD("u106","<b",106,1),
    FLFD("u107","<b",107,1),
    FLFD("u108","<b",108,1),
    FLFD("u109","<b",109,1),
    FLFD("u110","<b",110,1),
    FLFD("u111","<b",111,1),
    FLFD("u112","<b",112,1),
    FLFD("u113","<b",113,1),
    FLFD("u114","<b",114,1),
    FLFD("u115","<b",115,1),
    FLFD("u116","<b",116,1),
    FLFD("u117","<b",117,1),
    FLFD("u118","<b",118,1),
    FLFD("u119","<b",119,1),
    FLFD("u120","<b",120,1),
    FLFD("u121","<b",121,1),
    FLFD("u122","<b",122,1),
    FLFD("u123","<b",123,1),
    FLFD("u124","<b",124,1),
    FLFD("u125","<b",125,1),
    FLFD("u126","<b",126,1),
    FLFD("u127","<b",127,1),
    FLFD("u128","<b",128,1),
    FLFD("u129","<b",129,1),
    FLFD("u130","<b",130,1),
    FLFD("u131","<b",131,1),
    FLFD("u132","<b",132,1),
    FLFD("u133","<b",133,1),
    FLFD("u134","<b",134,1),
    FLFD("u135","<b",135,1),
    FLFD("u136","<b",136,1),
    FLFD("u137","<b",137,1),
    FLFD("u138","<b",138,1),
    FLFD("u139","<b",139,1),
    FLFD("u140","<b",140,1),
    FLFD("u141","<b",141,1),
    FLFD("u142","<b",142,1),
    FLFD("u143","<b",143,1),
    FLFD("u144","<b",144,1),
    FLFD("u145","<b",145,1),
    FLFD("u146","<b",146,1),
    FLFD("u147","<b",147,1),
    FLFD("u148","<b",148,1),
    FLFD("u149","<b",149,1),
    FLFD("u150","<b",150,1),
    FLFD("u151","<b",151,1),
    FLFD("u152","<b",152,1),
    FLFD("u153","<b",153,1),
    FLFD("u154","<b",154,1),
    FLFD("u155","<b",155,1),
    FLFD("u156","<b",156,1),
    FLFD("u157","<b",157,1),
    FLFD("u158","<b",158,1),
    FLFD("u159","<b",159,1),
    FLFD("u160","<b",160,1),
    FLFD("u161","<b",161,1),
    FLFD("u162","<b",162,1),
    FLFD("u163","<b",163,1),
    FLFD("u164","<b",164,1),
    FLFD("u165","<b",165,1),
    FLFD("u166","<b",166,1),
    FLFD("u167","<b",167,1),
    FLFD("u168","<b",168,1),
    FLFD("u169","<b",169,1),
    FLFD("u170","<b",170,1),
    FLFD("u171","<b",171,1),
    FLFD("u172","<b",172,1),
    FLFD("u173","<b",173,1),
    FLFD("u174","<b",174,1),
    FLFD("u175","<b",175,1),
    FLFD("u176","<b",176,1),
    FLFD("u177","<b",177,1),
    FLFD("u178","<b",178,1),
    FLFD("u179","<b",179,1),
    FLFD("u180","<b",180,1),
    FLFD("u181","<b",181,1),
    FLFD("u182","<b",182,1),
    FLFD("u183","<b",183,1),
    FLFD("u184","<b",184,1),
    FLFD("u185","<b",185,1),
    FLFD("u186","<b",186,1),
    FLFD("u187","<b",187,1),
    FLFD("u188","<b",188,1),
    FLFD("u189","<b",189,1),
    FLFD("u190","<b",190,1),
    FLFD("u191","<b",191,1),
    FLFD("u192","<b",192,1),
    FLFD("u193","<b",193,1),
    FLFD("u194","<b",194,1),
    FLFD("u195","<b",195,1),
    FLFD("u196","<b",196,1),
    FLFD("u197","<b",197,1),
    FLFD("u198","<b",198,1),
    FLFD("u199","<b",199,1),
    FLFD("u200","<b",200,1),
    FLFD("u201","<b",201,1),
    FLFD("u202","<b",202,1),
    FLFD("u203","<b",203,1),
    FLFD("u204","<b",204,1),
    FLFD("u205","<b",205,1),
    FLFD("u206","<b",206,1),
    FLFD("u207","<b",207,1),
    FLFD("u208","<b",208,1),
    FLFD("u209","<b",209,1),
    FLFD("u210","<b",210,1),
    FLFD("u211","<b",211,1),
    FLFD("u212","<b",212,1),
    FLFD("u213","<b",213,1),
    FLFD("u214","<b",214,1),
    FLFD("u215","<b",215,1),
    FLFD("u216","<b",216,1),
    FLFD("u217","<b",217,1),
    FLFD("u218","<b",218,1),
    FLFD("u219","<b",219,1),
    FLFD("u220","<b",220,1),
    FLFD("u221","<b",221,1),
    FLFD("u222","<b",222,1),
    FLFD("u223","<b",223,1),
    FLFD("u224","<b",224,1),
    FLFD("u225","<b",225,1),
    FLFD("u226","<b",226,1),
    FLFD("u227","<b",227,1),
    FLFD("u228","<b",228,1),
    FLFD("u229","<b",229,1),
    FLFD("u230","<b",230,1),
    FLFD("u231","<b",231,1),
    FLFD("u232","<b",232,1),
    FLFD("u233","<b",233,1),
    FLFD("u234","<b",234,1),
    FLFD("u235","<b",235,1),
    FLFD("u236","<b",236,1),
    FLFD("u237","<b",237,1),
    FLFD("u238","<b",238,1),
    FLFD("u239","<b",239,1),
    FLFD("u240","<b",240,1),
    FLFD("u241","<b",241,1),
    FLFD("u242","<b",242,1),
    FLFD("u243","<b",243,1),
    FLFD("u244","<b",244,1),
    FLFD("u245","<b",245,1),
    FLFD("u246","<b",246,1),
    FLFD("u247","<b",247,1),
    FLFD("u248","<b",248,1),
    FLFD("u249","<b",249,1),
    FLFD("u250","<b",250,1),
    FLFD("u251","<b",251,1),
    FLFD("u252","<b",252,1),
    FLFD("u253","<b",253,1),
    FLFD("u254","<b",254,1),
    FLFD("u255","<b",255,1),
    FLFD("u256","<b",256,1),
    FLFD("u257","<b",257,1),
    FLFD("u258","<b",258,1),
    FLFD("u259","<b",259,1),
    FLFD("u260","<b",260,1),
    FLFD("u261","<b",261,1),
    FLFD("u262","<b",262,1),
    FLFD("u263","<b",263,1),
    FLFD("u264","<b",264,1),
    FLFD("u265","<b",265,1),
    FLFD("u266","<b",266,1),
    FLFD("u267","<b",267,1),
    FLFD("u268","<b",268,1),
    FLFD("u269","<b",269,1),
    FLFD("u270","<b",270,1),
    FLFD("u271","<b",271,1),
    FLFD("u272","<b",272,1),
    FLFD("u273","<b",273,1),
    FLFD("u274","<b",274,1),
    FLFD("u275","<b",275,1),
    FLFD("u276","<b",276,1),
    FLFD("u277","<b",277,1),
    FLFD("u278","<b",278,1),
    FLFD("u279","<b",279,1),
    FLFD("u280","<b",280,1),
    FLFD("u281","<b",281,1),
    FLFD("u282","<b",282,1),
    FLFD("u283","<b",283,1),
    FLFD("u284","<b",284,1),
    FLFD("u285","<b",285,1),
    FLFD("u286","<b",286,1),
    FLFD("u287","<b",287,1),
    FLFD("u288","<b",288,1),
    FLFD("u289","<b",289,1),
    FLFD("u290","<b",290,1),
    FLFD("u291","<b",291,1),
    FLFD("u292","<b",292,1),
    FLFD("u293","<b",293,1),
    FLFD("u294","<b",294,1),

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
    FLFD("delta Y (m/s)", "<f", 312, 4, FLFD.round3),
    FLFD("delta X (m/s)", "<f", 316, 4, FLFD.round3),
    FLFD("u320", "<f", 320, 4, FLFD.round3),
    FLFD("u324", "<f", 324, 4, FLFD.round3),

    # Altitude above home point, AKA "Position Z".
    FLFD("alt (m)", "<f", 328, 4, FLFD.fix_alt),

    FLFD("delta Z (m/s)", "<f", 332, 4, FLFD.round3),
    # Unknown region: 336-367. All appear to be valid floating point numbers.
    FLFD("u336", "<f", 336, 4, FLFD.round3),
    FLFD("u340", "<f", 340, 4, FLFD.round3),
    FLFD("u344", "<f", 344, 4, FLFD.round3),
    FLFD("u348", "<f", 348, 4, FLFD.round3),
    FLFD("u352", "<f", 352, 4, FLFD.round3),
    FLFD("u356", "<f", 356, 4, FLFD.round3),
    FLFD("u360", "<f", 360, 4, FLFD.round3),
    FLFD("u364", "<f", 364, 4, FLFD.round3),

    # orientation and velocity (368-395)
    FLFD("bank (deg)", "<f", 368, 4, FLFD.radians_to_degrees),
    FLFD("pitch angle (deg)", "<f", 372, 4, FLFD.radians_to_degrees),
    FLFD("heading (deg)", "<f", 376, 4, FLFD.radian_heading_to_degrees),
    FLFD("u380", "<f", 380,4, FLFD.round3),
    FLFD("u384", "<f", 384,4, FLFD.round3),
    FLFD("u388", "<f", 388,4, FLFD.round3),

    # (392-396) Correlated with the GPS-derived drone speed but not perfectly.
    FLFD("speed (m/s)", "<f", 392,4, FLFD.round3),

    # (396-400) Unknown.
    FLFD("f396", "<f", 396,4),

    # (400-403) Always a constant value of 5050.0. Possibly a format id?
    FLFD("C5050", "<f", 400,4),

    # (404-407) Corrolated with u458 - possibly an estimate of wind speed?
    # Comparison with drone flight videos indicate this could be correct.
    FLFD("Wind Speed (m/s)", "<f", 404, 4, FLFD.round3),

    # (408-411) Wind direction in radians.
    # Comparison of this field with the pitch and roll fields indicate
    # that this is correct.
    FLFD("Wind (deg)", "<f", 408, 4, FLFD.radian_heading_to_degrees),

    # (412-415) Appears to represent the total thrust produced by the drone.
    # No obvious units. (Not sure what units it could be in?) Might be 
    # related to the power going to the motors?
    FLFD("Thrust", "<f", 412, 4, FLFD.round3),

    # (416-417) Ground distance to takeoff point (home) in meters.
    # Need to see what happens to this field when dynamic home is enabled.
    FLFD("distance (m)", "<f", 416, 4, FLFD.round3),

    # (420-427) Location of the takeoff/home point. Need to test if this
    # changes when the home point changes. (dynamic home)
    FLFD("Home Lat (deg)", "<i", 420, 4, FLFD.fix_lat_lon),
    FLFD("Home Lon (deg)", "<i", 424, 4, FLFD.fix_lat_lon),

    # (428) Enumeration of the drone mode. 0 = idle/motors off, 1 = launching,
    # 2 = flying, 3 = landing.
    FLFD("Drone Mode (text)", "<B", 428, 1, FLFD.drone_mode),

    # (429) 1 = RTH. 6 = an AI mode is active.
    FLFD("Auto", "<B", 429, 1),

    # (430) Enumeration of the positioning mode. 1 = ATTI, 2 = OPTI, 3 = GPS.
    FLFD("Positioning Mode (text)", "<B", 430, 1, FLFD.positioning_mode),

    # (431) Claude claims this indicates landing mode substate.
    # 0 = normal operation, 2 = landing imminent, 3 = final descent.
    FLFD("u431", "<B", 431, 1),

    # (432) Claude claims this is a substate for flight mode with 0 = idle,
    # 1-5 indicating phases of take off and flight.
    FLFD("u432", "<B", 432, 1),

    # (433) Enumerated flight mode.
    FLFD("Flight Mode (text)", "<B", 433, 1, FLFD.flight_mode),

    # (434) Always zero?
    FLFD("u434", "<B", 434, 1),

    # (u435) Flags? Enumerated? Varies, but just a few discrete values in each log file.
    FLFD("u435", "<B", 435, 1),

    # Flags or enumerated? Varies, but just a few discrete values in each log file.
    # High nibble is always F. Claude suggests it is a status field corrolated to
    # Drone Mode.
     FLFD("u436", "<B", 436, 1),

    # Flags or enumerated? Varies, but just a few discrete values in each log file.
    FLFD("u437", "<B", 437, 1),

    # (438) Almost always either 4 or 12, but occasionally 36 is seen.
    # 0x00000010, 0x00000110, or 0x00100100
    FLFD("u438", "<B", 438, 1),
    # (439) Almost always zero, in a few flights changed to 128.
    FLFD("u439", "<B", 439, 1),

    # (440-451) Battery related fields.
    FLFD("Battery V1 (mv)", "<h", 440, 2), # Voltage 1
    FLFD("Battery V2 (mv)", "<h", 442, 2), # Voltage 2
    FLFD("Battery Current (ma)", "<h", 444, 2, abs), # Current drain.
    FLFD("Battery Temp (c)", "<B", 446, 1), # Temperature in Celsius.
    FLFD("Battery Level (%)", "<B", 451, 1), # Current battery charge.

    # (452) zero or one of a small range of values between 0x28 and 0x2e
    # Appears to be strongly corrolated with speed, battery current, and flight
    # states: 41 = Idle/Off, 42/43 = launching, 44-46 = flying, returning, landing?
    FLFD("u452", "<B", 452, 1),

    # (453) Always zero?
    FLFD("u453", "<B", 453, 1),

    # (454) Almost always zero. In exactly one flight took a value of 1 part
    # way through.
    FLFD("u454", "<B", 454, 1),

    # (455) Ranges from 0 to 2. Claude indicates a corrolation with battery
    # temperature.
    FLFD("Battery State", "<B", 455, 1),

    FLFD("Drone Mode 2 (text)", "<B", 456, 1, FLFD.drone_mode),
    FLFD("Positioning Mode 2 (text)", "<B", 457, 1, FLFD.positioning_mode),

    # (458-461) Float. across all test flights ranged from 0.00 to 14.99.
    # Median was 4.38, average was 4.11. Possibly an estimate of wind speed.
    FLFD("Wind Speed (m/s)", "<f", 458, 4, FLFD.round3),

    # (462-463) Possibly RC signal quality. I don't see a good corrolation of
    # this and distance though.
    FLFD("RC Signal (%)", "<h", 462, 2),

    # Varies between -1800 and 1800. 
    FLFD("u464", "<h", 464, 2),

    # Unknown.
    FLFD("u466", "<B", 466, 1, FLFD.hex_dump),
    FLFD("u467", "<B", 467, 1, FLFD.hex_dump),

    # (468-469) Occasionally starts as 0x0000 but always ends up 0x5046.
    # Note - 0x5046 == ASCII "PF"
    FLFD("PF", "<H", 468, 2, FLFD.hex_dump2),

    # (470-471) Unknown.
    FLFD("u470", "<b", 470, 1),
    FLFD("u471", "<b", 471, 1),

    # (472) Always 3.
    FLFD("u472", "<b", 472, 1),

    # (473) Unknown, but ranges between 0 and 100.
    FLFD("u473", "<b", 473, 1),

    # (474-480) Possibly the RPM of the motors. Corrolates well with the speed
    # and pitch of the drone (i.e., in forward motion the rear motors have
    # higher rpm) No confirmation that the enumation of these fields
    # corresponds with the Motor State fields.
    #
    # 474, 476 = front motors,
    # 478, 480 = rear motors.
    FLFD("Motor RPM 1", "<H", 474, 2),
    FLFD("Motor RPM 2", "<H", 476, 2),
    FLFD("Motor RPM 3", "<H", 478, 2),
    FLFD("Motor RPM 4", "<H", 480, 2),

    FLFD("u482","<b",482,1),
    FLFD("u483","<b",483,1),
    FLFD("u484","<b",484,1),
    FLFD("u485","<b",485,1),
    FLFD("u486","<b",486,1),
    FLFD("u487","<b",487,1),
    FLFD("u488","<b",488,1),
    FLFD("u489","<b",489,1),
    FLFD("u490","<b",490,1),
    FLFD("u491","<b",491,1),
    FLFD("u492","<b",492,1),
    FLFD("u493","<b",493,1),
    FLFD("u494","<b",494,1),
    FLFD("u495","<b",495,1),
    FLFD("u496","<b",496,1),
    FLFD("u497","<b",497,1),
    FLFD("u498","<b",498,1),
    FLFD("u499","<b",499,1),
    FLFD("u500","<b",500,1),
    FLFD("u501","<b",501,1),
    FLFD("u502","<b",502,1),
    FLFD("u503","<b",503,1),
    FLFD("u504","<b",504,1),
    FLFD("u505","<b",505,1),
    FLFD("u506","<b",506,1),
    FLFD("u507","<b",507,1),
    FLFD("u508","<b",508,1),
    FLFD("u509","<b",509,1),
    FLFD("u510","<b",510,1),
    FLFD("u511","<b",511,1),
]

def atom_parse(file_name, destination=None):
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

        header = [field.name for field in ATOM2_FIELDS]

        writer.writerow(header)

        with open(file_name, mode="rb") as flight_file:
            record_count = 0
            error_count = 0

            transition = False
            transition_count = 0
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

                row = [record.get(field,"") for field in header]
                writer.writerow(row)

                if record.get("Drone Mode (text)") != record.get("Drone Mode 2 (text)"):
                    my_logger.debug("Drone Mode(%s) != Drone Mode 2(%s) in record id %s",
                        record.get("Drone Mode (text)"), record.get("Drone Mode 2 (text)"),
                        record.get("rid")
                    )

                if record.get("Positioning Mode (text)") != record.get("Positioning Mode 2 (text)"):
                    my_logger.debug("Positioning Mode(%s) != Positioning Mode 2(%s) in record id %s",
                        record.get("Positioning Mode (text)"), record.get("Positioning Mode 2 (text)"),
                        record.get("rid")
                    )

#                if not transition and record.get("u464", 0) != 0:
#                    transition = True
#                    my_logger.critical(
#                        "u464 has transitioned. Field = %s, RID = %s, Flight Mode = %s, Positioning Mode = %s, Drone Mode = %s",
#                        record.get("u464"), record.get("rid"), record.get("Flight Mode (text)"),
#                        record.get("Positioning Mode (text)"), record.get("Drone Mode (text)")
#                    )
#                    transition_count += 1
#                elif transition and record.get("u464", -1) == 0:
#                    my_logger.critical(
#                        "u464 has transitioned. Field = %s, rid = %s, Flight Mode = %s, Positioning Mode = %s, Drone Mode = %s",
#                        record.get("u464"), record.get("rid"), record.get("Flight Mode (text)"),
#                        record.get("Positioning Mode (text)"), record.get("Drone Mode (text)")
#                    )
#                    transition = False
#                    transition_count += 1

    my_logger.info(
        "%s valid records and %s invalid record(s) in %s.",
        record_count,
        error_count,
        file_name
    )
    my_logger.info("Report %s complete.", csv_name)

#    my_logger.critical("Transition Count: %s", transition_count)

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
            atom_parse(f, destination=args.destination)
        else:
            my_logger.info("%s appears to be an unsupported file type.", f)
            sys.exit(-1)

if __name__ == '__main__':
    main()
