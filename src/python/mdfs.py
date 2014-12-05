#!/usr/bin/env python
# -*- coding: utf-8 -*-

import fuse

import os
import stat
import errno
import logging
import fnmatch
import types
import json
import re
from core import Stat, TemplateFS

logging.basicConfig(level=logging.ERROR,)
fuse.fuse_python_api = (0, 2)

stringable_types = [str, unicode, int, long, float, bool, types.NoneType]
def default_formatter(directory_name, metadata_dict):
    return directory_name

class InvalidPathException(Exception):
    pass

class MDFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        logging.debug("Preparing to mount file system")

        # formatter for directory names, a function
        if 'formatter' in kwargs:
            self.formatter = kwargs.pop("formatter")
        else:
            self.formatter = default_formatter

        super(MDFS, self).__init__(*args, **kwargs)
        self.parser.add_option(mountopt="sourcedir", help="source dir to scan for conforming metadata files")

    def fsinit(self):
        logging.debug("Nonoption arguments: " + str(self.cmdline[1]))

        # TODO accept function to parse different types
        # patterns per http://docs.python.org/library/fnmatch.html
        md_filename_patterns = ['metadata.json']
        logging.debug("fsinit: looking for files which match: %s" % repr(md_filename_patterns))
        self.metadata_files = set()

        # TODO expand this so we can have multiple sourcedirs
        self.sourcedir = self.cmdline[0].sourcedir
        # walk specified sourcedir to find all metadata files which match md_filename_patterns
        if self.sourcedir is not None:
            logging.debug("sourcedir set to '" + self.sourcedir + "'")
            # patterns can match the same file, so use a set
            for root, dirnames, filenames in os.walk(self.sourcedir):
                for md_filename_pattern in md_filename_patterns:
                    for filename in fnmatch.filter(filenames, md_filename_pattern):
                        self.metadata_files.add(os.path.join(root, filename))
        else:
            logging.debug("sourcedir not set")
        logging.debug("fsinit: metadata files found: %s" % repr(self.metadata_files))

        logging.debug("fsinit: filling metadata cache...")
        """
        metadata cache: { metadata-key : { metadata-value : set(display name) }}
        """
        self.metadata_cache = {}
        self.directory_mapping = {}
        # parse all the found metadata files and build the metadata cache
        if self.metadata_files is not None:
            # parse the files
            for file in self.metadata_files:
                logging.debug("fsinit: parsing file: %s" % file)
                dirname = os.path.dirname(file)
                logging.debug("dirname: %s" % dirname)
                f = open(file, 'r')
                logging.debug("file: %s" % repr(f))
                d = json.load(f)
                logging.debug("d: %s, type: %s" % (d, type(d)))
                if type(d) == dict:
                    formatted_name = self._clean_dir_name(self.formatter(os.path.basename(dirname), d))
                    if formatted_name in self.directory_mapping:
                        formatted_name_conflict = formatted_name 
                        i = 1
                        while formatted_name_conflict in self.directory_mapping:
                            formatted_name_conflict = "%s-%d" % (formatted_name, i)
                            i = i + 1
                        formatted_name = formatted_name_conflict 
                    self.directory_mapping[formatted_name]= dirname
                    self._fill_metadata_cache(d, formatted_name)
                else:
                    logging.error("Found metadata in '" + file + "', but could not parse file into a dict")
        logging.debug("fsinit: metadata cache: %s" % repr(self.metadata_cache))
        logging.debug("Filesystem mounted")

    def _fill_metadata_cache(self, d, dirname, prefix=None):
        logging.debug("in _fill_metadata_cache")
        """
        d = the dict to add to the cache
        dirname = the dirname this dict applies to
        prefix = lookup prefix for nested keys, defaults to None
        """
        logging.debug("fill metadata cache: dirname: %s prefix: %s d: %s" % (dirname, prefix, repr(d)))
        prefix_str = u"%s→%s"
        # add to metadata cache
        for k, v in d.iteritems():
            logging.debug("fill metadata cache: k: %s v: %s" % (repr(k), repr(v)))
            # see http://docs.python.org/library/json.html#json.JSONDecoder
            if type(k) in stringable_types:
                if type(v) in stringable_types:
                    self._add_to_metadata_cache(k if prefix is None else prefix_str % (prefix, k), v, dirname)
                elif type(v) == list:
                    for val in v:
                        if type(val) in stringable_types:
                            self._add_to_metadata_cache(k if prefix is None else prefix_str % (prefix, k), val, dirname)
                        elif type(val) == list:
                            logging.debug("Found a nested list, which makes no sense, ignoring: '" + repr(val) + "'")
                        elif type(val) == dict:
                            self._fill_metadata_cache(val, dirname, k if prefix is None else prefix_str % (prefix, k))
                        else:
                            logging.debug("Found some other type '" + type(val) + "', ignoring: '" + repr(val) + "'")
                elif type(v) in [dict]:
                    self._fill_metadata_cache(v, dirname, k if prefix is None else prefix_str % (prefix, k))
                else:
                    logging.debug("Found key which will not cleanly convert to unicode, ignoring: '" + repr(key) + "'")
            else:
                logging.debug("Found key which will not cleanly convert to unicode, ignoring: '" + repr(key) + "'")

    def _clean_dir_name(self, name):
        logging.debug("_clean_dir_name, name: %s" % name)
        replace_char = "_" if self.facet_prefix != "_" else "-"
        clean_name = self.bad_characters.sub(replace_char, unicode(name))
        if clean_name == ".":
            clean_name = "DOT"
        elif clean_name == "..":
            clean_name = "DOTDOT"
        if clean_name.startswith(self.facet_prefix):
            clean_name = replace_char + clean_name
        logging.debug("_clean_dir_name, cleaned name: %s" % clean_name)
        return clean_name

    bad_characters = re.compile(r'[/\?%*:|"<>]')
    def _add_to_metadata_cache(self, metadata_key, metadata_value, display_name):
        logging.debug("add to metadata cache: : %s v: %s path: %s" % (repr(metadata_key), repr(metadata_value), display_name))
        """
        special characters get stripped here
        """
        key = self._clean_dir_name(metadata_key)
        if key in self.metadata_cache:
            key_dict = self.metadata_cache[key]
        else:
            key_dict = {}
            self.metadata_cache[key] = key_dict

        value = self._clean_dir_name(metadata_value)
        if value in key_dict:
            value_set = key_dict[value]
        else:
            value_set = set()
            key_dict[value] = value_set

        value_set.add(display_name)

    # TODO make configurable
    facet_prefix = "+"
    def _get_path_dict(self, path): 
        """
        gets information from the path
        verifies that the path is valid. raises InvalidPathException otherwise
        """
        logging.debug("in _get_path_dict: %s", path)
        parts = self._split_path(path)
        parts = parts[1:] if len(parts) and parts[0] == '/' else parts
        if not len(parts):
            return {"contents": self._get_facet_filtered([]) + [self.facet_prefix + k for k in self.metadata_cache.keys()]}

        ret = {}
        facets = []
        for index, part in enumerate(parts, 1):
            # check if this position in the path should be a value
            is_facet_value = False
            if len(facets):
                if len(facets[-1]) == 1:
                    is_facet_value = True
                    facet_key = facets[-1][0]
                    if not part in self.metadata_cache[facets[-1][0]]:
                        raise InvalidPathException
                    facets = facets[:-1]
                    facets.append((facet_key, part))
                    if index == len(parts):
                        # fill contents. matching dirs for active facets plus available facets
                        filtered_dirs = self._get_facet_filtered(facets)
                        ret["contents"] = filtered_dirs + [self.facet_prefix + k for k in self._get_available_keys(filtered_dirs)]

            is_facet_key = False
            if not is_facet_value:
                if part.startswith(self.facet_prefix):
                    is_facet_key = True
                    # this is a facet!
                    facet_key_lookup = part[len(self.facet_prefix):]
                    if not facet_key_lookup in self.metadata_cache:
                        raise InvalidPathException
                    if index == len(parts):
                        ret["contents"] = self._get_available_values(facet_key_lookup, facets)
                    else:
                        facets.append((facet_key_lookup,))  # OBS! comma here is to make it a tuple. pay attention!

            if not is_facet_value and not is_facet_key:
                # get all the valid paths based on the currently active facets
                valid = self._get_facet_filtered(facets)
                if not part in valid:
                    raise InvalidPathException
                ret["real_path"] = self.directory_mapping[part]
                #ret["remainder_path"] = os.path.join(parts[index:])
        ret["facets"] = facets
        return ret

    def _get_available_values(self, key, facets):
        directories = self._get_facet_filtered(facets)
        #logging.debug("dirs: %s" % repr(directories))
        values = []
        #metadata cache: { metadata-key : { metadata-value : set(display name) }}
        for value, dirs in self.metadata_cache[key].iteritems():
            for dir in dirs:
                if dir in directories:
                    values.append(value)
                    break
        return values

    def _get_available_keys(self, directories):
        keys = []
        for key, values in self.metadata_cache.iteritems():
            found = False
            for value, dirs in values.iteritems():
                for dir in directories:
                    if dir in dirs:
                        found = True
                        break
                if found:
                    keys.append(key)
                    break
        return keys

    def _get_facet_filtered(self, facets=[]):
        logging.debug("in _get_facet_filtered, facets: %s" % repr(facets))
        """
        filter all the formatted directory names by the active facets
        """
        if len(facets):
            valid = None
            for k, v in facets:
                try:
                    tmp = self.metadata_cache[k][v]
                    valid = tmp if valid is None else valid & tmp
                except KeyError:
                    return []
            if valid is None:
                return []
            return list(valid)
        else:
            ret = list(self.directory_mapping.keys())
            return ret

    def _split_path(self, path):
        logging.debug("in _split_path %s" % path)
        if path == "/":
            return []
        pathparts = []
        if path:
            while True:
                split = os.path.split(path)
                pathparts.append(split[1])
                if not split[0]:
                    break
                elif split[0] == "/":
                    pathparts.append(split[0])
                    break
                path = split[0]
        pathparts.reverse()
        return pathparts

    def getattr(self, path):
        path = path.decode('utf_8')
        logging.debug("getattr: %s" % path)
        try:
            pd = self._get_path_dict(path)
            if "real_path" in pd:
                mode = stat.S_IFLNK | 0777
                return Stat(st_mode=mode, st_size=7)
            else:
                mode = stat.S_IFDIR | 0755
                return Stat(st_mode=mode, st_size=Stat.DIRSIZE, st_nlink=2)
        except InvalidPathException:
            pass
        return -errno.ENOENT

    def access(self, path, flags):
        path = path.decode('utf_8')
        logging.debug("access: %s (flags %s)" % (path, oct(flags)))
        try:
            pd = self._get_path_dict(path)
            if os.W_OK & flags == os.W_OK:
                # wants write permission, fail
                return -errno.EACCES
            return 0
        except InvalidPathException:
            pass
        return -errno.EACCES

    def readlink(self, path):
        # TODO it seems like FUSE-python might be calling this too often... see the logs in debugging mode.
        path = path.decode('utf_8')
        logging.debug("readlink: %s" % path)
        try:
            pd = self._get_path_dict(path)
            if "real_path" in pd:
                return pd["real_path"]
        except InvalidPathException:
            pass
        return -errno.EOPNOTSUPP

    def opendir(self, path):
        logging.debug("opendir: %s" % path)
        path = path.decode('utf_8')
        try:
            pd = self._get_path_dict(path)
            return 0
        except InvalidPathException:
            return -errno.EACCES
        return -errno.EACCES

    def readdir(self, path, offset, dh=None):
        path = path.decode('utf_8')
        dirents = [".", ".."]
        logging.debug("readdir: %s (offset %s, dh %s)" % (path, offset, dh))
        try:
            pd = self._get_path_dict(path)
            for dir in dirents + pd["contents"] if "contents" in pd else dirents:
                yield fuse.Direntry(dir.encode('utf_8', 'replace'))
        except InvalidPathException:
            logging.debug("readdir: invalid path.")

