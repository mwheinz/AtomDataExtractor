# Development notes:

## Building:

The Toga code is just a skeleton and does nothing. There is no packaging
for the CLI tool right now, just run it from the directory.

To try and build the Toga package:

```
$ python3 -m venv venv
$ source venv/bin/activate
$ cd atomdataviewer
$ briefcase build
```

## Briefcase & Toga:
https://beeware.org/

## Telemetry Overlay Documentation:
https://goprotelemetryextractor.com/docs/telemetry-overlay-manual.pdf

## FC2 data file format:
0. koen-aerts, who wrote the potdroneflightparser reverse engineered the
   file formats. He doesn't know what to do with the Atom2's FPV files.
   Says they are "optional".
1. The FC2 file format uses 512 byte records. The first 4 bytes are a record id.
2. The file name is a reasonably accurate time stamp (unlike the names of the video files)

## FC2 Record format:
Fields are all little-endian.
"Correct" indicates that I know for sure that the field is valid.
| Byte: | Length: | Format: | Description: | Correct: |
|-------|---------|---------|--------------|----------|
| 0 | 4 | integer | Record Id | Yes |
| 4 | 1 | byte | always zero. ||
| 5 | 8 | long long | ms since the drone started(?) | Yes |
| 13 | 2 | short | Starts as zero but occasionally changes to one of a few distinct values. Observed values are 0, 25, 30, 35, 40, 120. Initially zero, goes to a non-zero value very early in the log. May occasionally change during flight.||
| 15 | 2 | short | Starts as zero but then may change to a value that will match field 13. ||
| 17 | 2 | ushort | How many times the drone has flown? Increments with each take off. Slightly more than what the PTD-1 reports. | Yes |
| 19 | 26 | ??? | Unknown. Values appear to change frequently. | |
| 45 | 1 | byte | GPS Lock. Appears to be 0 when there is no GNSS lock and 3 when there is. |Yes|
| 46 | 1 | byte | # of GNSS satellites the drone has a lock on. | Yes |
| 47 | 4 | integer | drone's latitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 51 | 4 | integer | drone's longitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 55 | 4 | integer | Seems to represent the GPS signal strength, higher is better. ||
| 59 | 4 | float | 0 or 1 when no satellites found. Possibly represents confidence in the GPS position, with 0.0 the best and 1.0 the worst. ||
| 63 | 4 | float | Possibly related to confidence in the drone's horizontal position, with 5.0 being poor and 0.0 being best. ||
| 67 | 4 | float | Possibly related to confidence in the drone's vertical position, with 10.0 being poor and 0.0 being best. ||
| 71 | 225 | ??? | Unknown. ||
| 296 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 297 | 1 | byte | Motor State #1 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 298 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 299 | 1 | byte | Motor State #2 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 300 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 301 | 1 | byte | Motor State #3 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 302 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 303 | 1 | byte | Motor State #4 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 304 | 4 | float | How far east or west the drone is from the home point in meters. ||
| 308 | 4 | float | How far north or south the drone is from the home point in meters. ||
| 312 | 4 | float | Possibly the drone's pitch? | Unconfirmed |
| 316 | 4 | float | Possibly the drone's roll? | Unconfirmed |
| 320 | 4 | float | Possibly the drone's pitch rate? | Unconfirmed |
| 324 | 4 | float | Possibly the drone's roll rate? | Unconfirmed |
| 328 | 4 | float | Altitude above ground, in meters. Take the absolute value before using... | Yes |
| 332 | 44 | ???? | Unknown. ||
| 376 | 4 | float | Compass heading in radians. | Yes |
| 380 | 4 | float | delta X. Current velocity in the east/west direction. | Unverified |
| 384 | 4 | float | delta Y. Current velocity in the north/south direction. | Unverified |
| 388 | 4 | float | delta Z. Current velocity in the up/down direction. | Unverified |
| 392 | 4 | float | Ground speed? | Unverified | 
| 396 | 4 | float | Unknown. ||
| 400 | 4 | float | Appears to be a constant. ||
| 404 | 4 | float | Air speed? Correlated with altitude? | Unverified |
| 408 | 4 | float | Wind direction in radians. | Yes |
| 412 | 4 | float | Related to total thrust? Goes non-zero during launch, drops to zero when all 4 motors are idle.| Unconfirmed. |
| 416 | 4 | float | Distance to home, in meters. | Yes |
| 420 | 4 | integer | Latitude of the home point in degrees * 1e7. | Yes |
| 424 | 4 | integer | Longitude of the home point in degrees * 1e7 | Yes |
| 428 | 1 | byte | Unknown. ||
| 429 | 1 | byte | Non-zero if Return-to-Home is active. | Yes |
| 430 | 3 | byte | Unknown. ||
| 433 | 1 | byte | Flight mode 7 = video, 8 = normal, 9 = sport | Yes |
| 434 | 6 | byte | Unknown. ||
| 440 | 2 | short | Battery voltage #1 (mv?) | Yes |
| 442 | 2 | short | Battery voltage #2 (mv?) | Yes |
| 444 | 2 | short | Battery current (ma) | Yes |
| 446 | 1 | byte | Battery Temp (celsius) | Yes |
| 451 | 1 | byte | Battery Level (%) | Yes |
| 456 | 1 | byte | Drone mode 0 = motors off, 1 = idle/launching, 2 = flying, 3 = landing | Yes |
| 457 | 1 | byte | Positioning mode. 3 = GPS, 2 = Optical, 1 = Attitude(?) | 75% sure |
