#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
from fnmatch import fnmatch
from urchin.fs.plugin import MetadataMatcher, MetadataMerger, Formatter

class SelfMetadataMatcher(MetadataMatcher):
    """Minimal matcher which returns the item path"""
    name = "default"
    def __init__(self, config):
        pass
    def match(self, path):
        return path

class DefaultMerger(MetadataMerger):
    name = "default"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        merged = dict()
        for source,d in metadata.iteritems():
            for k,v in d.iteritems():

                # FIXME need to add v to a set
                # FIXME dont forget to unpack lists!
                # FIXME may need to modify the extractor to remap {id: value} values

                
                if k not in merged:
                    merged[k] = v
                else:
                    merged[k].update(v)
        return merged

class DefaultFormatter(Formatter):
    """Default formatter which returns the original item file/directory name"""
    name = "default"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        return original_name

