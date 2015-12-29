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

from urchin import __version__
import urchin.fs.plugin as plugin
import urchin.fs.default as default
import urchin.fs.mp3 as mp3
import urchin.fs.json as json
import urchin.fs.tmdb as tmdb
from urchin.fs.core import Stat, TemplateFS

# FIXME inotify
# FIXME disambiguation for collisions
# FIXME cleanup for disallowed characters
# FIXME unit tests

logging.basicConfig()
fuse.fuse_python_api = (0, 2)

class ConfigurationError(fuse.FuseError):
    pass

class InvalidPathError(Exception):
    pass

class immutable(type):
    """simplistic immutable contract similar to http://stackoverflow.com/a/18092572/320220"""
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
    """
    An entry in the filesystem.
    `path` is the actual path of the file/directory
    `metadata_paths` are the paths from which `metadata` is derived
    `metadata` is the metadata associated with the entry
    `formatted_names` are the names by which the entry will be displayed
    """
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
    # TODO evaluate if we should make an inverted hash
    #def __hash__(self):
    #    # TODO should this take into account the metadata values?
    #    return hash((self.path,)
    #           + tuple(self.metadata_paths)
    #           + tuple(self.formatted_names)
    #           + tuple(self.metadata.keys()))
    def __repr__(self):
        return "<Entry %s -> %s>" % (self.path, "[%s]" % ",".join(self.formatted_names))

class Result(object):
    """represntation of a directory/symlink"""
    def __init__(self, name, destination=None):
        self.name = name
        self.destination = destination
        self.mode = (stat.S_IFLNK | 0777) if self.destination else (stat.S_IFDIR | 0755)
        # "The size of a symbolic link is the length of the
        # pathname it contains, without a terminating null byte."
        self.size = len(name) if self.destination else Stat.DIRSIZE
    def __repr__(self):
        return "<Result %s>" % (self.name if self.destination is None else "%s -> %s" % (self.name, self.destination))

AND = u"^"
OR = u"+"
CUR = u"."
PARENT= u".."

AND_RESULT = Result(AND)
OR_RESULT = Result(OR)
CUR_RESULT = Result(CUR)
PARENT_RESULT = Result(PARENT)

