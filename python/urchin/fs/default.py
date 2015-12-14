#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
from fnmatch import fnmatch
import collections

from urchin.fs.plugin import MetadataMatcher, MetadataMunger, MetadataMerger, Formatter

class DefaultMetadataMatcher(MetadataMatcher):
    """Minimal matcher which returns the item path"""
    name = "default"
    def __init__(self, config):
        pass
    def match(self, path):
        return path

class DefaultMerger(MetadataMerger):
    """
    Minimal merger which does as little as possible to the data.
    """
    name = "default"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        merged = dict()
        for source,d in metadata.iteritems():
            for k,v in d.iteritems():
                if k not in merged:
                    merged[k] = v
                else:
                    cur_val_type = type(merged[k])
                    val_type = type(v)
                    if cur_val_type == set and isinstance(v, collections.Hashable):
                        merged[k].update(v)
                    elif cur_val_type == tuple and val_type == tuple:
                        # i guess?
                        merged[k] = merged[k] + val_type
                    elif cur_val_type == list and val_type == list:
                        merged[k].extend(v)
                    elif cur_val_type == list:
                        merged[k].add(v)
                    else:
                        merged[k] = [merged[k], v]
                    #else:
                    #    logger.debug("could not merge key '%s' value types '%s' and '%s'" % (k, cur_val_type, val_type))
        return merged

class DefaultMunger(MetadataMunger):
    """Minimal munger which does nothing to the data"""
    name = "default"
    def __init__(self, config):
        pass
    def mung(self, metadata):
        return metadata

class DefaultFormatter(Formatter):
    """Default formatter which returns the original item file/directory name"""
    name = "default"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        return original_name

