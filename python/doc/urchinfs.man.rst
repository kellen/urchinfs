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

::

    $ ls -1 example/
    ^
    Easter Parade (1948, color)
    Kiss Me Deadly (1955, bw)
    The Lady Vanishes (1938, bw)
    The Naked City (1948, bw)

    $ ls -1 example/^/
    color
    year

    $ ls -1 example/^/year/1948/
    ^
    +
    Easter Parade (1948, color)
    The Naked City (1948, bw)

    $ ls -1 example/^/year/1948/^/color/bw/
    ^
    +
    Easter Parade (1948, color)
    The Naked City (1948, bw)

Each facet can be specified with multiple values, where the results
have one of these values. Values are nested in a **+** directory,
where **+** is the symbol for the 
`OR <http://en.wikipedia.org/wiki/Logical_disjunction>`_ operation.

::

    $ ls -1 example/
    ^
    Easter Parade (1948, color)
    Kiss Me Deadly (1955, bw)
    The Lady Vanishes (1938, bw)
    The Naked City (1948, bw)

    $ ls -1 example/^/year/
    1938
    1948
    1955

    $ ls -1 example/^/year/1948/
    ^
    +
    Easter Parade (1948, color)
    The Naked City (1948, bw)

    $ ls -1 example/^/year/1948/+/1955/
    ^
    +
    Easter Parade (1948, color)
    Kiss Me Deadly (1955, bw)
    The Naked City (1948, bw)

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
    the source directory to index

indexer
    the short name for the indexer class

matcher
    the short name for the matcher class

extractor
    the short name for the extractor class

merger
    the short name for the merger class

munger
    the short name for the munger class

formatter
    the short name for the formatter class

plugin
    the short name for the plugin class

watch
    if set, watches the source directory for changes via inotify

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

   urchinfs /mountpoint -o source=/srv/source,indexer=json,matcher=json,extractor=json,merger=default,munger=tmdb,formatter=default,watch=true

To produce the same mount in `/etc/fstab`::

    urchinfs /mountpoint fuse source=/srv/source,indexer=json,matcher=json,extractor=json,merger=default,munger=tmdb,formatter=default,watch=true 0 0 

If using a plugin, these can be shortened::

   urchinfs /mountpoint -o source=/srv/source,plugin=tmdb,watch=true

And in `/etc/fstab`::

    urchinfs /mountpoint fuse source=/srv/source,plugin=tmdb,watch=true 0 0 

PLUGINS
=======

Plugins can be placed in subdirectories of `~/.urchin/plugins/` and exposed in
an **__init__.py** file. For example, an **imdb** plugin would be located in
**~/.urchin/plugins/imdb/__init__.py**.

Plugins may provide complete pipelines by inheriting from the `urchin.fs.plugin.Plugin` 
class, or provide single components by inheriting from one of: `Indexer`, `MetadataMatcher`, 
`MetadataExtractor`, `MetadataMunger`, `MetadataMerger`, or `Formatter`.

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