class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.plugin_search_paths = ["~/.urchin/plugins/"]
        self.component_types = self._find_component_types()
        self.component_keys = self.component_types.keys()
        self.original_working_directory = os.getcwd()

        super(UrchinFS, self).__init__(*args, **kwargs)
        self.parser.add_option(mountopt="config", help="configuration file. if set, other options ignored")
        self.parser.add_option(mountopt="source", help="source directory")
        self.parser.add_option(mountopt="plugin", help="plugin name. if set, component options ignored")
        self.parser.add_option(mountopt="watch", help="watch the source directory for changes?")
        self.parser.add_option(mountopt="log", help="the file to which to log")
        self.parser.add_option(mountopt="loglevel", help="the log level", choices=['debug', 'info', 'warning', 'error', 'critical'])
        for k in self.component_keys:
            self.parser.add_option(mountopt=k, help="%s name" % k)

    #
    # Plugin handling
    #

    def _find_component_types(self):
        logging.debug("finding component types...")
        components = dict()
        for (name, cls) in plugin.__dict__.items():
            if isinstance(cls, type) and hasattr(cls, 'component'):
                components[cls.component] = cls
        logging.debug("found component types %s" % components)
        return components

    _plugin_main_module = "__init__"
    def _load_plugins(self):
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
                        if os.path.isdir(path) and "%s.py" % self._plugin_main_module in os.listdir(path):
                            try:
                                info = imp.find_module("__init__", [path])
                                plugins[name] = imp.load_module(self._plugin_main_module, info[0], info[1], info[2])
                                logging.debug("found plugin module '%s'" % name)
                                info[0].close()
                            except ImportError:
                                logging.warning("plugin module '%s' has no '%s'" % (name, _plugin_main_module))
        logging.debug("loaded plugins:\n%s" % pprint.pformat(plugins))
        return plugins

    def _components_from_modules(self, modules):
        """find all components in modules"""
        # find all named classes
        named = []
        for module in modules:
            for (name, cls) in module.__dict__.items():
                if isinstance(cls, type) and hasattr(cls, "name"):
                    named.append(cls)
        # sort classes by component type
        components = dict()
        for component_name,component_cls in self.component_types.iteritems():
            components[component_name] = {cls.name: cls for cls in named if issubclass(cls, component_cls)} # fuck duck typing
        return components

    def _find_plugin_components(self):
        """Find all named plugin classes and sort them by the command-line parameter for which they are valid"""
        logging.debug("loading plugin components...")
        plugin_components = self._components_from_modules(self.plugins.values())
        logging.debug("loaded plugin components:\n%s" % pprint.pformat(plugin_components))
        return plugin_components

    _plugin_class_name = "Plugin"
    def _configure_components_from_plugin(self, plugin_name):
        """load a set of components from a plugin class given its name"""
        if not plugin_name in self.plugins:
            raise ConfigurationError("Found no plugin with name '%s'" % plugin_name)
        plugin_module = self.plugins[plugin_name]
        if not self._plugin_class_name in plugin_module.__dict__:
            raise ConfigurationError("Found plugin module with name '%s', but no class named '%s'" % (plugin_name, self._plugin_class_name))
        plugin_class = plugin_module.__dict__[self._plugin_class_name]
        if not isinstance(plugin_class, type):
            raise ConfigurationError("Found plugin module with name '%s', but '%s' is not a class" % (plugin_name, self._plugin_class_name))
        plugin = plugin_class()
        return {k: getattr(plugin, k) for k in self.component_keys}

    def _configure_components_from_options(self, option_set):
        """load a set of components by name, using defaults if not specified"""
        # load the classes defined in default
        component_config = {k: None for k in self.component_keys}
        component_config.update({key: v for key,value in self._components_from_modules([default]).items() for k,v in value.items()})
        # override with the classes specified on the command line
        for component_key in self.component_keys:
            if component_key in option_set:
                component_name = option_set[component_key]
                if component_name in self.plugin_components[component_key]:
                    component_config[component_key] = self.plugin_components[component_key][component_name]
                else:
                    logging.debug("could not find plugin '%s'" % component_name)
                    raise ConfigurationError("Could not find specified plugin '%s' for %s component" % (component_name, component_key))
        logging.debug("component configuration from options:\n%s" % pprint.pformat(component_config))
        return component_config

    def _configure_components(self, option_set):
        logging.debug("configuring components for option_set %s..." % option_set)
        if "plugin" in option_set:
            config = self._configure_components_from_plugin(option_set["plugin"])
        else:
            config = self._configure_components_from_options(option_set)
        for k in self.component_keys:
            if k not in config or not config[k]:
                raise ConfigurationError("No component specified for '%s'" % k)
        logging.debug("using component config:\n%s" % pprint.pformat(config))
        return {k: cls(option_set) for k,cls in config.iteritems()}

    def _normalize_path(self, path):
        if not os.path.isabs(path):
            path = os.path.join(self.original_working_directory, path)
        return os.path.normpath(path)

    def _make_entries(self, components, path):
        path = self._normalize_path(path)
        entries = []
        indexed = components["indexer"].index(path)
        logging.debug("indexed path %s gave items: %s" % (path, pprint.pformat(indexed)))
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
            entries.append(Entry(item, sources, metadata, formatted_names))
        logging.debug("entries: %s" % pprint.pformat(entries))
        return entries

    #
    # init
    #

    def fsinit(self):
        logging.debug("initialized filesystem")

    def _load_configurations_from_file(self, path):
        """configuration must be a python file with a variable 'config' which is a list of dicts."""
        path = self._normalize_path(path)
        context = {}
        try:
            execfile(path, context)
        except Exception:
            raise ConfigurationError("Error while attempting to load configuration from %s" % path)
        if "config" not in context:
            raise ConfigurationError("No 'config' variable defined in %s" % path)
        config = context["config"]
        if isinstance(config, dict):
            config = [config]
        if not isinstance(config, list):
            raise ConfigurationError("'config' must be a dict or a list of dicts")
        for d in config:
            if not isinstance(d, dict):
                raise ConfigurationError("'config' must be a dict or a list of dicts")
            if "source" in d:
                if not os.path.isabs(d["source"]):
                    raise ConfigurationError("'source' [%s] must be an absolute path when defined in a config file" % d["source"])
        return config

    def _get_option_sets(self):
        options = self.cmdline[0] # ugh
        if options.config:
            logging.debug("loading configuration from [%s], other options ignored" % options.config)
            return self._load_configurations_from_file(options.config)
        else:
            logging.debug("loading configuration from command line options")
            # extract dict from optparse.Values instance
            return [{k:v for k,v in vars(options).items() if v}]

    _logging_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL
            }
    def _configure_logging(self):
        # it would be nicer to be able to do this pre-init but the option parsing is then a pain
        options = self.cmdline[0]
        log = logging.getLogger()
        if options.log:
            if not os.path.isabs(options.log):
                raise ConfigurationError("log path must be absolute")
            # remove all old handlers and set the new one
            fileh = logging.FileHandler(options.log, 'a')
            for hdlr in log.handlers:
                log.removeHandler(hdlr)
                log.addHandler(fileh)
        if options.loglevel:
            if options.loglevel not in self._logging_map:
                raise ConfigurationError("loglevel must be one of: %s" % ",".join(self._logging_map.keys()))
            log.setLevel(self._logging_map[options.loglevel])

    def configure(self):
        self._configure_logging()
        logging.debug("configuring filesystem...")
        self.plugins = self._load_plugins()
        self.plugin_components = self._find_plugin_components()
        self.mount_configurations = {}
        for option_set in self._get_option_sets():
            components = self._configure_components(option_set)
            logging.debug("components: %s" % pprint.pformat(components))
            entries = self._make_entries(components, option_set["source"])
            self.mount_configurations[option_set["source"]] = {"config": option_set, "components": components, "entries": entries}
            if option_set["watch"]:
                pass
                # FIXME add inotify support
                #self.inotify_fd = inotifyx.init()
                # FIXME add watches
                # FIXME decide where to update things
                # FIXME check the system inotify limit and warn if watches exceed
        self.entries = [entry for configuration in self.mount_configurations.values() for entry in configuration["entries"]]
        logging.debug("configured filesystem")

    #
    # Lookups
    #

    def _strip_empty_prefix(self, parts):
        if len(parts) == 0:
            return parts
        cur = 0
        while cur < len(parts) and parts[cur] == "":
            cur = cur + 1
        if cur > 0:
            parts = parts[cur:]
        return parts

    def _split_path(self, path):
        return self._split_path_recursive(os.path.normpath(path))

    def _split_path_recursive(self, path):
        """http://stackoverflow.com/a/15050936/320220"""
        a,b = os.path.split(path)
        return (self._split_path(a) if len(a) and len(b) else []) + [b]

    def _get_results(self, path):
        return self._get_results_from_parts(self._strip_empty_prefix(self._split_path(path)))

    def _get_results_from_parts(self, parts):
        logging.debug("get_results_from_parts: %s" % parts)
        if not parts: # root dir
            return [result for entry in self.entries for result in entry.results] + [AND_RESULT, CUR_RESULT, PARENT_RESULT]

        # fake enum
        class Parsed:
            KEY, VAL, AND, OR, NONE, DIR = range(1,7)

        found = self.entries
        current_valid_keys = set([key for entry in found for key in entry.metadata.keys()])
        current_valid_values = set()
        current_key = None
        state = dict()

        last = Parsed.NONE
        last_index = len(parts)-1

        for index,part in enumerate(parts):
            is_last = index == last_index

            if part == AND:
                last = Parsed.AND
                current_key = None
                current_valid_values = set()
                current_valid_keys = set([key for key in entry.metadata.keys() for entry in found]) - set(state.keys())
                if is_last:
                    return [Result(key) for key in current_valid_keys] + [CUR_RESULT, PARENT_RESULT]
            elif last == Parsed.AND:
                last = Parsed.KEY
                if part not in current_valid_keys:
                    raise InvalidPathError("invalid key [%s]" % part)
                if part in state:
                    raise InvalidPathError("duplicate key [%s]" % part)
                current_key = part
                current_valid_keys = current_valid_keys - set([current_key])
                state[current_key] = set()
                current_valid_values = set([v for f in found for k,values in f.metadata.iteritems() for v in values if k == current_key])
                if is_last:
                    return [Result(value) for value in current_valid_values] + [CUR_RESULT, PARENT_RESULT]
            elif last == Parsed.VAL and part == OR:
                last = Parsed.OR
                if is_last:
                    return [Result(value) for value in current_valid_values] + [CUR_RESULT, PARENT_RESULT]
            elif last == Parsed.KEY or last == Parsed.OR:
                last = Parsed.VAL
                if part not in current_valid_values:
                    logging.debug("current_valid_values: %s" % ','.join(current_valid_values))
                    raise InvalidPathError("invalid value [%s]" % part)
                current_valid_values = current_valid_values - set([part])
                state[current_key].update([part])
                # lookahead, and if the next token is _not_ an OR,
                # filter the entries by the current facet
                if is_last or (not is_last and parts[index+1] != OR):
                    newfound = []
                    logging.debug("finding %s -> %s" % (current_key, state[current_key]))
                    for e in found:
                        keep = False
                        logging.debug("\ttesting %s" % e.path)
                        if current_key in e.metadata:
                            logging.debug("\t\tkey %s exists" % current_key)
                            for v in state[current_key]:
                                if v in e.metadata[current_key]:
                                    logging.debug("\t\tvalue %s exists" % v)
                                    keep = True
                        if keep:
                            newfound.append(e)
                    found = newfound
                if is_last:
                    ret = [r for f in found for r in f.results] + [CUR_RESULT, PARENT_RESULT]
                    # add AND and OR if appropriate
                    if len(current_valid_values) > 0:
                        ret = ret + [OR_RESULT]
                    if len(current_valid_keys) > 0:
                        ret = ret + [AND_RESULT]
                    return ret
            else:
                last = Parsed.DIR
                # a "normal directory", i.e. something somewhere else on disk
                # if this isn't the last component in the path, error out
                if not is_last:
                    raise InvalidPathError("woops")
                for f in found:
                    for r in f.results:
                        if r.name == part:
                            return [Result(CUR, r.destination)]
                raise InvalidPathError("invalid dir name [%s]" % part)

    #
    # Fuse handling
    #

    def getattr(self, path):
        path = path.decode('utf_8')
        logging.debug("getattr: %s" % path)
        try:
            results = self._get_results(path)
            logging.debug("\t%s" % results)
            for r in results:
                if r.name == CUR:
                    result_stat = Stat(st_mode = r.mode, st_size = r.size)
                    logging.debug("\t%s" % result_stat)
                    return result_stat
        except InvalidPathError,e:
            pass
        return -errno.ENOENT

    def access(self, path, flags):
        path = path.decode('utf_8')
        logging.debug("access: %s (flags %s)" % (path, oct(flags)))
        try:
            results = self._get_results(path)
            logging.debug("\t%s" % results)
            if os.W_OK & flags == os.W_OK:
                # wants write permission, fail
                return -errno.EACCES
            return 0
        except InvalidPathError:
            pass
        return -errno.ENOENT

    def opendir(self, path):
        path = path.decode('utf_8')
        logging.debug("opendir: %s" % path)
        try:
            results = self._get_results(path)
            logging.debug("\t%s" % results)
            return None
        except InvalidPathError:
            pass
        return -errno.ENOENT

    def readdir(self, path, offset, dh=None):
        path = path.decode('utf_8')
        logging.debug("readdir: %s (offset %s, dh %s)" % (path, offset, dh))
        try:
            results = self._get_results(path)
            logging.debug("\t%s" % results)
            for result in results:
                logging.debug("\tyeilding %s" % result)
                yield fuse.Direntry(result.name.encode('utf_8', 'replace'))
        except InvalidPathError:
            logging.debug("readdir: invalid path %s" % path)

    def readlink(self, path):
        # TODO it seems like FUSE-python might be calling this too often... see the logs in debugging mode.
        path = path.decode('utf_8')
        logging.debug("readlink: %s" % path)
        try:
            results = self._get_results(path)
            logging.debug("\t%s" % results)
            for r in results:
                if r.name == CUR:
                    return r.destination
        except InvalidPathError:
            pass
        return -errno.ENOENT

def main():
    server = UrchinFS(version="%prog " + __version__, dash_s_do='setsingle')
    args = server.parse(errex=1)
    server.multithreaded = 0
    try:
        server.configure()
    except ConfigurationError, e:
        logging.error("Failed to configure filesystem, exiting. Cause:\n\t%s" % e.message)
        sys.exit(1)
    try:
        server.main()
    except fuse.FuseError, e:
        logging.error("Error during filesystem operation. Cause:\n\t%s" % e.message)

if __name__ == '__main__':
    main()
