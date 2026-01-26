# Development notes:

TODO: Document the rest of the record format here.

TODO: Learn how to package a python app.

TODO: Turn this thing into something someone without developer experience can
use.

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
| 5     | 8       | long long | ms since the drone started(?) | Yes |
| 13    | 2       | short | S1. Starts as zero but then may change to a value that seems to stay constant for the rest of the log. Values include 0x1e, 0x78. If non-zero it will match S2. | |
| 15    | 2       | short | S2. Starts as zero but then may change to a value that seems to stay constant for the rest of the log. Values include 0x1e, 0x78. If S1 is non-zero it will match this value. | |
| 17 | 2 | ushort | How many times the drone has flown? Can increment in the middle of a flight. | |
| 19 | 26 | ??? | Unknown. Values appear to change frequently. | |
| 45 | 1 | byte | Unknown. Appears to be 0 when there is no GNSS lock and 3 when there is. | |
| 46 | 1 | byte | # of GNSS satellites the drone has a lock on. | Yes |
| 47 | 4 | integer | drone's latitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 51 | 4 | integer | drone's longitude in ten-millionths of degrees. 0 if unknown. | Yes |
| 55 | 8 | ??? | Unknown. During a static engines-off test, remained a constant 0x803f, frequently changes during flight. | |
| 63 | 8 | ??? | Unknown. During a static engines-off test, remained a constant 0xa04000002041, frequently changes during flight. | |
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
| 297 | 1 | byte | Motor State #1 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 299 | 1 | byte | Motor State #2 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 301 | 1 | byte | Motor State #3 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 303 | 1 | byte | Motor State #4 3 = off, 4 = idle, 5 = low, 6 = medium, 7 = high | Yes |
| 328 | 4 | float | altitude in meters. | Yes |
| 376 | 4 | float | compass heading in radians. | Yes |
| 416 | 4 | float | distance to home, in meters. | Yes |
| 420 | 4 | integer | latitude of the home point in degrees * 1e7. | Yes |
| 424 | 4 | integer | longitude of the home point in degrees * 1e7 | Yes |
| 433 | 1 | byte | Flight mode 7 = video, 8 = normal, 9 = sport | Yes |
| 440 | 2 | short | Battery voltage #1 (mv?) | Yes |
| 442 | 2 | short | Battery voltage #2 (mv?) | Yes |
| 444 | 2 | short | Battery current (ma) | Yes |
| 446 | 1 | byte | Battery Temp (c) | Yes |
| 451 | 1 | byte | Battery Level (%) | Yes |
| 456 | 1 | byte | Drone mode 0 = motors off, 1 = idle/launching, 2 = flying, 3 = landing | Yes |
| 457 | 1 | byte | Positioning mode. 3 = GPS, 2 = Optical, 1 = Attitude(?) | 75% sure |
