#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import getopt
import argparse
import logging
import re
import pprint
import requests
import urllib

from tmdb3 import set_key, searchMovie
from googlesearch import GoogleSearch

logging.basicConfig(level=logging.DEBUG,)

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

class SearchError(Exception):
    def __init__(self, msg):
        self.msg = msg

class MovieFetcher(object):
    # from http://kodi.wiki/view/Advancedsettings.xml#cleanstrings
    # a separator or start-of-string, followed by a stopword, followed by a separator or end-of-string
    #cleanup_regex = re.compile(r"""
    #(^|[ _,.()\[\]\-])(
    #    ac3|dts|custom|dc|divx|divx5|dsr|dsrip|dutch|dvd|dvdrip|dvdscr|dvdscreener|screener|dvdivx|cam|fragment|
    #    fs|hdtv|hdrip|hdtvrip|internal|limited|multisubs|ntsc|ogg|ogm|pal|pdtv|proper|repack|rerip|retail|cd[1-9]|
    #    r3|r5|bd5|se|svcd|swedish|german|read.nfo|nfofix|unrated|ws|telesync|ts|telecine|tc|brrip|bdrip|480p|480i|
    #    576p|576i|720p|720i|1080p|1080i|hrhd|hrhdtv|hddvd|bluray|x264|h264|xvid|xvidvd|xxx|www.www|
    #    \[.*\]  # anything enclosed in brackets
    #)([ _,.()\[\]\-]|$)  # separator or end-of-string
    #""", re.VERBOSE | re.IGNORECASE)

    cleanup_regex = re.compile(r"(^|[ _,.()\[\]\-])(ac3|dts|custom|dc|divx|divx5|dsr|dsrip|dutch|dvd|dvdrip|dvdscr|dvdscreener|screener|dvdivx|cam|fragment|fs|hdtv|hdrip|hdtvrip|internal|limited|multisubs|ntsc|ogg|ogm|pal|pdtv|proper|repack|rerip|retail|cd[1-9]|r3|r5|bd5|se|svcd|swedish|german|read.nfo|nfofix|unrated|ws|telesync|ts|telecine|tc|brrip|bdrip|480p|480i|576p|576i|720p|720i|1080p|1080i|hrhd|hrhdtv|hddvd|bluray|x264|h264|xvid|xvidvd|xxx|www.www|\[.*\])([ _,.()\[\]\-]|$)", re.IGNORECASE)

    def __init__(self):
        api_key = None
        api_key_path = os.path.expanduser("~/.urchin/api_key")
        with open(api_key_path, 'r') as api_key_file:
            api_key = api_key_file.read().strip()
            set_key(api_key)
    def suggest(self, query):
        excludes = [
                    #"Parents Guide", "Plot Summary", "Release Info", "Quotes", "Taglines", "FAQ", "Trivia", "News",
                    #"Full Cast", "Technical Specifications", "Goofs", "Filming Locations", "User ratings",
                    #"Critic Reviews", "Company credits", "Synopsis", "External Reviews", "Soundtracks", "Recommendations"
                   ]
        google_query = ' '.join([
                        #'allintitle:',
                        query,
                        ' '.join(['-"%s"' % e for e in excludes]),
                        'site:imdb.com/title/'
                    ])
        logging.debug("querying google with: %s" % google_query)
        gs = GoogleSearch(google_query)
        for hit in gs.top_results():
            print hit["url"], "->", hit["titleNoFormatting"].replace(' - IMDb', '')
    def clean(self, query):
        query = query.replace(".", " ")
        while True:
            subbed = self.cleanup_regex.sub(" ", query)
            if subbed != query:
                query = subbed
                print query
            else:
                break
        query = query.strip()
        print query
        return query
    def search(self, query):
        cleaned = self.clean(query)
        logging.debug("querying with original query '%s', after cleaning '%s' " % (query, cleaned))
        self.suggest(cleaned)
        #for movie in searchMovie(cleaned):
        #    print movie

def main():
    try:
        try:
            parser = argparse.ArgumentParser(description='searches TMDB and outputs json metadata files')
            parser.add_argument('dir', nargs='*', help='directories to process; if omitted the current directory is assumed')
            args = vars(parser.parse_args())
        except argparse.ArgumentError, msg:
             raise Usage(msg)

        fetcher = MovieFetcher()
        if not args["dir"]:
            args["dir"] = ['.']
        for dir in args["dir"]:
            path = os.path.abspath(dir)
            path = path[:-1] if path.endswith('/') else path
            fetcher.search(os.path.basename(path))
    except Usage, err:
        return 2

if __name__ == "__main__":
    sys.exit(main())
