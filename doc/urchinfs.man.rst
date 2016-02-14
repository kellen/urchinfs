.. role:: ref(emphasis)

========
urchinfs
========

faceted-search FUSE filesystem
------------------------------

:Manual section: 8

SYNOPSIS
========

urchinfs [mountpoint] [-o option[,option]...]

DESCRIPTION
===========

`urchinfs` presents a faceted-search-style navigation of items on the filesystem.

`urchinfs` supports filtering on multiple facets, where the result is entries 
which match all given facets. Facets are nested in a **^** directory, where **^** is 
the symbol for the `AND <http://en.wikipedia.org/wiki/Logical_conjunction>`_ operation.

Each facet can be specified with multiple values, where the results
have one of these values. Values are nested in a **+** directory,
where **+** is the symbol for the 
`OR <http://en.wikipedia.org/wiki/Logical_disjunction>`_ operation.

OPERATION
=========

`urchinfs` operates on a configurable pipeline of **components** which indexes items
and produces a map of metadata values and one or more names to use for the item.
The pipeline looks like this:

source directory ->
**indexer** -> items -> 
**matcher** -> metadata-sources-for-item ->
**extractor** -> metadata-collections-for-item ->
**merger** -> combined-metadata-for-item ->
**munger** -> final-metadata-for-item ->
**formatter** -> formatted-names-for-item

An entire component pipeline can alternatively be configured via a **plugin** class.

See the **COMPONENTS** section for an extended description.

OPTIONS
=======

See :ref:`fuse(8)` for complete fuse-related options.

-h, --help
    Display help text and exit.

-o opts
    Use the specified mount options. The opts argument is a comma-separated list.
    See **EXAMPLES** for an example invocation and the **MOUNT OPTIONS** section 
    for options details.

--version
    Display the version number and exit.
 
MOUNT OPTIONS
=============

source
    the source directory to index, required.
plugin
    the short name for the plugin class. If set, all component options are ignored.
refresh
    time before doing a full refresh, in seconds. 0 (default) will not refresh.
COMPONENTS
    indexer
        the short name for the indexer class, required if no plugin is specified.

    matcher
        the short name for the matcher class, default: "default".

    extractor
        the short name for the extractor class, required if no plugin is specified.

    merger
        the short name for the merger class, default: "default".

    munger
        the short name for the munger class, default: "default".

    formatter
        the short name for the formatter class, default: "default".

BUILT-INS
=========

COMPONENTS
    INDEXER
        json
            Indexes directories which contain json files
        mp3
            Indexes directories which contain mp3 files
        mp3-file
            Indexes mp3 files
    MATCHER
        default
            Matches the item path
        json
            Matches json files contained in the item directory 
        mp3
            Matches mp3 files contained in the item directory
    EXTRACTOR
        json-basic
            Parses a json file and returns the untouched json object
        json
            Parses a json file and converts non-string keys and values to strings if 
            the conversion is straightforward. Values in the source must be are single 
            values or lists of single values, otherwise they are ignored. 
        mp3
            Extracts the metadata contained in the id3 tag
    MERGER
        default
            Merges metadata maps while attempting to do as little as possible.
            Values for duplicate keys are merged into lists, unless the values
            are themselves tuples, sets, or lists, in which case the values are combined.
        mp3
            Merges metadata for an entire directory, assumed to be an album.
            Drops some metadata irrelevant to an album, e.g. track number
            Sets a fallback "????" for unknown values required by the `mp3` formatter.
            Sets "compilation" and "split" metadata.
    MUNGER
        default
            Does nothing
        tmdb
            Extracts some specified values from data from TheMovieDB; used in the **tmdb** plugin
    FORMATTER
        default
            Returns the basename for the item path
        mp3
            Formats as: "artist - date - album" for typical albums.
            Uses "Compilation" instead of artist when the "compilation" metadata is set.
            For splits, defined as albums with exactly two artists, produces two entries:
            "artist1 - date - with artist2 - album" and "artist2 - date - with artist1 - album"
        tmdb
            Formats as: "title (alternative-title) (director, year)", falls back on
            the item path if no title exists.
