#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from fnmatch import fnmatch
from urchinfs import Indexer, MetadataMatcher

def AbstractDirectoryIndexer(Indexer):
    """Recursively finds directories in path which have a child file which matches the glob"""
    def __init__(self, config, glob):
        self.glob = glob;
    def match(self, path):
        return [x[0] for x in os.walk(path) if [f for f in x[2] if fnmatch(f, self.glob)]]

def AbstractFileIndexer(Indexer):
    """Recursively finds files which match the glob"""
    def __init__(self, config, glob):
        self.glob = glob
    def match(self, path):
        paths = [[os.path.join(walked[0], filename) for filename in walked[2]] for walked in os.walk(path)]
        flattened = [file for sublist in paths for file in sublist]
        filtered = [file for file in flattened if fnmatch(file, self.glob)]
        return filtered

def AbstractFileMetadataMatcher(MetadataMatcher):
    """
    If `path` is a directory, returns the paths of files which are children and which match `glob`,
    otherwise returns an empty list.
    """
    def __init__(self,config, glob):
        self.glob = glob
    def match(self, path):
        if os.path.isdir(path):
            [os.path.join(path, x) for x in os.listdir(path) if fnmatch(x, self.glob)]
        return []