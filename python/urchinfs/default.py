#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from fnmatch import fnmatch
from urchinfs import MetadataMatcher, MetadataMerger, Formatter

def SelfMetadataMatcher(MetadataMatcher):
    """Minimal matcher which returns the item path"""
    name = "default"
    def match(self, path):
        return path

# FIXME WRITE THIS
class DefaultMerger(MetadataMerger):
    name = "default"
    def __init(self, config):
        pass
    def merge(self, metadata):
        pass

class DefaultFormatter(Formatter):
    """Default formatter which returns the original item file/directory name"""
    name = "default"
    def format(self, original_name, metadata):
        return original_name

