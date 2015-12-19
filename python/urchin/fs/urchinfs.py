#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import sys
import os
import stat
import errno
import logging
import fnmatch
import types
import re
import pprint
import fuse
import imp

import urchin.fs.plugin as plugin
import urchin.fs.default as default
import urchin.fs.mp3 as mp3
import urchin.fs.json as json
import urchin.fs.tmdb as tmdb
from urchin.fs.core import Stat, TemplateFS

"""
urchin-fs TODO

source-dir
-> indexer -> items-to-index
-> matcher -> metadata-sources-for-item
-> extractor -> metadata-collections-for-item
-> merger -> combined-metadata-for-item
-> munger -> munged-metadata-collections-for-item
-> formatter -> names-for-item

"""

#LOG_FILENAME = "LOG"
#logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO,)
logging.basicConfig(level=logging.DEBUG,)
#logging.getLogger().addHandler(logging.StreamHandler())
#logging.basicConfig(level=logging.ERROR,)
fuse.fuse_python_api = (0, 2)

class ConfigurationError(fuse.FuseError):
    pass

class InvalidPathError(Exception):
    pass

# simplistic immutable contract
# like http://stackoverflow.com/a/18092572/320220
class immutable(type):
    def __init__(cls, classname, parents, attributes):
        cls.__original_init__ = cls.__init__
        cls.__original_setattr__ = cls.__setattr__
        cls.__original_delattr__ = cls.__delattr__
        cls.__immutable__ = True

        def init(self, *args, **kwargs):
            object.__setattr__(self, "__immutable__", False)
            self.__original_init__(*args, **kwargs)
            self.__immutable__ = True
        def setattr(self, name, value):
            if self.__immutable__:
                raise TypeError("immutable")
            self.__original_setattr__(name, value)
        def delattr(self, name):
            if self.__immutable__:
                raise TypeError("immutable")
            self.__original_delattr__(name)

        cls.__init__ = init
        cls.__setattr__ = setattr
        cls.__delattr__ = delattr

class Entry(object):
    __metaclass__ = immutable
    def __init__(self, path, metadata_paths, metadata, formatted_names):
        assert type(path) == str
        self.path = path
        assert type(metadata_paths) == set
        self.metadata_paths = metadata_paths
        assert type(metadata) == dict
        self.metadata = metadata
        assert type(formatted_names) == set
        self.formatted_names = formatted_names
        self.results = [Result(name, self.path) for name in self.formatted_names]
    def __hash__(self):
        # FIXME should this take into account the metadata values?
        return hash((self.path,)
               + tuple(self.metadata_paths)
               + tuple(self.formatted_names)
               + tuple(self.metadata.keys()))

class Result(object):
    def __init__(self, name, destination=None):
        self.name = name
        self.destination = destination
        self.mode = (stat.S_IFLNK | 0777) if self.destination else (stat.S_IFDIR | 0755)
        # "The size of a symbolic link is the length of the
        # pathname it contains, without a terminating null byte."
        self.size = len(name) if self.destination else Stat.DIRSIZE

AND = "^"
OR = "+"
CUR = "."
AND_RESULT = Result(AND)
OR_RESULT = Result(OR)
CUR_RESULT = Result(CUR)

