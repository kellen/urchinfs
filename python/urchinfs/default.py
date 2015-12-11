#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from fnmatch import fnmatch
from plugin import MetadataMatcher, MetadataMerger, Formatter

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
        for d in metadata:
            for k,v in d.iteritems():
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

