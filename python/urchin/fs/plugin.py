#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import

class Plugin(object):
    """Plugin encapsulates a set of processing classes"""
    def __init__(self, indexer, matcher, extractor, merger, munger, formatter):
        self.indexer = indexer
        self.matcher = matcher
        self.extractor = extractor
        self.merger = merger
        self.munger = munger
        self.formatter = formatter

class Indexer(object):
    """Finds items to be indexed"""
    component = "indexer"
    def __init__(self, config):
        pass
    def index(self, path):
        """Return a list of paths to be indexed"""
        raise NotImplementedError()

class MetadataMatcher(object):
    """For a given item path, matches paths from which metadata should be extracted"""
    component = "matcher"
    def __init__(self, config):
        pass
    def match(self, path):
        """Return a list of paths from which to extract metadata"""
        raise NotImplementedError()

class MetadataExtractor(object):
    """Metadata extractor"""
    component = "extractor"
    def __init__(self, config):
        pass
    def extract(self, path):
        """
        Takes a file path and returns a dict with string keys and sets of strings as values.
        metadata[key] = set(value1, value2)
        """
        raise NotImplementedError()

class MetadataMunger(object):
    """
    Metadata munger

    Cleans up metadata by manipulating/removing values or adding/removing structure
    """
    component = "munger"
    def __init__(self, config):
        pass
    def mung(self, metadata):
        raise NotImplementedError()

class MetadataMerger(object):
    """Merges metadata when multiple sources are involved"""
    component = "merger"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        """
        Merges `metadata`, a list of dicts with string keys and sets of strings as values
        into a single dict with string keys and sets of strings as values.
        """
        raise NotImplementedError()

class Formatter(object):
    """Formatter for display names."""
    component = "formatter"
    def format(self, original_name, metadata):
        """Takes the original file/directory name and associated metadata and returns one or more formatted "display names" """
        raise NotImplementedError()
