"""
Reads a JSON file in the right format, compares it with the current
state of the Tango DB, and generates the set of DB API commands needed
to get to the state described by the file. These commands can also
optionally be run.
"""

import sys
import time
import json
from optparse import OptionParser
from tempfile import NamedTemporaryFile

import PyTango
from dsconfig.configure import configure
from dsconfig.diff import print_diff
from dsconfig.filtering import filter_config
from dsconfig.formatting import (CLASSES_LEVELS, SERVERS_LEVELS, load_json,
                                 normalize_config, validate_json,
                                 clean_metadata)
from dsconfig.tangodb import get_dict_from_db, summarise_calls
from dsconfig.utils import green, red, yellow, progressbar


def main():

    usage = "Usage: %prog [options] JSONFILE"
    parser = OptionParser(usage=usage)

    parser.add_option("-w", "--write", dest="write", action="store_true",
                      help="write to the Tango DB", metavar="WRITE")
    parser.add_option("-u", "--update", dest="update", action="store_true",
                      help="don't remove things, only add/update",
                      metavar="UPDATE")
    parser.add_option("-q", "--quiet",
                      action="store_false", dest="verbose", default=True,
                      help="don't print actions to stderr")
    parser.add_option("-o", "--output", dest="output", action="store_true",
                      help="Output the relevant DB state as JSON.")
    parser.add_option("-p", "--input", dest="input", action="store_true",
                      help="Output the input JSON (after filtering).")
    parser.add_option("-d", "--dbcalls", dest="dbcalls", action="store_true",
                      help="print out all db calls.")
    parser.add_option("-v", "--no-validation", dest="validate", default=True,
                      action="store_false", help=("Skip JSON validation"))
    parser.add_option("-s", "--sleep", dest="sleep", default=0.01,
                      type="float",
                      help=("Number of seconds to sleep between DB calls"))

    parser.add_option("-i", "--include", dest="include", action="append",
                      help=("Inclusive filter on server configutation"))
    parser.add_option("-x", "--exclude", dest="exclude", action="append",
                      help=("Exclusive filter on server configutation"))
    parser.add_option("-I", "--include-classes", dest="include_classes",
                      action="append",
                      help=("Inclusive filter on class configuration"))
    parser.add_option("-X", "--exclude-classes", dest="exclude_classes",
                      action="append",
                      help=("Exclusive filter on class configuration"))

    parser.add_option(
        "-D", "--dbdata",
        help="Read the given file as DB data instead of using the actual DB",
        dest="dbdata")

    options, args = parser.parse_args()

    if len(args) == 0:
        data = load_json(sys.stdin)
    else:
        json_file = args[0]
        with open(json_file) as f:
            data = load_json(f)

    # Normalization - making the config conform to standard
    data = normalize_config(data)

    # remove any metadata at the top level (should we use this for something?)
    data = clean_metadata(data)

    # Optional validation of the JSON file format.
    if options.validate:
        validate_json(data)

    # filtering
    try:
        if options.include:
            data["servers"] = filter_config(
                data["servers"], options.include, SERVERS_LEVELS)
        if options.exclude:
            data["servers"] = filter_config(
                data["servers"], options.exclude, SERVERS_LEVELS, invert=True)
        if options.include_classes:
            data["classes"] = filter_config(
                data["classes"], options.include_classes, CLASSES_LEVELS)
        if options.exclude_classes:
            data["classes"] = filter_config(
                data["classes"], options.exclude_classes, CLASSES_LEVELS,
                invert=True)
    except ValueError as e:
        sys.exit("Filter error:\n%s" % e)

    if not any(k in data for k in ("devices", "servers", "classes")):
        sys.exit("No config data; exiting!")

    # check if there is anything in the DB that will be changed or removed
    db = PyTango.Database()
    if options.dbdata:
        with open(options.dbdata) as f:
            original = json.loads(f.read())
        collisions = {}
    else:
        original, collisions = get_dict_from_db(db, data)

    # Print out a nice diff
    if options.verbose:
        print_diff(original, data, removes=not options.update)

    # get the list of DB calls needed
    dbcalls = configure(data, original, options.update)

    # perform the db operations (if we're supposed to)
    if options.write and dbcalls:
        for i, (method, args, kwargs) in enumerate(dbcalls):
            if options.sleep:
                time.sleep(options.sleep)
            if options.verbose:
                progressbar(i, len(dbcalls), 20)
            getattr(db, method)(*args, **kwargs)

    # optionally dump some information to stdout
    if options.output:
        print json.dumps(original, indent=4)
    elif options.input:
        print json.dumps(data, indent=4)
    if options.dbcalls:
        print >>sys.stderr, "Tango database calls:"
        for method, args, kwargs in dbcalls:
            print method, args

    # Check for moved devices and remove empty servers
    empty = set()
    for srvname, devs in collisions.items():
        if options.verbose:
            srv, inst = srvname.split("/")
            for cls, dev in devs:
                print >>sys.stderr, red("MOVED (because of collision):")
                print >>sys.stderr, red(" > servers > %s > %s > %s > %s"
                                        % (srv, inst, cls, dev))
        if len(db.get_device_class_list(srvname)) == 2:  # just dserver
            empty.add(srvname)
            if options.write:
                db.delete_server(srvname)

    # finally print out a brief summary of what was done
    if dbcalls:
        print
        print "\n".join(summarise_calls(dbcalls, original))
        if collisions:
            servers = len(collisions)
            devices = sum(len(devs) for devs in collisions.values())
            print >>sys.stderr, red("Move %d devices from %d servers." %
                                    (devices, servers))
        if empty and options.verbose:
            print >>sys.stderr, red("Removed %d empty servers." % len(empty))

        if options.write:
            print >>sys.stderr, red("\n*** Data was written to the Tango DB ***")
            with NamedTemporaryFile(prefix="dsconfig-", suffix=".json",
                                    delete=False) as f:
                f.write(json.dumps(original, indent=4))
                print >>sys.stderr, ("The previous DB data was saved to %s" %
                                     f.name)
        else:
            print >>sys.stderr, yellow(
                "\n*** Nothing was written to the Tango DB (use -w) ***")
    else:
        print >>sys.stderr, green("\n*** No changes needed in Tango DB ***")


if __name__ == "__main__":
    main()