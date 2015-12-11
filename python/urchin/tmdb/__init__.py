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

logging.basicConfig(level=logging.DEBUG,)

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

class SearchError(Exception):
    def __init__(self, msg):
        self.msg = msg

class Google(object):
    """Basically the same as googlesearch.GoogleSearch, but uses mozilla-like headers"""
    URL_TEMPLATE = 'http://ajax.googleapis.com/ajax/services/search/web?v=1.0&%s'
    HEADERS = {
            #'User-Agent': "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:42.0) Gecko/20100101 Firefox/42.0",
            #'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            #'Accept-Language': "en-US,en;q=0.5",
            #'Accept-Encoding': "gzip, deflate"
            #'DNT': "1"
            #'Connection': "keep-alive"
            #'Cache-Control': "max-age=0"
            }
    def __init__(self, query):
        self.query = query
        self._encoded_query = urllib.urlencode({'q': self.query})
        self._results = None
    @property
    def results(self):
        if self._results is None:
            self._results = self.search()
        return self._results
    def search(self):
        url = self.URL_TEMPLATE % self._encoded_query
        response = requests.get(url) #, headers = self.HEADERS)
        json = response.json()
        results = json["responseData"]
        status = json['responseStatus']
        # details = json['responseDetails']
        if status != 200:
            logging.debug("error while searching google, status %s" % status)
            raise SearchError(details)
        return results
    def hits(self):
        return self.results["results"]

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
        gs = Google(google_query)
        for hit in gs.hits():
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
