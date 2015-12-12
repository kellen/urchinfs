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
import readline
import requests
from urllib import urlencode

from tmdb3 import set_key, searchMovie, Movie
from googlesearch import GoogleSearch

logging.basicConfig(level=logging.ERROR,)

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

# per http://stackoverflow.com/questions/2533120/show-default-value-for-editing-on-python-input-possible/2533142#2533142
def prompt_with_input(prompt, prefill=''):
   readline.set_startup_hook(lambda: readline.insert_text(prefill))
   try:
      return raw_input(prompt)
   finally:
      readline.set_startup_hook()

class MovieFetcher(object):
    # from http://kodi.wiki/view/Advancedsettings.xml#cleanstrings
    # a separator or start-of-string, followed by a stopword, followed by a separator or end-of-string
    cleanup_pattern = re.compile(r"""
    (^|[ _,.()\[\]\-])(
        ac3|dts|custom|dc|divx|divx5|dsr|dsrip|dutch|dvd|dvdrip|dvdscr|dvdscreener|screener|dvdivx|cam|fragment|
        fs|hdtv|hdrip|hdtvrip|internal|limited|multisubs|ntsc|ogg|ogm|pal|pdtv|proper|repack|rerip|retail|cd[1-9]|
        r3|r5|bd5|se|svcd|swedish|german|read.nfo|nfofix|unrated|ws|telesync|ts|telecine|tc|brrip|bdrip|480p|480i|
        576p|576i|720p|720i|1080p|1080i|hrhd|hrhdtv|hddvd|bluray|x264|h264|xvid|xvidvd|xxx|www.www|
        \[.*\]  # anything enclosed in brackets
    )([ _,.()\[\]\-]|$)  # separator or end-of-string
    """, re.VERBOSE | re.IGNORECASE)

    #cleanup_pattern = re.compile(r"(^|[ _,.()\[\]\-])(ac3|dts|custom|dc|divx|divx5|dsr|dsrip|dutch|dvd|dvdrip|dvdscr|dvdscreener|screener|dvdivx|cam|fragment|fs|hdtv|hdrip|hdtvrip|internal|limited|multisubs|ntsc|ogg|ogm|pal|pdtv|proper|repack|rerip|retail|cd[1-9]|r3|r5|bd5|se|svcd|swedish|german|read.nfo|nfofix|unrated|ws|telesync|ts|telecine|tc|brrip|bdrip|480p|480i|576p|576i|720p|720i|1080p|1080i|hrhd|hrhdtv|hddvd|bluray|x264|h264|xvid|xvidvd|xxx|www.www|\[.*\])([ _,.()\[\]\-]|$)", re.IGNORECASE)
    imdb_pattern = re.compile(r"https?://(?:www\.)?imdb.com/title/(tt[0-9]+)/?$", re.IGNORECASE)

    tmdb_url = "http://api.themoviedb.org/3/"

    def __init__(self):
        self.api_key = None
        api_key_path = os.path.expanduser("~/.urchin/api_key")
        with open(api_key_path, 'r') as api_key_file:
            self.api_key = api_key_file.read().strip()
    def clean(self, query):
        query = query.replace(".", " ")
        while True:
            subbed = self.cleanup_pattern.sub(" ", query)
            if subbed == query:
                break
            query = subbed
        return query.strip()
    def search(self, query):
        for movie in searchMovie(cleaned):
            print movie
    def tmdb_from_imdb(self, id):
        params = {'api_key': self.api_key}
        r = requests.get(
            '{0}{1}?{2}'.format(
                self.tmdb_url,
                'movie/{0}'.format(id),
                urlencode(params)
            )
        )
        if r.status_code == 200:
            pprint.pprint(r.json())
            return r.json()
        return None
    def imdb_suggest(self, query):
        excludes = [
                    #"Parents Guide", "Plot Summary", "Release Info", "Quotes", "Taglines", "FAQ", "Trivia", "News",
                    #"Full Cast", "Technical Specifications", "Goofs", "Filming Locations", "User ratings",
                    #"Critic Reviews", "Company credits", "Synopsis", "External Reviews", "Soundtracks", "Recommendations"
                   ]
        google_query = ' '.join([query, ' '.join(['-"%s"' % e for e in excludes]), 'site:imdb.com/title/'])
        gs = GoogleSearch(google_query, use_proxy=False)
        suggestions = []
        for hit in gs.top_results():
            m = self.imdb_pattern.match(hit["url"])
            if m:
                suggestions.append({"id": m.group(1), "title": hit["titleNoFormatting"].replace(' - IMDb', '')})
        logging.debug("google found %d results with query: %s" % (len(suggestions), google_query))
        return suggestions
    def interact(self, path):
        query = self.clean(os.path.basename(path))
        while True:
            logging.debug("current query: %s" % query)
            imdb_suggestions = self.imdb_suggest(query)
            if not imdb_suggestions:
                try:
                    query = prompt_with_input("No suggestions found, edit query (Ctrl-C to skip): ", query)
                except KeyboardInterrupt:
                    print "skipping..."
                    return
            else:
                num_suggestions = len(imdb_suggestions)
                print "Found %d suggestions:" % num_suggestions
                for idx, suggestion in enumerate(imdb_suggestions):
                    print "  [%d] %s" % ( idx, suggestion["title"])
                choice = 0
                try:
                    while True:
                        print "Choose number or Ctrl-C to skip [0]:"
                        choice_str = raw_input()
                        if not choice_str:
                            break
                        try:
                            choice = int(choice_str)
                        except ValueError:
                            print "Choice must be a valid number."
                            continue
                        if choice < 0 or choice >= num_suggestions:
                            if num_suggestions > 0:
                                print "Choice must be between %d and %d" % (0, num_suggestions)
                            else:
                                print "You may only choose 0 or press Ctrl-C to skip"
                            continue
                        break
                except KeyboardInterrupt:
                    print "skipping..."
                    return
                chosen = imdb_suggestions[choice]
                pprint.pprint(chosen)
                #movie = Movie.fromIMDB(chosen["id"])
                movie = self.tmdb_from_imdb(chosen["id"])
                pprint.pprint(movie)
                return
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
            if os.path.isdir(path):
                fetcher.interact(path)
            else:
                logging.error("path is not a directory, ignoring: %s" % path)
    except Usage, err:
        return 2

if __name__ == "__main__":
    sys.exit(main())

# TESTS
# input is a file
# input dir is not writable
# tests for kodi regex
