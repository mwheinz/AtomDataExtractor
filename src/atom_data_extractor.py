#!python3
'''
Convert information from an Atom-2 flight log into a Telemetry Overlay CSV
'''

import os
import sys
import argparse
import csv
import mwhlogging
from mwhlogging import MWHLogger
from atom2parser import atom2_parser, BASIC_DATA, EXTENDED_DATA, VALIDATION_DATA

my_logger = MWHLogger("csv_extractor")

def write_csv(file_name, records, extended=False, validation=False, destination=None):
    """ Convert a list of parsed records into a CSV file. """
    base_name, _ = os.path.splitext(os.path.basename(file_name))
    directory = (destination if destination is not None else os.path.dirname(file_name))

    csv_name = os.path.join(directory, f"{base_name}.csv")
    my_logger.debug("Creating %s", csv_name)

    with open(csv_name, mode="w", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        header = BASIC_DATA + \
            (EXTENDED_DATA if extended else []) + \
            (VALIDATION_DATA if validation else [])
        writer.writerow(header)

        for record in records:
            row = [record.get(field,"") for field in header]
            writer.writerow(row)
    my_logger.print(f"{csv_name} complete.")

def print_stats(records, extended, validation):
    field_list = BASIC_DATA + \
        (EXTENDED_DATA if extended else []) + \
        (VALIDATION_DATA if validation else [])
    print("Field                                     Min              Max")
    for field_name in field_list:
        field_range = [r[field_name] for r in records if r.get(field_name) != ""]
        if len(field_range) == 0:
            continue
        field_max = max(field_range)
        field_min = min(field_range)
        if not isinstance(field_min, (int,float)):
            continue
        if isinstance(field_min, float):
            field_min = round(field_min,3)
            field_max = round(field_max,3)
        print(f"{field_name:25s}: {field_min:17} {field_max:17}")

def main() -> None:
    """ This is the main program. Duh."""
    arg_parser = argparse.ArgumentParser(
        description="Extract telemetry from Potensic Atom 2 flight logs (.fc2)",
        epilog=(
            "Written by Michael Heinz. Based on work done by Michael Heinz, Koen Aerts,\n"
            "and Rob Pritt. See README.md for detailed field documentation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    arg_parser.add_argument(
        "-D","--destination",
        type=str,
        default=None,
        help="The directory to write the CSV files to. "\
             "Defaults to the directory the telemetry file is in."
    )

    arg_parser.add_argument(
        "-l","--log",
        type=int,
        choices=[0, 1, 2, 3],
        default=2,
        help="Set log level. 0=error, 1=warning, 2=info, 3=debug."
    )

    arg_parser.add_argument(
        "-L","--logfile",
        type=str,
        default=None,
        help="Redirect logging output to a file."
    )

    arg_parser.add_argument(
        "-x","--extended",
        action="store_true",
        help="Include extended fields"
    )

    arg_parser.add_argument(
        "-v","--validation",
        action="store_true",
        help="Calcuate some additional fields to compare against the raw data."
    )

    arg_parser.add_argument(
        "-s", "--stats",
        action="store_true",
        help="Report the min and max for all the basic fields."
    )

    arg_parser.add_argument(
        "files",
        nargs="+",
        help="One or more Atom 2 .fc2 files to convert."
    )

    args = arg_parser.parse_args()

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
            records = atom2_parser(file_name=f, logger=my_logger)
            if records is not None:
                write_csv(f, records,
                          extended=args.extended,
                          validation=args.validation,
                          destination=args.destination)
            if args.stats:
                print_stats(records,
                            extended=args.extended,
                            validation=args.validation)
        else:
            my_logger.info("%s appears to be an unsupported file type.", f)
            sys.exit(-1)

if __name__ == '__main__':
    main()