def string_generator(var):
    """
    generates strings for basic types.
    sets/lists/tuples/dicts must contain string-able items.
    non-stringable items are ignored.
    """
    if type(var) in stringable_types:
        yield unicode(var)
    elif type(var) in [list, tuple, set]:
        for x in var:
            if type(x) in stringable_types:
                yield unicode(x)
    elif type(var) == dict:
        for x in var.values():
            if type(x) in stringable_types:
                yield unicode(x)
    else:
        logging.debug("string_generator: wtf found unknown type!")

def formatter_title_dir_year_english_usa(directory_name, metadata_dict):
    english_countries = ["USA", "Canada", "Australia", "UK"]
    md = {"title": None, "director": None, "year": None }
    for key in md:
        md[key] = ", ".join(string_generator(metadata_dict[key])) if key in metadata_dict else None
    if "country" in metadata_dict:
        country = metadata_dict["country"] 
        english_found = False
        if type(country) in stringable_types:
            if unicode(country) in english_countries:
                english_found = True
        else:
            for c in country:
                if unicode(c) in english_countries:
                    english_found = True
        if not english_found:
            if "alternative-title" in metadata_dict:
                alt = metadata_dict["alternative-title"]
                english_alt_found = False
                for a in alt:
                    if type(a) == dict:
                        if "country" in a:
                            c = unicode(a["country"])
                            startswith = ["english"] + english_countries
                            for s in startswith:
                                if c.startswith(s):
                                    if "title" in a:
                                        md["original_title"] = md["title"]
                                        md["title"] = a["title"]
                                        english_alt_found = True
                            if english_alt_found:
                                break
    if md["title"] is None:
        return directory_name
    t = md["title"]
    if "original_title" in md:
        t = t + "(" + md["original_title"] + ")"
    if md["director"] or md["year"]:
        t = t + " ("
    if md["director"]:
        t = t + md["director"]
    if md["director"] and md["year"]:
        t = t + ", "
    if md["year"]:
        t = t + md["year"]
    if md["director"] or md["year"]:
        t = t + ")"
    return t

def main():
    usage = """
    MDFS: A metadata FUSE file system.
    """ + fuse.Fuse.fusage
    server = MDFS(version="%prog " + fuse.__version__, 
            usage=usage, dash_s_do='setsingle', 
            formatter=formatter_title_dir_year_english_usa)
    server.parse(errex=1)
    server.multithreaded = 0
    try:
        server.main()
    except fuse.FuseError, e:
        print str(e)

if __name__ == '__main__':
    main()

logging.debug("File system unmounted")
