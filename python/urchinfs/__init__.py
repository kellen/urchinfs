#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import stat
import errno
import logging
import fnmatch
import types
import re

import fuse

# local
import plugin, default

from core import Stat, TemplateFS

"""urchin-fs TODO"""

LOG_FILENAME = "LOG"
#logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO,)
logging.basicConfig(level=logging.INFO,)
logging.getLogger().addHandler(logging.StreamHandler())
#logging.basicConfig(level=logging.ERROR,)
fuse.fuse_python_api = (0, 2)

class UrchinFSEntry(object):
    def __init__(self, path, metadata_paths, metadata, formatted_names):
        self.path = path
        self.metadata_paths = metadata_paths
        self.metadata = metadata
        self.formatted_names = formatted_names
        #FIXME probably need to retain the matchers/extractors/formatters in order to update?

class ConfigurationError(Exception):
    pass

# TODO remove references to TemplateFS since it has some demo funcitonality we don't want
class UrchinFS(TemplateFS):
    def __init__(self, *args, **kwargs):
        self.plugin_search_paths = ["~/.urchinfs/plugins/"]
        self.component_types = self.find_component_types()
        self.plugin_keys = component_types.keys()

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
        components = dict()
        for cls in plugin.__dict__.items():
            if isinstance(cls, type) and hasattr(cls, 'component'):
                components[cls.name] = cls
        return components

    plugin_main_module = "__init__"
    def load_plugins(self):
        # roughly like https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        plugins = dict()
        for plugin_path in plugin_search_paths:
            for name in os.listdir(plugin_path):
                path = os.path.join(plugin_path, name)
                if os.path.isdir(path) and "%s.py" % plugin_main_module in os.listdir(path):
                    try:
                        info = imp.find_module("__init__", [location])
                        # FIXME this seems wrong
                        plugins[name] = imp.load_module(plugin_main_module, info)
                    except ImportError:
                        logging.warning("plugin module '%s' has no '%s'" % (name, plugin_main_module))
        return plugins

    def find_plugin_components(self, plugins):
        # find all named plugin classes
        named = []
        for plugin in plugins:
            for (name, cls) in plugin.__dict__.items():
                if isinstance(cls, type) and hasattr(cls, "name"):
                    named.append(cls)
        # sort by type
        plugin_components = dict()
        for component_name,component_cls in self.component_types.iteritems():
            # fuck duck typing
            plugin_components[component_name] = {cls.name: cls for cls in named if issubclass(cls, component_cls)}
        return plugin_components

    def fsinit(self):
        plugins = load_plugins()
        plugin_components = find_components(plugins)

        # FIXME split options into option sets if python-fuse can even accept duplicate args
        from_cmdline = {key: cmdline[key] for key in self.plugin_keys if key in cmdline} # FIXME this should be all options
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
            for option, option_value in option_set.iteritems():
                if option in self.plugin_keys:
                    if option_value in available_components[option]:
                        # fetch the class with the short name for this component
                        config[option] = plugin_components[option][option_value]
            for k,v in plugin_config:
                if not v:
                    raise ConfigurationError("No component specified for '%s'" % k)
            components = {k: cls(config) for k,cls in plugin_config.iteritems()}

def main():
    # FIXME this usage sucks
    usage = """UrchinFS: A faceted-search FUSE file system.""" + fuse.Fuse.fusage
    server = UrchinFS(version="%prog " + fuse.__version__, usage=usage, dash_s_do='setsingle')
    server.parse(errex=1)
    server.multithreaded = 0
    try:
        server.main()
    except fuse.FuseError, e:
        print str(e)

if __name__ == '__main__':
    main()

logging.debug("File system unmounted")
