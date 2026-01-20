# Development notes:

## Telemetry Overlay Documentation:
https://goprotelemetryextractor.com/docs/telemetry-overlay-manual.pdf

## Atom2 data file format:
0. koen-aerts, who wrote the potdroneflightparser reverse engineered the
   file formats. He doesn't know what to do with the Atom2's FPV files.
   Says they are "optional".
1. The FC2 file format uses 512 byte records. The first 4 bytes are a record id.

TODO: Document the rest of the record format here.

TODO: Learn how to package a python app.

TODO: Turn this thing into something someone without developer experience can
use.
