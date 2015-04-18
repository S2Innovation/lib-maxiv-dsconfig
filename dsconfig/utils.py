from functools import partial

import PyTango

from appending_dict import AppendingDict

#colors
ADD = GREEN = '\033[92m'
REMOVE = RED = FAIL = '\033[91m'
REPLACE = YELLOW = WARN = '\033[93m'
ENDC = '\033[0m'

def green(text):
    return GREEN + text + ENDC

def red(text):
    return RED + text + ENDC

def yellow(text):
    return YELLOW + text + ENDC


# functions to decode unicode JSON (PyTango does not like unicode strings)

def decode_list(data):
    rv = []
    for item in data:
        if isinstance(item, unicode):
            item = str(item.encode('utf-8'))
        elif isinstance(item, list):
            item = decode_list(item)
        elif isinstance(item, dict):
            item = decode_dict(item)
        rv.append(item)
    return rv


def decode_dict(data):
    rv = {}
    for key, value in data.iteritems():
        if isinstance(key, unicode):
            key = str(key.encode('utf-8'))
        if isinstance(value, unicode):
            value = str(value.encode('utf-8'))
        elif isinstance(value, list):
            value = decode_list(value)
        elif isinstance(value, dict):
            value = decode_dict(value)
        rv[key] = value
    return rv


def find_device(definitions, devname):
    "Find a given device in a server dict"
    for instname, inst in definitions["servers"].items():
        for classname, cls in inst.items():
            if devname in cls:
                return cls[devname], (instname, classname, devname)
    raise ValueError("device '%s' not defined" % devname)


def find_class(definitions, clsname):
    "Find a given device in a server dict"
    for instname, inst in definitions["servers"].items():
        if clsname in inst:
            return inst[clsname]
    raise ValueError("class '%s' not defined" % clsname)


def decode_pointer(ptr):
    """Take a string representing a JSON pointer and return a
    sequence of parts, decoded."""
    return [p.replace("~1", "/").replace("~0", "~")
            for p in ptr.split("/")]


def get_devices_from_dict(dbdict):
    return [(server_name, class_name, device_name)
            for server_name, server in dbdict.items()
            for class_name, clss in server.items()
            for device_name in clss]


# These are special properties that we'll ignore for now
PROTECTED_PROPERTIES = [
    "polled_attr", "logging_level", "logging_target"
]


SPECIAL_ATTRIBUTE_PROPERTIES = ["label", "format", "unit",
                                "min_value", "min_alarm", "min_warning",
                                "max_value", "min_alarm", "min_warning",
                                "abs_change", "rel_change", "event_period",
                                "archive_abs_change", "archive_rel_change",
                                "archive_period",
                                "description", "mode"]


def is_protected(prop, attr=False):
    """Ignore all properties starting with underscore (typically Tango
    created) and some special ones"""
    if attr:
        # Consider attribute config to be protected. This means we do
        # not remove them, but we do overwrite if included in the config.
        return prop.startswith("_") or prop in SPECIAL_ATTRIBUTE_PROPERTIES
    else:
        return prop.startswith("_") or prop in PROTECTED_PROPERTIES


