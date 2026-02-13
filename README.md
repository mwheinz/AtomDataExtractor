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
| 0     | 4       | integer | Record Id | Yes |
| 4     | 1       | byte | always zero. ||
| 5     | 8       | long long | ms since the drone started(?) | Yes |
| 13    | 2       | short | Starts as zero but occasionally changes to one of a few distinct values. Observed values are 0, 25, 30, 35, 40, 120.||
| 15    | 2       | short | Starts as zero but then may change to a value that will match field #13. ||
| 17 | 2 | ushort | How many times the drone has flown? Can increment in the middle of a flight. Slightly less than what the PTD-1 reports. | |
| 19 | 26 | ??? | Unknown. Values appear to change frequently. | |
| 45 | 1 | byte | GPS Lock. Appears to be 0 when there is no GNSS lock and 3 when there is. |Yes|
| 46 | 1 | byte | # of GNSS satellites the drone has a lock on. | Yes |
| 47 | 4 | integer | drone's latitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 51 | 4 | integer | drone's longitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 55 | 4 | integer | Unknown. Zero when no satellites found. Non-zero when the # of satellites > 0. Can be negative. Varies over time. Could it be signal strength?||
| 59 | 4 | float | Unknown. 0 or 1 when no satellites found. Seems to vary between 0 and 1. ||
| 63 | 4 | float | Unknown. Seems to default to 5, otherwise varies between 0 and 5. ||
| 67 | 4 | float | Unknown. Seems to default to 10, otherwise varies between 0 and 10. 55-67 seem to vary in related, but not identical, patterns.||
| 71 | 8 | ??? | Unknown. Frequently changing hex data.||
| 79 | 2 | ??? | 2 bytes that might be a ushort or might be 2 separate fields. byte 80 seems to usually == 70 or 71. Byte 79 changes more. ||
| 81 | 6 | ??? | Rapidly changing data ||
| 87 | 2 | ??? | Might be another ushort or pair of bytes. ||
| 89 | 2 | ??? | Might be another ushort or pair of bytes. ||
| 91 | 16 | ??? | Unknown. ||
| 107 | 1 | byte | Seems to be a 1 byte flag. ||
| 108 | 3 | byte | Always zero. ||
| 111 | 2 | ??? | 2 bytes of data. ||
| 113 | 2 | ??? | Always zero. ||
| 115 | 2 | ??? | 2 bytes of data. ||
| 144 | 4 | integer | controller's latitude? Doesn't seem correct for Atom 2.||
| 148 | 4 | integer | controller's longitude? Doesn't seem correct for Atom 2.||
| 220 | 4 | integer | "dist 1 lat"? Doesn't seem correct for Atom 2.||
| 224 | 4 | integer | "dist 1 lon"? Doesn't seem correct for Atom 2.||
| 264 | 4 | float? | Supposed to indicate GPS status. <0 no GPS, 0 GPS ready, >2 GPS in use? Doesn't seem right for Atom 2. ||
| 296 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 297 | 1 | byte | Motor State #1 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 298 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 299 | 1 | byte | Motor State #2 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 300 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 301 | 1 | byte | Motor State #3 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 302 | 1 | byte | Seems to be related to motor state. Value = 182 when motor is off. Sometimes varies, sometimes jumps. Probably unsigned?||
| 303 | 1 | byte | Motor State #4 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 304 | 24 | byte | Initially zero, goes non-zero during launch. Goes back to zero when drone has landed. Don't seem to be floats...? ||
| 328 | 4 | float | altitude above ground, in meters. Take the absolute value before using... | Yes |
| 376 | 4 | float | compass heading in radians. | Yes |
| 408 | 4 | float | wind direction in radians. | Yes |
| 412 | 4 | float | Unknown. Initially zero, goes non-zero during launch. Returns to zero during landing. Observed to range between 0 to 24. Varies much more quickly than distance or altitude. ||
| 416 | 4 | float | distance to home, in meters. | Yes |
| 420 | 4 | integer | latitude of the home point in degrees * 1e7. | Yes |
| 424 | 4 | integer | longitude of the home point in degrees * 1e7 | Yes |
| 433 | 1 | byte | Flight mode 7 = video, 8 = normal, 9 = sport | Yes |
| 440 | 2 | short | Battery voltage #1 (mv?) | Yes |
| 442 | 2 | short | Battery voltage #2 (mv?) | Yes |
| 444 | 2 | short | Battery current (ma) | Yes |
| 446 | 1 | byte | Battery Temp (celsius) | Yes |
| 451 | 1 | byte | Battery Level (%) | Yes |
| 456 | 1 | byte | Drone mode 0 = motors off, 1 = idle/launching, 2 = flying, 3 = landing | Yes |
| 457 | 1 | byte | Positioning mode. 3 = GPS, 2 = Optical, 1 = Attitude(?) | 75% sure |
