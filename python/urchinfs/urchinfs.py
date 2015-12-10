#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

# local
import plugin, default, mp3, json

from core import Stat, TemplateFS

"""urchin-fs TODO"""

#LOG_FILENAME = "LOG"
#logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO,)
logging.basicConfig(level=logging.DEBUG,)
#logging.getLogger().addHandler(logging.StreamHandler())
#logging.basicConfig(level=logging.ERROR,)
fuse.fuse_python_api = (0, 2)

class UrchinFSEntry(object):
    def __init__(self, path, metadata_paths, metadata, formatted_names):
        self.path = path
        self.metadata_paths = metadata_paths
        self.metadata = metadata
        self.formatted_names = formatted_names
        #FIXME probably need to retain the matchers/extractors/formatters in order to update?

class ConfigurationError(fuse.FuseError):
    pass

# TODO remove references to TemplateFS since it has some demo funcitonality we don't want
class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.plugin_search_paths = ["~/.urchinfs/plugins/"]
        self.component_types = self.find_component_types()
        self.plugin_keys = self.component_types.keys()

        super(UrchinFS, self).__init__(*args, **kwargs)
        # -o indexer=json,matcher=json,extractor=json,merger=default,formatter=default,source="../test",watch=true
        self.parser.add_option(mountopt="source", help="source directory")
        self.parser.add_option(mountopt="indexer", help="indexer class")
        self.parser.add_option(mountopt="matcher", help="matcher class")
        self.parser.add_option(mountopt="extractor", help="extractor class")
        self.parser.add_option(mountopt="merger", help="merger class")
        self.parser.add_option(mountopt="formatter", help="formatter class")
        self.parser.add_option(mountopt="plugin", help="plugin class")
        self.parser.add_option(mountopt="watch", help="watch the source directory for changes?")

    def find_component_types(self):
        logging.debug("finding component types")
        components = dict()
        for (name, cls) in plugin.__dict__.items():
            if isinstance(cls, type) and hasattr(cls, 'component'):
                components[cls.component] = cls
        logging.debug("Found component types %s" % components)
        return components

    plugin_main_module = "__init__"
    def load_plugins(self):
        logging.debug("loading plugins")
        # roughly like https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        plugins = {
                "mp3": mp3,
                "default": default,
                "json": json
                }
        logging.debug("loaded default plugins")
        # FIXME TEST THIS
        for plugin_path in self.plugin_search_paths:
            logging.debug("searching for plugins in %s" % plugin_path)
            if os.path.exists(plugin_path) and os.path.isdir(plugin_path):
                for name in os.listdir(plugin_path):
                    path = os.path.join(plugin_path, name)
                    if os.path.isdir(path) and "%s.py" % plugin_main_module in os.listdir(path):
                        try:
                            info = imp.find_module("__init__", [location])
                            # FIXME this seems wrong
                            plugins[name] = imp.load_module(plugin_main_module, info)
                        except ImportError:
                            logging.warning("plugin module '%s' has no '%s'" % (name, plugin_main_module))
        logging.debug("found plugins:\n%s" % pprint.pformat(plugins))
        return plugins

    def find_plugin_components(self, plugins):
        logging.debug("loading plugin components")
        # find all named plugin classes
        named = []
        for plugin in plugins.values():
            for (name, cls) in plugin.__dict__.items():
                if isinstance(cls, type) and hasattr(cls, "name"):
                    named.append(cls)
        # sort by type
        plugin_components = dict()
        for component_name,component_cls in self.component_types.iteritems():
            # fuck duck typing
            plugin_components[component_name] = {cls.name: cls for cls in named if issubclass(cls, component_cls)}
            #logging.debug("finding components of type %s (%s)" % (component_name, component_cls))
            #plugin_components[component_name] = dict()
            #for cls in named:
            #    #logging.debug("testing class %s" % cls)
            #    if issubclass(cls, component_cls):
            #        #logging.debug("class %s is of type %s" % (cls, component_cls))
            #        plugin_components[component_name][cls.name] = cls
        logging.debug("found plugin components:\n%s" % pprint.pformat(plugin_components))
        return plugin_components

    def fsinit(self):
        try:
            logging.debug("initializing filesystem")
            logging.debug("Option arguments: " + str(self.cmdline[0]))
            logging.debug("Nonoption arguments: " + str(self.cmdline[1]))

            plugins = self.load_plugins()
            plugin_components = self.find_plugin_components(plugins)

            #from_cmdline = dict()
            #for key in self.plugin_keys:
            #    if hasattr(self.cmdline[0], key):
            #        from_cmdline[key] = getattr(self.cmdline[0],key)
            from_cmdline = {key: getattr(self.cmdline[0], key) for key in self.plugin_keys if hasattr(self.cmdline[0], key)}

            logging.debug("from_cmdline: %s" % from_cmdline)
            options = [from_cmdline]
            for option_set in options:
                config = dict() # FIXME which options should be here?
                # each "option set" describes the configuration of a specific source directory/way of formatting
                plugin_config = {
                        "indexer": None,
                        "matcher": default.SelfMetadataMatcher,
                        "extractor": None,
                        "merger": default.DefaultMerger,
                        "formatter":  default.DefaultFormatter
                        }
                logging.debug("option_set: %s" % option_set)
                # FIXME THROW ERROR ON NOT FOUND
                for plugin_key in self.plugin_keys:
                    logging.debug("key: %s" % plugin_key)
                    if plugin_key in option_set:
                        logging.debug("in option set: %s" % plugin_key)
                        plugin_short_name = option_set[plugin_key]
                        logging.debug("short name: %s" % plugin_short_name)

                        if plugin_short_name in plugin_components[plugin_key]:
                            plugin_config[plugin_key] = plugin_components[plugin_key][plugin_short_name]
                            logging.debug("plugin_config now:\n%s" % pprint.pformat(plugin_config))
                        else:
                            logging.debug("could not find plugin '%s'" % plugin_short_name)
                            raise ConfigurationError("Could not find specified plugin '%s' for %s component" % (plugin_short_name, plugin_key))
                logging.debug("using plugin_config:\n%s" % pprint.pformat(plugin_config))
                for k,v in plugin_config.iteritems():
                    if not v:
                        raise ConfigurationError("No component specified for '%s'" % k)
                components = {k: cls for k,cls in plugin_config.iteritems()}
        except Exception, e:
            #
            # FIXME Fatal errors should be resolved before init() (or potentially even main()) is called
            # FIXME so.... perhaps do our own options parsing so we can load all the plugins before we get to here.
            #
            # Errors in fsinit() go back via FUSE so they won't bubble up properly.
            # Assume any error here to be fatal
            logging.exception("Failed to initialize filesystem.")

def main():
    # FIXME this usage sucks
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
