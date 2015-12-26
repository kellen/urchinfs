#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from urchin.fs.plugin import Matcher

class GlobFileMatcher(Matcher):
    """Matches files with filenames matching a given glob"""
    def __init__(self, config):
        # FIXME implement
        self.glob = config.glob
    def match(self, path):
        # FIXME how the fuck to get the glob here? some generic config options for every instance?
        raise NotImplementedError()

class FileGlobDirectoryMatcher(Matcher):
    """
    """
    def match(self, path):
        raise NotImplementedError()

class DefaultIndexer(Indexer):
    """
    """
    def index(self, path, metadata):
        """
        Returns some number of items to be indexed.
        """
        raise NotImplementedError()
