"""
Command line utlity for Python QuickRoute
"""
from quickroute.reader import QuickRouteData
from quickroute.utils import DateTimeEncoder
import argparse
import logging
import sys
import json


def main(argv=None):
    """ Command line  entry point """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--format", choices=["json", "gpx"], default="json",
                        help="Output format (default %(default)r)")
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING"], default="INFO")
    parser.add_argument("file")
    args = parser.parse_args()

    log_lvl = logging.getLevelName(args.log_level)
    log_fmt = "%(message)s"
    logging.basicConfig(level=log_lvl, format=log_fmt)

    qrt = QuickRouteData(jpeg=args.file)
    if args.format == "json":
        print json.dumps(qrt, sort_keys=True, indent=2, cls=DateTimeEncoder)
    elif args.format == "gpx":
        # soon...
        print "gpx output not supported yet"


if __name__ == "__main__":
    main()