class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.plugin_search_paths = ["~/.urchin/plugins/"]
        self.component_types = self.find_component_types()
        self.component_keys = self.component_types.keys()
        self.plugins = self.load_plugins()
        self.plugin_components = self.find_plugin_components()

        super(UrchinFS, self).__init__(*args, **kwargs)
        # -o indexer=json,matcher=json,extractor=json,merger=default,munger=tmdb,formatter=default,source="../test",watch=true
        self.parser.add_option(mountopt="source", help="source directory")
        self.parser.add_option(mountopt="indexer", help="indexer class")
        self.parser.add_option(mountopt="matcher", help="matcher class")
        self.parser.add_option(mountopt="extractor", help="extractor class")
        self.parser.add_option(mountopt="merger", help="merger class")
        self.parser.add_option(mountopt="munger", help="munger class")
        self.parser.add_option(mountopt="formatter", help="formatter class")
        self.parser.add_option(mountopt="plugin", help="plugin class")
        self.parser.add_option(mountopt="watch", help="watch the source directory for changes?")

    #
    # Plugin handling
    #

    def find_component_types(self):
        logging.debug("finding component types...")
        components = dict()
        for (name, cls) in plugin.__dict__.items():
            if isinstance(cls, type) and hasattr(cls, 'component'):
                components[cls.component] = cls
        logging.debug("found component types %s" % components)
        return components

    plugin_main_module = "__init__"
    def load_plugins(self):
        """Load default plugins and plugins found in `plugin_search_paths`"""
        logging.debug("loading plugins...")
        # roughly like https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        plugins = {"mp3": mp3, "default": default, "json": json, "tmdb": tmdb }
        logging.debug("loaded default plugins")
        for plugin_path in self.plugin_search_paths:
            plugin_path = os.path.abspath(os.path.expanduser(plugin_path))
            logging.debug("searching for plugins in %s" % plugin_path)
            if not os.path.exists(plugin_path):
                logging.debug("plugin search path does not exist: %s" % plugin_path)
            else:
                if not os.path.isdir(plugin_path):
                    logging.debug("plugin search path is not a directory: %s" % plugin_path)
                else:
                    for name in os.listdir(plugin_path):
                        path = os.path.join(plugin_path, name)
                        if os.path.isdir(path) and "%s.py" % self.plugin_main_module in os.listdir(path):
                            try:
                                info = imp.find_module("__init__", [path])
                                plugins[name] = imp.load_module(self.plugin_main_module, info[0], info[1], info[2])
                                logging.debug("found plugin module '%s'" % name)
                                info[0].close()
                            except ImportError:
                                logging.warning("plugin module '%s' has no '%s'" % (name, plugin_main_module))
        logging.debug("loaded plugins:\n%s" % pprint.pformat(plugins))
        return plugins

    def find_plugin_components(self):
        """Find all named plugin classes and sort them by the command-line parameter for which they are valid"""
        logging.debug("loading plugin components...")
        # find all named plugin classes
        named = []
        for plugin in self.plugins.values():
            for (name, cls) in plugin.__dict__.items():
                if isinstance(cls, type) and hasattr(cls, "name"):
                    named.append(cls)
        # sort by type
        plugin_components = dict()
        for component_name,component_cls in self.component_types.iteritems():
            plugin_components[component_name] = {cls.name: cls for cls in named if issubclass(cls, component_cls)} # fuck duck typing
        logging.debug("loaded plugin components:\n%s" % pprint.pformat(plugin_components))
        return plugin_components

    # FIXME OMG UGLY
    plugin_class_name = "Plugin"
    def configure_components(self, option_set, config):
        # each "option set" describes the configuration of a specific source directory/way of formatting
        logging.debug("configuring components for option_set %s..." % option_set)
        plugin_config = {k: None for k in self.component_keys}
        if "plugin" in option_set:
            if not option_set["plugin"] in self.plugins:
                raise ConfigurationError("Found no plugin with name '%s'" % option_set["plugin"])
            plugin_module = self.plugins[option_set["plugin"]]
            if not self.plugin_class_name in plugin_module.__dict__:
                raise ConfigurationError("Found plugin module with name '%s', but no class named '%s'" % (option_set["plugin"], self.plugin_class_name))
            plugin_class = plugin_module.__dict__[self.plugin_class_name]
            if not isinstance(plugin_class, type):
                raise ConfigurationError("Found plugin module with name '%s', but '%s' is not a class" % (option_set["plugin"], self.plugin_class_name))
            plugin = plugin_class()
            plugin_config = {
                    "indexer": plugin.indexer,
                    "matcher": plugin.matcher,
                    "extractor": plugin.extractor,
                    "merger": plugin.merger,
                    "munger": plugin.munger,
                    "formatter":  plugin.formatter}
        else:
            plugin_config = {"indexer": None, "matcher": default.DefaultMetadataMatcher, "extractor": None,
                    "merger": default.DefaultMerger, "munger": default.DefaultMunger, "formatter":  default.DefaultFormatter}
            for component_key in self.component_keys:
                if component_key in option_set:
                    plugin_short_name = option_set[component_key]
                    if plugin_short_name in self.plugin_components[component_key]:
                        plugin_config[component_key] = self.plugin_components[component_key][plugin_short_name]
                    else:
                        logging.debug("could not find plugin '%s'" % plugin_short_name)
                        raise ConfigurationError("Could not find specified plugin '%s' for %s component" % (plugin_short_name, component_key))
        # ensure all components are defined
        for k,v in plugin_config.iteritems():
            if not v:
                raise ConfigurationError("No component specified for '%s'" % k)
        logging.debug("using plugin_config:\n%s" % pprint.pformat(plugin_config))
        return {k: cls(config) for k,cls in plugin_config.iteritems()}

    def make_entries(self, components, path):
        entries = []
        indexed = components["indexer"].index(path)
        logging.debug("indexed: %s" % pprint.pformat(indexed))
        for item in indexed:
            sources = components["matcher"].match(item)
            logging.debug("sources: %s" % pprint.pformat(sources))
            raw_metadata = {source: components["extractor"].extract(source) for source in sources}
            logging.debug("raw metadata: %s..." % pprint.pformat(raw_metadata)[:500])
            combined_metadata = components["merger"].merge(raw_metadata)
            logging.debug("combined metadata: %s..." % pprint.pformat(combined_metadata)[:500])
            metadata = components["munger"].mung(combined_metadata)
            logging.debug("munged metadata: %s..." % pprint.pformat(metadata)[:500])
            formatted_names = components["formatter"].format(item, metadata)
            logging.debug("formatted: %s..." % pprint.pformat(formatted_names))
            entries.append(Entry(path, sources, metadata, formatted_names))
        logging.debug("entries: %s" % pprint.pformat(entries))
        return entries

    #
    # init
    #

    def fsinit(self):
        logging.debug("initializing filesystem...")
        try:
            options = self.cmdline[0]
            logging.debug("Option arguments: " + str(options))
            logging.debug("Nonoption arguments: " + str(self.cmdline[1]))

            # FIXME rework this so we don't have to fetch from cmdline
            from_cmdline = {key: getattr(options, key) for key in self.component_keys if hasattr(options, key)}
            from_cmdline["source"] = options.source
            from_cmdline["plugin"] = options.plugin
            option_sets = [from_cmdline]
            logging.debug("from_cmdline: %s" % from_cmdline)

            self.mount_configurations = {}
            for option_set in option_sets:
                config = dict() # FIXME which options should be here?
                components = self.configure_components(option_set, config)
                logging.debug("components: %s" % pprint.pformat(components))
                entries = self.make_entries(components, option_set["source"])
                self.mount_configurations[option_set["source"]] = {"config": config, "components": components, "entries": entries}
            if options.watch:
                pass
                # FIXME add inotify support
                #self.inotify_fd = inotifyx.init()
                # FIXME add watches
                # FIXME decide where to update things
                # FIXME check the system inotify limit and warn if watches exceed
        except Exception, e:
            # FIXME Fatal errors should be resolved before init() (or potentially even main()) is called
            # FIXME so.... perhaps do our own options parsing so we can load all the plugins before we get to here.
            logging.exception("Failed to initialize filesystem.")
            raise e
        logging.debug("initialized filesystem")

    #
    # Lookups
    #

    # FIXME private prefix methods?
    def strip_empty_prefix(self, parts):
        cur = 0
        while parts[cur] == "":
            cur = cur + 1
        if cur > 0:
            parts = parts[cur:]
        return parts

    def split_path(self, path):
        return self.split_path_recursive(os.path.normpath(path))

    def split_path_recursive(self, path):
        """http://stackoverflow.com/a/15050936/320220"""
        a,b = os.path.split(path)
        return (split_path(a) if len(a) and len(b) else []) + [b]

    def get_results(self, path):
        return self._get_results_from_parts(self.strip_empty_prefix(self.split_path(path)))

    def _get_results_from_parts(self, parts):
        if not parts: # root dir
            return [result for result in entry.results for entry in self.entries] + [AND_RESULT, CUR_RESULT]

        # fake enum
        class Parsed:
            KEY, VAL, AND, OR, NONE, DIR = range(1,6)

        class State(object):
            def __init__(self, found):
                self.found = found
                self.last = Parsed.NONE
                self.key = None
                self.valid_values = []
                self.valid_keys = set()
                for entry in self.found:
                    self.valid_keys.update(entry.metadata.keys())
                self.current = dict()
            def AND(self):
                self.last = Parsed.AND
                self.key = None
                self.valid_values = []
            def KEY(self, key):
                self.last = Parsed.KEY
                self.key = key
                self.valid_keys = self.valid_keys - set([key])
                self.current[key] = []
                self.found = self.filter(self.found, self.key)
                self.valid_values = self.values(self.found, self.key)
            def OR(self):
                self.last = Parsed.OR
            def filter(self):
                pass
            def values(self):
                pass
            def get_keys(self):
                pass
            def VAL(self, value):
                self.valid_values = self.valid_values - set([value])
                self.current[self.key] = self.current[self.key] + [value]
                # FIXME
                found = filter....

        state = State(self.entries)
        last_index = len(parts)-1
        for index,part in enumerate(parts):
            is_last = index == last_index

            if part == AND:
                state.AND()
                if is_last:
                    return state.valid_keys + [CUR_RESULT]
            elif state.last == Parsed.AND:
                if part not in state.valid_keys:
                    raise InvalidPathError("invalid key [%s]" % part)
                if part in state.keys:
                    raise InvalidPathError("duplicate key [%s]" % part)
                state.KEY(part)
                if is_last:
                    return state.valid_values + [CUR_RESULT]
            elif state.last == Parsed.VAL and part == OR:
                state.OR()
                if is_last:
                    return state.valid_values + [CUR_RESULT]
            elif state.last == Parsed.KEY or state.last == Parsed.OR:
                if part not in state.valid_values:
                    raise InvalidPathError("invalid value [%s]" % part)

                # FIXME something goes here
                state.VAL(part)

                if is_last:
                    ret = state.listing() + [CUR_RESULT]
                    # add AND and OR if appropriate
                    if len(state.valid_values) > 0:
                        ret = ret + [OR_RESULT]
                    if len(state.valid_keys) > 0:
                        ret = ret + [AND_RESULT]
                    return ret
            else:
                state.DIR()
                if not is_last:
                    raise InvalidPathError("woops")
                if part not in state.valid_values:
                    raise InvalidPathException("invalid value [%s]" % part)
                return state. ... # FIXME

    #
    # Fuse handling
    #

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

def main():
    # FIXME add useful usage description
    usage = """UrchinFS: A faceted-search FUSE file system.""" + fuse.Fuse.fusage
    server = UrchinFS(version="%prog " + fuse.__version__, usage=usage, dash_s_do='setsingle')
    server.parse(errex=1)
    server.multithreaded = 0

    exit_code = 0
    try:
        server.main()
    except fuse.FuseError, e:
        logging.error(str(e))

if __name__ == '__main__':
    main()

logging.debug("File system unmounted")
