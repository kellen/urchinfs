#!/usr/bin/env python
# -*- coding: utf-8 -*-

from urchinfs import Indexer, MetadataMatcher, Formatter
from urchinfs.default import SelfMetadataMatcher, DefaultFormatter

"""
class Plugin(object):
    def __init__(self, item_matcher=None, metadata_matcher=SelfMetadataMatcher,
            metadata_extractor=None, metadata_merger=None,
            formatter=G):
        pass
        self.item_matcher = item_matcher
        self.metadata_matcher = 
"""

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

class MetadataMerger(object):
    """Merges metadata when multiple sources are involved"""
    component = "merger"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        """Merges metadata from multiple sources, potentially removing some keys or values"""
        raise NotImplementedError()

class Formatter(object):
    """Formatter for display names."""
    component = "formatter"
    def format(self, original_name, metadata):
        """Takes the original file/directory name and associated metadata and returns one or more formatted "display names" """
        raise NotImplementedError()
