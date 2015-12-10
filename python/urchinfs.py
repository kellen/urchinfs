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
    plugin_keys = ["indexer", "matcher", "extractor", "merger", "formatter"]
    def __init__(self, *args, **kwargs):
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
        self.plugin_search_paths = ["~/.urchinfs/plugins/"]

    main_module = "__init__"
    def load_plugins(self):
        # roughly like https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        plugins = dict()
        for plugin_path in plugin_search_paths:
            for name in os.listdir(plugin_path):
                path = os.path.join(plugin_path, name)
                if os.path.isdir(path) and "%s.py" % main_module in os.listdir(path):
                    try:
                        info = imp.find_module("__init__", [location])
                        # FIXME this seems wrong
                        plugins[name] = imp.load_module(main_module, info)
                    except ImportError:
                        logging.warning("plugin module '%s' has no '%s'" % (name, main_module))
        return plugins


    def import_class(self, cl):
        # FIXME perhaps do this instead: https://lkubuntu.wordpress.com/2012/10/02/writing-a-python-plugin-api/
        # per http://stackoverflow.com/questions/547829/how-to-dynamically-load-a-python-class
        try:
            (modulename, classname) = cl.rsplit('.', 1)
            m = __import__(modulename, globals(), locals(), [classname])
            return getattr(m, classname)
        except:
            raise ConfigurationError("Could not load class '%s'" % cl)

    def fsinit(self):
        loaded_plugins = load_plugins()
        plugin_components = find_components()

        # FIXME split options into option sets if python-fuse can even accept duplicate args
        from_cmdline = {key: cmdline[key] for key in plugin_keys if key in cmdline}
        options = [from_cmdline]
        for option_set in options:
            # each "option set" describes the configuration of a specific source directory/way of formatting
            config = dict()
            plugin_modules = {key: import_class(option_set[key]) for key in plugin_keys if key in option_set}
            for k,v in plugin_modules.iteritems():
                if k in loaded_plugins:
                    config[key] = loaded_plugins[k]
                elif k in available_plugins
                    plugin = load_plugin(
                    config[key]




            # FIXME use plugins to get correct classes
            #matcher = 
            items = matcher.match(config["path"])

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
