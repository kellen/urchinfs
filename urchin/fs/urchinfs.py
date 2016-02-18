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
import time
import functools
import uuid
import sqlite3

from urchin import __version__
import urchin.fs.plugin as plugin
import urchin.fs.default as default
import urchin.fs.mp3 as mp3
import urchin.fs.mp3file as mp3file
import urchin.fs.json as json
import urchin.fs.tmdb as tmdb
from urchin.fs.core import Stat, TemplateFS

# FIXME unit tests

logging.basicConfig()
fuse.fuse_python_api = (0, 2)

def cache(obj):
    """modified https://wiki.python.org/moin/PythonDecoratorLibrary#Alternate_memoize_as_nested_functions"""
    @functools.wraps(obj)
    def cacher(self, *args, **kwargs):
        self.cache_init()

        now = time.time()
        before = len(self.cache.keys())
        self.cache = {key: val for key,val in self.cache.items() if now - val[1] < self.config["expire"]}
        num_expired = before - len(self.cache.keys())
        if num_expired > 0:
            logging.debug("\texpired %d cache keys" % num_expired)

        key = str(self) + str(obj) + str(args) + str(kwargs)
        if key not in self.cache:
            self.cachemisses = self.cachemisses + 1
            logging.debug("\tcache miss. hits: %d misses: %d" % (self.cachehits, self.cachemisses))
            ret = obj(self, *args, **kwargs)
            self.cache[key] = (ret , time.time())
        else:
            val,_ = self.cache[key]
            self.cache[key] = (val, time.time())
            self.cachehits = self.cachehits + 1
            logging.debug("\tcache hit. hits: %d misses: %d" % (self.cachehits, self.cachemisses))
        val,_ = self.cache[key]
        return val
    return cacher

