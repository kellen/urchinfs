#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
from fnmatch import fnmatch
from urchin.fs.plugin import Indexer, MetadataMatcher

class AbstractDirectoryIndexer(Indexer):
    """Recursively finds directories in path which have a child file which matches the glob"""
    def __init__(self, config, glob):
        self.glob = glob;
    def index(self, path):
        return [x[0] for x in os.walk(path) if [f for f in x[2] if fnmatch(f, self.glob)]]

class AbstractFileIndexer(Indexer):
    """Recursively finds files which match the glob"""
    def __init__(self, config, glob):
        self.glob = glob
    def index(self, path):
        paths = [[os.path.join(walked[0], filename) for filename in walked[2]] for walked in os.walk(path)]
        flattened = [file for sublist in paths for file in sublist]
        filtered = [file for file in flattened if fnmatch(file, self.glob)]
        return filtered

class AbstractFileMetadataMatcher(MetadataMatcher):
    """
    If `path` is a directory, returns the paths of files which are children and which match `glob`,
    otherwise returns an empty list.
    """
    def __init__(self,config, glob):
        self.glob = glob
    def match(self, path):
        if os.path.isdir(path):
            return set([os.path.join(path, x) for x in os.listdir(path) if fnmatch(x, self.glob)])
        return set()
