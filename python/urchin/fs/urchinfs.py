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

class UrchinFSEntry(object):
    def __init__(self, path, metadata_paths, metadata, formatted_names):
        self.path = path
        self.metadata_paths = metadata_paths
        self.metadata = metadata
        self.formatted_names = formatted_names

class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.plugin_search_paths = ["~/.urchin/plugins/"]
        self.component_types = self.find_component_types()
        self.plugin_keys = self.component_types.keys()

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
        plugins = {"mp3": mp3, "default": default, "json": json }
        logging.debug("loaded default plugins")
        # FIXME TEST THIS
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
                                # FIXME this seems wrong
                                plugins[name] = imp.load_module(self.plugin_main_module, info[0], info[1], info[2])
                                logging.debug("found plugin module '%s'" % name)
                                info[0].close()
                            except ImportError:
                                logging.warning("plugin module '%s' has no '%s'" % (name, plugin_main_module))
        logging.debug("loaded plugins:\n%s" % pprint.pformat(plugins))
        return plugins

    def find_plugin_components(self, plugins):
        """Find all named plugin classes and sort them by the command-line parameter for which they are valid"""
        logging.debug("loading plugin components...")
        # find all named plugin classes
        named = []
        for plugin in plugins.values():
            for (name, cls) in plugin.__dict__.items():
                if isinstance(cls, type) and hasattr(cls, "name"):
                    named.append(cls)
        # sort by type
        plugin_components = dict()
        for component_name,component_cls in self.component_types.iteritems():
            plugin_components[component_name] = {cls.name: cls for cls in named if issubclass(cls, component_cls)} # fuck duck typing
        logging.debug("loaded plugin components:\n%s" % pprint.pformat(plugin_components))
        return plugin_components

    def configure_components(self, option_set, config, plugin_components):
        logging.debug("configuring components for option_set %s..." % option_set)
        # each "option set" describes the configuration of a specific source directory/way of formatting
        plugin_config = {"indexer": None, "matcher": default.DefaultMetadataMatcher, "extractor": None,
                "merger": default.DefaultMerger, "munger": default.DefaultMunger, "formatter":  default.DefaultFormatter}
        for plugin_key in self.plugin_keys:
            if plugin_key in option_set:
                plugin_short_name = option_set[plugin_key]
                if plugin_short_name in plugin_components[plugin_key]:
                    plugin_config[plugin_key] = plugin_components[plugin_key][plugin_short_name]
                else:
                    logging.debug("could not find plugin '%s'" % plugin_short_name)
                    raise ConfigurationError("Could not find specified plugin '%s' for %s component" % (plugin_short_name, plugin_key))
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
            entries.append(UrchinFSEntry(path, sources, metadata, formatted_names))
        logging.debug("entries: %s" % pprint.pformat(entries))
        return entries

    def fsinit(self):
        logging.debug("initializing filesystem...")
        try:
            options = self.cmdline[0]
            logging.debug("Option arguments: " + str(options))
            logging.debug("Nonoption arguments: " + str(self.cmdline[1]))
            plugin_components = self.find_plugin_components(self.load_plugins())

            # FIXME rework this so we don't have to fetch from cmdline
            from_cmdline = {key: getattr(options, key) for key in self.plugin_keys if hasattr(options, key)}
            from_cmdline["source"] = options.source
            option_sets = [from_cmdline]
            logging.debug("from_cmdline: %s" % from_cmdline)

            self.mount_configurations = {}
            for option_set in option_sets:
                config = dict() # FIXME which options should be here?
                components = self.configure_components(option_set, config, plugin_components)
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