class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.component_types = self._find_component_types()
        self.component_keys = self.component_types.keys()
        self.original_working_directory = os.getcwd()

        self.config = {
                "loglevel": "warning",
                "expire": 3600,
                "plugindir": ["~/.urchin/plugins/"]
                }
        self.mount_configurations = {}
        self.plugins = {}
        self.plugin_components = {}
        self._disambiguation = dict()
        self.refresh = False

        super(UrchinFS, self).__init__(*args, **kwargs)
        self.parser.add_option(mountopt="config", help="configuration file. if set, other options ignored")
        self.parser.add_option(mountopt="source", help="source directory")
        self.parser.add_option(mountopt="plugin", help="plugin name. if set, component options ignored")
        self.parser.add_option(mountopt="plugindir", help="directory in which to find plugins")
        self.parser.add_option(mountopt="refresh", type="int", default=0, help="time before doing a full refresh, in seconds. 0 (default) will not refresh")
        self.parser.add_option(mountopt="log", help="the file to which to log")
        self.parser.add_option(mountopt="loglevel", help="the log level", choices=['debug', 'info', 'warning', 'error', 'critical'])
        self.parser.add_option(mountopt="expire", type="int", default=3600, help="cache expire time in seconds; 0 will never expire")
        for k in self.component_keys:
            self.parser.add_option(mountopt=k, help="%s name" % k)

    #
    # cache
    #
    def cache_init(self):
        if not getattr(self, "cache", None):
            self.cache = {}
        if not getattr(self, "cachehits", None):
            self.cachehits = 0
        if not getattr(self, "cachemisses", None):
            self.cachemisses = 0


    # FIXME ugly
    def cache_reset(self):
        self.cache_init()
        self.cache = {}
        self.cachehits = 0
        self.cachemisses = 0

    #
    # Plugin/component handling
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
        """Load default plugins and plugins found in `plugindir`"""
        logging.debug("loading plugins...")
        # roughly like https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        plugins = {"mp3": mp3, "mp3file": mp3file, "default": default, "json": json, "tmdb": tmdb }
        logging.debug("loaded default plugins")
        if "plugindir" in self.config and self.config["plugindir"]:
            for plugin_path in self.config["plugindir"]:
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

    def _configure_components_from_options(self, mount_options):
        """load a set of components by name, using defaults if not specified"""
        # load the classes defined in default
        component_config = {k: None for k in self.component_keys}
        component_config.update({key: v for key,value in self._components_from_modules([default]).items() for k,v in value.items()})
        # override with the classes specified on the command line
        for component_key in self.component_keys:
            if component_key in mount_options:
                component_name = mount_options[component_key]
                if component_name in self.plugin_components[component_key]:
                    component_config[component_key] = self.plugin_components[component_key][component_name]
                else:
                    logging.debug("could not find plugin '%s'" % component_name)
                    raise ConfigurationError("Could not find specified plugin '%s' for %s component" % (component_name, component_key))
        logging.debug("component configuration from options:\n%s" % pprint.pformat(component_config))
        return component_config

    def _configure_components(self, mount_options):
        logging.debug("configuring components for mount_options %s..." % mount_options)
        if "plugin" in mount_options:
            config = self._configure_components_from_plugin(mount_options["plugin"])
        else:
            config = self._configure_components_from_options(mount_options)
        for k in self.component_keys:
            if k not in config or not config[k]:
                raise ConfigurationError("No component specified for '%s'" % k)
        logging.debug("using component config:\n%s" % pprint.pformat(config))
        return {k: cls(mount_options) for k,cls in config.iteritems()}

    #
    # Indexing
    #

    def _clean_formatted_names(self, formatted_names):
        names = []
        for name in formatted_names:
            name = self._clean_display_value(name)
            if name:
                names.append(name)
        return set(names)

    _display_value_regex = re.compile(u"^\s+|\s+$|^-+|^~+|[/\u0000-\u001F\u007f\u0085\u2028\u2029]", re.U)
    def _clean_display_value(self, value):
        """
        repeatedly removes disallowed characters:
        - leading whitespace
        - leading hyphens
        - leading tilde
        - trailing whitespace
        - slashes
        - control characters (NUL, BEL, TAB(!), etc)
        - line breaks (\n, \r, \v, \f, file separator, group separator, record separator, NEL, line separator, paragraph separator)
        """
        orig = value
        while True:
            new = self._display_value_regex.sub("", value)
            if new == value:
                break
            value = new
        if value == "." or value == "..":
            value = None
        if not value:
            logging.debug("ignoring value [%s]; after replacing disallowed characters, value is empty." % orig)
        return value

    def _disambiguate_formatted_names(self, formatted_names):
        """return a tuple and a disambiguation number for each name in formatted_names"""
        names = set(formatted_names)
        out = []
        for name in formatted_names:
            idx = 0
            if name in self._disambiguation:
                idx = self._disambiguation[name] + 1
            self._disambiguation[name] = idx
            out.append((name, idx))
        return out

    def _make_entry(self, item_path, components, old_entry=None):
        sources = components["matcher"].match(item_path)
        raw_metadata = {source: components["extractor"].extract(source) for source in sources}
        combined_metadata = components["merger"].merge(raw_metadata)
        metadata = components["munger"].mung(combined_metadata)
        metadata = self._clean_metadata(metadata)

        formatted_names = components["formatter"].format(item_path, metadata)
        cleaned_formatted_names = self._clean_formatted_names(formatted_names)
        disambiguated_cleaned_formatted_names = []

        if old_entry:
            for name in cleaned_formatted_names:
                for old_name,idx in old_entry.name_tuples:
                    if old_name == name:
                        disambiguated_cleaned_formatted_names.append((old_name,idx))
                        break
            remove = [name for name,_ in disambiguated_cleaned_formatted_names]
            cleaned_formatted_names = [name for name in cleaned_formatted_names if name not in remove]

        disambiguated_cleaned_formatted_names.extend(self._disambiguate_formatted_names(cleaned_formatted_names))
        return Entry(item_path, sources, metadata, disambiguated_cleaned_formatted_names)

    def _clean_metadata(self, metadata):
        """
        cleans up the metadata dict for an entry
        - removes invalid characters
        - removes empty keys and values
        - removes keys with no values
        """
        md = {}
        for k,vals in metadata.items():
            newvals = [self._clean_display_value(v) for v in vals]
            newvals = [v for v in newvals if v]
            if not newvals:
                continue
            newkey = self._clean_display_value(k)
            if not newkey:
                continue
            md[newkey] = set(newvals)
        return md

    def _make_entries(self, components, path, old_entries=None):
        """
        make the entries for `path` given the defined `components`
        if `old_entries` is set, if a matching entry is found, its matching formatted paths are retained
        """
        entries = []
        indexed = components["indexer"].index(path)
        logging.debug("indexed path %s gave item paths: %s" % (path, pprint.pformat(indexed)))
        for item_path in indexed:
            from_old = False
            if old_entries:
                for old_entry in old_entries:
                    if old_entry.path == item_path:
                        from_old = True
                        entries.append(self._make_entry(item_path, components, old_entry))
                        break
            if not from_old:
                entries.append(self._make_entry(item_path, components))
        logging.debug("entries: %s" % pprint.pformat(entries))
        return entries

    #
    # Initialization
    #

    def fsinit(self):
        logging.debug("initialized filesystem")

    def fsdestroy(self):
        logging.debug("destroying filesystem")
        self.db.close()
        if "db.tmp" in self.config and self.config["db.tmp"]:
            os.remove(self.config["db"])
        logging.debug("destroyed filesystem")

    def configure(self):
        config = self._get_config_from_file() if self.cmdline[0].config else self._get_config_from_options()
        self.config.update(config)
        self.config = self._normalize_config_paths(self.config)
        self._configure_logging()

        logging.debug("configuring filesystem...")
        self.plugins = self._load_plugins()
        self.plugin_components = self._find_plugin_components()
        self._configure_db()
        self._create_mount_configurations()
        logging.debug("configured filesystem")

    def _configure_db(self):
        if "db" not in self.config or not self.config["db"]:
            base = self._normalize_path("~/.urchin/")
            tmppath = os.path.join(base, "tmp")
            self.config["db"] = os.path.join(tmppath, "%s.db" % uuid.uuid4())
            self.config["db.tmp"] = True
            logging.debug("No database path configured, using %s" % self.config["db"])
            if not os.path.exists(base):
                raise ConfigurationError("No existing urchin directory: %s" % base)
            if os.path.exists(tmppath) and os.path.isfile(tmppath):
                raise ConfigurationError("Temporary urchin path is not a directory: %s" % tmppath)
            if not os.path.exists(tmppath):
                try:
                    os.mkdir(tmppath)
                except OSError:
                    raise ConfigurationError("Could not make temporary directory: %s" % tmppath)
        self.config["db"] = self._normalize_path(self.config["db"])
        self.db = sqlite3.connect(self.config["db"])
        c = self.db.cursor()
        c.execute("create table if not exists mount (id integer primary key, name text not null)")
        c.execute("create table if not exists item (id integer primary key, mount_id integer not null, path text not null)")
        c.execute("create table if not exists source (id integer primary key, item_id integer not null, path text not null)")
        c.execute("create table if not exists metadata (id integer primary key, source_id integer not null, key text not null, value text not null)")
        c.execute("create table if not exists name (id integer primary key, item_id integer not null, name text not null)")
        c.close()
        self.db.commit()

    def _normalize_config_paths(self, config):
        """expand and normalize paths defined in configuration"""
        if "log" in config:
            config["log"] = self._normalize_path(config["log"])
        if "mounts" in config:
            for mount in config["mounts"]:
                mount["source"] = self._normalize_path(mount["source"])
        if "plugindir" in config:
            config["plugindir"] = [self._normalize_path(dir) for dir in self.config["plugindir"]]
        return config

    _logging_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL
            }
    def _configure_logging(self):
        log = logging.getLogger()
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
        if "log" in self.config and self.config["log"]:
            logfile = self.config["log"]
            fileh = logging.FileHandler(logfile, 'a')
            fileh.setFormatter(formatter)
            # remove all old handlers and set the new one
            for hdlr in log.handlers:
                log.removeHandler(hdlr)
            log.addHandler(fileh)
        if "loglevel" in self.config and self.config["loglevel"]:
            loglevel = self.config["loglevel"]
            if loglevel not in self._logging_map:
                raise ConfigurationError("loglevel must be one of: %s" % ",".join(self._logging_map.keys()))
            log.setLevel(self._logging_map[loglevel])

    def _get_config_from_options(self):
        logging.debug("loading configuration from command line options")
        options = self.cmdline[0]
        config = {}
        d = {k:v for k,v in vars(options).items() if v}
        # all options except these are part of the single mount configuration
        # which can be specified on the command line/in the fstab
        nonmount = ["loglevel", "log", "expire", "plugindir"]
        for opt in nonmount:
            if opt in d:
                config[opt] = d[opt]
                del d[opt]
        config["mounts"] = [d]
        if "plugindir" in config:
            config["plugindir"] = [config["plugindir"]]
        config["from_file"] = False
        return config

    def _get_config_from_file(self):
        """configuration must be a python file with a variable 'config' which is a dict or dict-like."""
        path = self.cmdline[0].config
        logging.debug("loading configuration from [%s], other options ignored" % path)
        path = self._normalize_path(path)
        context = {}
        try:
            execfile(path, context)
        except Exception:
            raise ConfigurationError("Error while attempting to load configuration from %s" % path)
        if "config" not in context:
            raise ConfigurationError("No 'config' variable defined in %s" % path)
        config = context["config"]
        config["from_file"] = True
        return config

    def _create_mount_configurations(self):
        for mount_options in self.config["mounts"]:
            components = self._configure_components(mount_options)
            logging.debug("components: %s" % pprint.pformat(components))
            entries = self._make_entries(components, mount_options["source"])
            refresh = 0
            if "refresh" in mount_options:
                refresh = mount_options["refresh"]
            if refresh > 0:
                self.refresh = True # set if any mount config will refresh
            self.mount_configurations[mount_options["source"]] = {
                    "config": mount_options,
                    "components": components,
                    "entries": entries,
                    "refresh": refresh,
                    "last_update": time.time(),
                    }

    def _refresh(self):
        refresh_time = time.time()
        for source,config in self.mount_configurations.items():
            if config["refresh"] > 0:
                if refresh_time - config["last_update"] > config["refresh"]:
                    logging.debug("refreshing %s" % source)
                    config["last_update"] = refresh_time
                    config["entries"] = self._make_entries(config["components"], source, config["entries"])
                    self.cache_reset()

    #
    # util
    #

    def _normalize_path(self, path):
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.original_working_directory, path)
        return os.path.normpath(path)

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

    #
    # Lookups
    #

    def _get_results(self, path):
        if self.refresh:
            self._refresh()
        parts = self._strip_empty_prefix(self._split_path(path))
        return self._get_results_from_parts(parts)

    @cache
    def _get_results_from_parts(self, parts):
        if not parts: # root dir
            return [result for configuration in self.mount_configurations.values() for entry in configuration["entries"] for result in entry.results] + [_AND_RESULT, _CUR_RESULT, _PARENT_RESULT]

        # fake enum
        class Parsed:
            KEY, VAL, AND, OR, NONE, DIR = range(1,7)

        found = [entry for configuration in self.mount_configurations.values() for entry in configuration["entries"]]
        current_valid_keys = set([key for entry in found for key in entry.metadata.keys()])
        current_valid_values = set()
        current_key = None
        state = dict()

        last = Parsed.NONE
        last_index = len(parts)-1

        for index,part in enumerate(parts):
            is_last = index == last_index

            if part == _AND:
                last = Parsed.AND
                current_key = None
                current_valid_values = set()
                current_valid_keys = set([key for key in entry.metadata.keys() for entry in found]) - set(state.keys())
                if is_last:
                    return [Result(key) for key in current_valid_keys] + [_CUR_RESULT, _PARENT_RESULT]
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
                    return [Result(value) for value in current_valid_values] + [_CUR_RESULT, _PARENT_RESULT]
            elif last == Parsed.VAL and part == _OR:
                last = Parsed.OR
                if is_last:
                    return [Result(value) for value in current_valid_values] + [_CUR_RESULT, _PARENT_RESULT]
            elif last == Parsed.KEY or last == Parsed.OR:
                last = Parsed.VAL
                if part not in current_valid_values:
                    logging.debug("current_valid_values: %s" % ','.join(current_valid_values))
                    raise InvalidPathError("invalid value [%s]" % part)
                current_valid_values = current_valid_values - set([part])
                state[current_key].add(part)
                # lookahead, and if the next token is _not_ an OR,
                # filter the entries by the current facet
                if is_last or (not is_last and parts[index+1] != _OR):
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
                    ret = [r for f in found for r in f.results] + [_CUR_RESULT, _PARENT_RESULT]
                    # add AND and OR if appropriate
                    if len(current_valid_values) > 0:
                        ret = ret + [_OR_RESULT]
                    if len(current_valid_keys) > 0:
                        ret = ret + [_AND_RESULT]
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
                            return [Result(_CUR, r.destination)]
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
                if r.name == _CUR:
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
                if r.name == _CUR:
                    return r.destination
        except InvalidPathError:
            pass
        return -errno.ENOENT