def get_dict_from_db(db, data):

    """Takes a data dict, checks if any if the definitions are already
    in the DB and returns a dict describing them."""

    # This is where we'll collect all the relevant data
    dbdict = AppendingDict()
    moved_devices = []

    # Devices that are already defined somewhere else
    for server, clss, device in get_devices_from_dict(data["servers"]):
        try:
            devinfo = db.get_device_info(device)
            if devinfo.ds_full_name != server:
                moved_devices.append((devinfo.name, devinfo.class_name,
                                      devinfo.ds_full_name))
        except PyTango.DevFailed:
            pass

    # Servers
    for server_name, srvr in data.get("servers", {}).items():

        for class_name, cls in srvr.items():
            devices = db.get_device_name(server_name, class_name)

            for device_name in devices:
                name = device_name

                db_props = db.get_device_property_list(name, "*")
                dev = dbdict.servers[server_name][class_name][device_name]

                # Properties
                for prop in db_props:
                    if not is_protected(prop):
                        value = db.get_device_property(name, prop)[prop]
                        value = [str(v) for v in value]  # is this safe?
                        dev.properties[prop] = value

                # Attribute properties
                # Seems impossible to get the full list of defined attribute
                # properties through the API so we'll have to make do with
                # the attributes we know about.
                attr_props = cls.get(device_name, {}).get("attribute_properties")
                if attr_props:
                    dbprops = db.get_device_attribute_property(device_name,
                                                               attr_props.keys())
                    for attr, props in dbprops.items():
                        props = dict((prop, [str(v) for v in values])
                                     for prop, values in props.items())  # whew!
                        dev.attribute_properties[attr] = props

    # Classes
    for class_name, cls in data.get("classes", {}).items():

        for prop in cls.get("properties", ()):
            if not is_protected(prop):
                db_prop = db.get_class_property(class_name, prop)[prop]
                if db_prop:
                    value = [str(v) for v in db_prop]
                    dbdict.classes[class_name].properties[prop] = value

        attr_props = cls.get("attribute_properties")
        if attr_props:
            dbprops = db.get_class_attribute_property(class_name,
                                                      attr_props.keys())
            for attr, props in dbprops.items():
                props = dict((prop, [str(v) for v in values])
                             for prop, values in props.items())
                dbdict.classes[class_name].attribute_properties[attr] = props

    return dbdict.to_dict(), moved_devices


class ObjectWrapper(object):

    """An object that allows all method calls and records them,
    then passes them on to a target object (if any)."""

    def __init__(self, target=None):
        self.target = target
        self.calls = []

    def __getattr__(self, attr):

        def method(attr, *args, **kwargs):
            self.calls.append((attr, args, kwargs))
            if self.target:
                getattr(self.target, attr)(*args, **kwargs)

        return partial(method, attr)


# From http://code.activestate.com/recipes/66315/#c8

#  27-05-04
# v2.0.2
#

# caseless
# Featuring :

# caselessDict
# A case insensitive dictionary that only permits strings as keys.

# Implemented for ConfigObj
# Requires Python 2.2 or above

# Copyright Michael Foord
# Not for use in commercial projects without permission. (Although permission will probably be given).
# If you use in a non-commercial project then please credit me and include a link back.
# If you release the project non-commercially then let me know (and include this message with my code !)

# No warranty express or implied for the accuracy, fitness to purpose or otherwise for this code....
# Use at your own risk !!!

# E-mail fuzzyman AT atlantibots DOT org DOT uk (or michael AT foord DOT me DOT uk )
# Maintained at www.voidspace.org.uk/atlantibots/pythonutils.html