PLUGINS
    tmdb
        Same as: indexer: json, matcher: json, extractor: json-basic,
        merger: default, munger: tmdb, formatter: tmdb
    mp3
        Same as: indexer: mp3, matcher: mp3, extractor: mp3,
        merger: mp3, munger: default, formatter: mp3

COMPONENTS
==========

`urchinfs` searches the directory specified by *source* and indexes items (files, 
directories) matched by the *indexer*. Each item is passed to the *matcher* which
matches one or more metadata sources for the item. The *extractor* then extracts 
metadata from each metadata source in format-specific manner. If there is more
than one metadata source, the *merger* combines the extracted metadata into a single
object. Finally, the *munger* may additionally manipulate the metadata. An indexed
item is presented with one or more names as produced by the *formatter* component.

The different components allow for a flexible pipeline which can support varying
metadata sources an use-cases.

`urchinfs` provides some predefined components, including one for data fetched from
TheMovieDB (TMDB), which we'll use to describe the components named above.

Using the `urchin` command, we download metadata for the 1948 Jules Dassin film
"The Naked City". TMDB provides metadata in several separate files, `urchin` fetches
two of these: *movie.json* and *credits.json*. It will be easier for us to update 
metadata as well as integrate with other tools if retain the original formats. 

When indexing movies, we'll choose to index the directory, which can contain the actual
movie file or files, cover scans, sample files, etc. rather than single video files.
To do this, the *json* indexer will be used; it matches any directory which contains
json files. The metadata comes from the two json files; the *json* matcher will match 
all json files in a directory.

Next, each of the json files are parsed using the *json-basic* extractor. This extractor
only opens and parses the json file; other extractors may attempt to do more, for example
only returning certain keys or converting numeric argumets to strings.

The parsed json objects are merged by the *default* merger component, which tries to
combine the two metadata objects while altering them as little as possible. The merged
metadata is then passed to the *tmdb* munger, which is specialized for the TMDB metadata
format: it reduces the parsed metadata to only a few key-value pairs. This functionality
could also have been integrated into a specialized *extractor*.

Finally, the merged-and-munged metadata is passed to the *tmdb* formatter, which produces
a single name for the entry: "The Naked City (Jules Dassin, 1948)". Though we don't do it
here, one can imagine a formatter which might produce two entries: "The Naked City" and
"Naked City, The".

EXAMPLES
========

From the command line::

   urchinfs /mountpoint -o source=/srv/source,indexer=json,matcher=json,extractor=json,merger=default,munger=tmdb,formatter=default,refresh=300

To produce the same mount in `/etc/fstab`::

    urchinfs /mountpoint fuse source=/srv/source,indexer=json,matcher=json,extractor=json,merger=default,munger=tmdb,formatter=default,refresh=300 0 0

If using a plugin, these can be shortened::

   urchinfs /mountpoint -o source=/srv/source,plugin=tmdb,refresh=300

And in `/etc/fstab`::

    urchinfs /mountpoint fuse source=/srv/source,plugin=tmdb,refresh=300 0 0

PLUGINS
=======

Plugins can be placed in subdirectories of `~/.urchin/plugins/` and exposed in
an **__init__.py** file. For example, an **imdb** plugin would be located in
**~/.urchin/plugins/imdb/__init__.py**.

Plugins may provide complete pipelines by inheriting from the `urchin.fs.plugin.Plugin` 
class, or provide single components by inheriting from one of: `Indexer`, `MetadataMatcher`, 
`MetadataExtractor`, `MetadataMerger`, `MetadataMunger`, or `Formatter`.

Each plugin or component must have an attribute **name** which specifies the short
name used on the command line, for example in `indexer=json`, **json** is the short
name.

Plugins and components are detected automatically and can then be invoked by their
short names from the command line or via `/etc/fstab`.

SEE ALSO
========

* :ref:`fuse(8)`
* :ref:`urchin-tmdb(1)`

AUTHORS
=======

Kellen Dye <kellen@cretin.net>

COPYRIGHT
=========

public domain

NOTES
=====

git repository: https://github.com/kellen/urchinfs

issues: https://github.com/kellen/urchinfs/issues 