class ConfigurationError(fuse.FuseError):
    pass

class InvalidPathError(Exception):
    pass

class _immutable(type):
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
    `name_tuples` is a list of tuples of (name, disambiguation_number); the names by which the entry will be displayed
    """
    __metaclass__ = _immutable
    def __init__(self, path, metadata_paths, metadata, name_tuples):
        assert type(path) == str
        self.path = path
        assert type(metadata_paths) == set
        self.metadata_paths = metadata_paths
        assert type(metadata) == dict
        self.metadata = metadata
        assert type(name_tuples) == list
        if name_tuples:
            assert type(name_tuples[0]) == tuple
        self.name_tuples = name_tuples
        self.results = [Result("%s (%s)" % (name, idx) if idx != 0 else name, self.path) for name,idx in self.name_tuples]
    # TODO evaluate if we should make an inverted hash
    #def __hash__(self):
    #    # TODO should this take into account the metadata values?
    #    return hash((self.path,)
    #           + tuple(self.metadata_paths)
    #           + tuple(self.name_tuples)
    #           + tuple(self.metadata.keys()))
    def __repr__(self):
        return "<Entry %s -> %s>" % (self.path, "[%s]" % ",".join(["%s (%s)" % (name, idx) if idx != 0 else name for name,idx in self.name_tuples]))

class Result(object):
    """representation of a directory/symlink"""
    def __init__(self, name, destination=None):
        self.name = name
        self.destination = destination
        self.mode = (stat.S_IFLNK | 0777) if self.destination else (stat.S_IFDIR | 0755)
        # "The size of a symbolic link is the length of the
        # pathname it contains, without a terminating null byte."
        self.size = len(name) if self.destination else Stat.DIRSIZE
    def __repr__(self):
        return "<Result %s>" % (self.name.encode("utf-8") if self.destination is None else "%s -> %s" % (self.name.encode("utf-8"), self.destination))

_AND = u"^"
_OR = u"+"
_CUR = u"."
_PARENT= u".."

_AND_RESULT = Result(_AND)
_OR_RESULT = Result(_OR)
_CUR_RESULT = Result(_CUR)
_PARENT_RESULT = Result(_PARENT)

def main():
    server = UrchinFS(version="%prog " + __version__, dash_s_do='setsingle')
    args = server.parse(errex=1)
    server.multithreaded = 0
    try:
        server.configure()
    except ConfigurationError, e:
        msg = "Failed to configure filesystem, exiting. Cause:\n\t%s" % e.message
        logging.error(msg)
        sys.stderr.write(msg)
        sys.exit(1)
    try:
        server.main()
    except fuse.FuseError, e:
        msg = "Error during filesystem operation. Cause:\n\t%s" % e.message
        logging.error(msg)
        sys.stderr.write(msg)
        sys.exit(1)

if __name__ == '__main__':
    main()