class CaselessDict(dict):
    """A case insensitive dictionary that only permits strings as keys."""
    def __init__(self, indict={}):
        dict.__init__(self)
        self._keydict = {}                      # not self.__keydict because I want it to be easily accessible by subclasses
        for entry in indict:
            self[entry] = indict[entry]         # not dict.__setitem__(self, entry, indict[entry]) becasue this causes errors (phantom entries) where indict has overlapping keys...

    def findkey(self, item):
        """A caseless way of checking if a key exists or not.
        It returns None or the correct key."""
        if not isinstance(item, str): raise TypeError('Keywords for this object must be strings. You supplied %s' % type(item))
        key = item.lower()
        try:
            return self._keydict[key]
        except:
            return None

    def changekey(self, item):
        """For changing the casing of a key.
        If a key exists that is a caseless match for 'item' it will be changed to 'item'.
        This is useful when initially setting up default keys - but later might want to preserve an alternative casing.
        (e.g. if later read from a config file - and you might want to write back out with the user's casing preserved).
        """
        key = self.findkey(item)           # does the key exist
        if key == None: raise KeyError(item)
        temp = self[key]
        del self[key]
        self[item] = temp
        self._keydict[item.lower()] = item

    def lowerkeys(self):
        """Returns a lowercase list of all member keywords."""
        return self._keydict.keys()

    def __setitem__(self, item, value):             # setting a keyword
        """To implement lowercase keys."""
        key = self.findkey(item)           # if the key already exists
        if key != None:
            dict.__delitem__(self,key)
        self._keydict[item.lower()] = item
        dict.__setitem__(self, item, value)

    def __getitem__(self, item):
        """To implement lowercase keys."""
        key = self.findkey(item)           # does the key exist
        if key == None: raise KeyError(item)
        return dict.__getitem__(self, key)

    def __delitem__(self, item):                # deleting a keyword
        key = self.findkey(item)           # does the key exist
        if key == None: raise KeyError(item)
        dict.__delitem__(self, key)
        del self._keydict[item.lower()]

    def pop(self, item, default=None):
        """Correctly emulates the pop method."""
        key = self.findkey(item)           # does the key exist
        if key == None:
            if default == None:
                raise KeyError(item)
            else:
                return default
        del self._keydict[item.lower()]
        return dict.pop(self, key)

    def popitem(self):
        """Correctly emulates the popitem method."""
        popped = dict.popitem(self)
        del self._keydict[popped[0].lower()]
        return popped

    def has_key(self, item):
        """A case insensitive test for keys."""
        if not isinstance(item, str): return False               # should never have a non-string key
        return self._keydict.has_key(item.lower())           # does the key exist

    def __contains__(self, item):
        """A case insensitive __contains__."""
        if not isinstance(item, str): return False               # should never have a non-string key
        return self._keydict.has_key(item.lower())           # does the key exist

    def setdefault(self, item, default=None):
        """A case insensitive setdefault.
        If no default is supplied it sets the item to None"""
        key = self.findkey(item)           # does the key exist
        if key != None: return self[key]
        self.__setitem__(item, default)
        self._keydict[item.lower()] = item
        return default

    def get(self, item, default=None):
        """A case insensitive get."""
        key = self.findkey(item)           # does the key exist
        if key != None: return self[key]
        return default

    def update(self, indict):
        """A case insensitive update.
        If your dictionary has overlapping keys (e.g. 'FISH' and 'fish') then one will overwrite the other.
        The one that is kept is arbitrary."""
        for entry in indict:
            self[entry] = indict[entry]         # this uses the new __setitem__ method

    def copy(self):
        """Create a new caselessDict object that is a copy of this one."""
        return CaselessDict(self)

    def dict(self):
        """Create a dictionary version of this caselessDict."""
        return dict.copy(self)

    def clear(self):
        """Clear this caselessDict."""
        self._keydict = {}
        dict.clear(self)

    def __repr__(self):
        """A caselessDict version of __repr__ """
        return 'caselessDict(' + dict.__repr__(self) + ')'


"""A tuctionary, or tuct, is the combination of a tuple with
a dictionary. A tuct has named items, but they cannot be
deleted or rebound, nor new can be added.
"""

class ImmutableDict(object):
    """The tuct class. An immutable dictionary.
    """

    def __init__(self, dict=None, **kwds):
            self.__data = {}
            if dict is not None:
                    self.__data.update(dict)
            if len(kwds):
                    self.__data.update(kwds)

    #del __init__

    def __repr__(self):
            return repr(self.__data)

    def __cmp__(self, dict):
            if isinstance(dict, ImmutableDict):
                    return cmp(self.__data, dict.__data)
            else:
                    return cmp(self.__data, dict)

    def __len__(self):
            return len(self.__data)

    def __getitem__(self, key):
            return self.__data[key]

    def copy(self):
            if self.__class__ is ImmutableDict:
                    return ImmutableDict(self.__data.copy())
            import copy
            __data = self.__data


def filter_nested_dict(node, pattern, depth, level=0, invert=False):
    """
    Filter the parts of a nested dict where keys match regex pattern,
    at the given depth.
    """
    if level == depth:
        return dict((key, value) for key, value in node.iteritems()
                    if (not invert and pattern.search(key)) or
                    (invert and not pattern.search(key)))
    else:
        dupe_node = {}
        for key, val in node.iteritems():
            cur_node = filter_nested_dict(val, pattern, depth, level+1,
                                          invert)
            if cur_node:
                dupe_node[key] = cur_node
        return dupe_node or None
