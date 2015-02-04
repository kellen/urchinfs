import dfuse.fuse;
import std.algorithm, std.conv, std.stdio, std.string;
import std.path, std.array;
import std.datetime;
import core.sys.posix.sys.types;
import core.sys.posix.unistd;
import core.sys.posix.sys.inotify;

static const int DEBUG = false;
static const int MODE_DIR = S_IFDIR | octal!755;
static const int MODE_SYM = S_IFLNK | octal!777;
static const int W_OK = 2;
static const int DIRSIZE = 4096;

/*
 * URCHINFS(1)
 * 
 * NAME
 *      urchinfs - faceted-search FUSE filesystem
 *
 * SYNOPSIS
 *      urchinfs MOUNTPOINT -t TYPE [TYPE_OPTIONS] [-f FORMATTER]
 *
 * DESCRIPTION
 *      urchinfs presents a faceted-search-style navigation of items on the filesystem.
 *      
 *      urchinfs searches a source of type TYPE and collects key-value pairs for each item. 
 *      In MOUNTPOINT, items are displayed as symlinks, as formatted by FORMATTER. In the 
 *      special directory "^" (read: "AND") subdirectories represent keys. In a key 
 *      directory, subdirectories represent values. The contents of a value directory are
 *      the items with matching key-value pairs, the special "^" directory if there are 
 *      remaining unselected keys, and the special "+" directory (read: "OR"). In the "+"
 *      directory, subdirectories represent additional values for the last selected key.
 *
 *      Items are displayed if they have all selected keys and match at least one of the 
 *      selected values for each key.
 
 * OPTIONS
 *      -t TYPE, --type=TYPE
 *          The type of source, default DirectoryFileMetadataSource
 *      -f FORMATTER, --formatter=FORMATTER
 *          The formatter, default GenericFormatter
 *
 * TYPES
 *  DirectoryFileMetadataSource
 *      Indexes directories as items using metadata extracted from a metadata file
 *
 *      TYPE_OPTIONS: -s SOURCE [-p PATTERN | -g GLOB] [-w]
 *
 *      -s SOURCE, --source=SOURCE
 *          The source directory
 *      -g GLOB, --glob=GLOB
 *          Globbing expression, default "*.json"
 *      -p PATTERN, --pattern=PATTERN
 *          Regular expression.
 *      -e EXTRACTOR, --extractor=EXTRACTOR
 *          The extractor to apply, default JsonExtractor
 *      -w, --watch
 *          Watch for changes in the filesystem
 *
 * FORMATTING
 *  GenericFormatter
 *      Returns the original item name, disambiguated if necessary
 *
 * ENVIRONMENT VARIABLES
 * EXAMPLES
 *
 *  FIXME -> multiple sources
 *
 * PLUGINS
 *
 * EXIT STATUS
 * COPYRIGHT
 * BUGS
 * SEE ALSO
 * NOTES
 */

// class for command line options
class Option {
    string option;
    string value;
}

interface Type { 
    // return the name of this source type
    string name();
    // FIXME this needs to return UrchinFSEntries(?)
    // given a set of command line options, return the metadata
    string[][string] init(immutable Option[]);
}

interface Formatter { 
    // given a set of metadata, return a displayable name
    string format(immutable string[][string] metadata);
}

interface UrchinFSEntry {
    // the display name of this item
    string display_name();
    // the destination on the filesystem to which symlinks should point
    string destination();
    // the metadata for this item
    string[][string] metadata();
}

class UrchinFSEntry {
    string display_name = null;
    string destination = "/";
    string[] metadata_sources = [];
    string[][string] metadata;
}

class UrchinFSResult {
    string name = null;
    int mode = 0;
    int size = 0;
    string destination = null;

    this(string name) immutable {
        this.name = name;
        this.mode = MODE_DIR;
        this.size = DIRSIZE;
    }

    this(string name, string destination) immutable {
        this.name = name;
        this.destination = destination;
        this.mode = MODE_SYM;
        // "The size of a symbolic link is the length of the 
        // pathname it contains, without a terminating null byte."
        this.size = to!int(name.length);
    }
}

class UrchinFS : Operations {

    static const string AND = "^";
    static const string OR = "+";

    static immutable UrchinFSResult AND_DIR = new immutable UrchinFSResult("^");
    static immutable UrchinFSResult OR_DIR = new immutable UrchinFSResult("+");

    static immutable UrchinFSResult CUR_DIR = new immutable UrchinFSResult(".");
    static immutable UrchinFSResult CUR_SYM = new immutable UrchinFSResult(".", "/");

    enum parsed { KEY, VAL, AND, OR, NONE, DIR }

    // { metadata_key -> { metadata_value -> { display_name -> bool } }}
    // the last nested map is a hack due to no set type in dlang

    UrchinFSEntry[] entries;
    time_t mount_time = 0;
    uid_t mount_uid;
    gid_t mount_gid;

    override void initialize() {
        mount_time = Clock.currTime().toUnixTime();
        mount_gid = getgid(); 
        mount_uid = getuid();
    }

    this() {
        // TODO fetch actual data from disk
        UrchinFSEntry easter = new UrchinFSEntry();
        easter.display_name = "Easter Parade (1948, color)";
        string[][string] easter_md;
        easter_md["year"] = ["1948"];
        easter_md["color"] = ["color"];
        easter.metadata = easter_md;
        entries ~= easter;

        UrchinFSEntry city = new UrchinFSEntry();
        city.display_name = "The Naked City (1948, bw)";
        string[][string] city_md;
        city_md["year"] = ["1948"];
        city_md["color"] = ["black-and-white"];
        city.metadata = city_md;
        entries ~= city;

        UrchinFSEntry vanish = new UrchinFSEntry();
        vanish.display_name = "The Lady Vanishes (1938, bw)";
        string[][string] vanish_md;
        vanish_md["year"] = ["1938"];
        vanish_md["color"] = ["black-and-white"];
        vanish.metadata = vanish_md;
        entries ~= vanish;

        UrchinFSEntry kiss = new UrchinFSEntry();
        kiss.display_name = "Kiss Me Deadly (1955, bw)";
        string[][string] kiss_md;
        kiss_md["year"] = ["1955"];
        kiss_md["color"] = ["black-and-white"];
        kiss.metadata = kiss_md;
        entries ~= kiss;
    }

    void log(string, A...)(string msg, A args) {
        if(DEBUG) {
            stdout.writefln(msg, args);
        }
    }

    void error(string, A...)(string msg, A args) {
        if(DEBUG) {
            stderr.writefln(msg, args);
        }
    }

    // get all of the valid keys for the given entries
    string[] get_keys(UrchinFSEntry[] entries) {
        bool[string] keys;
        foreach(entry; entries) {
            foreach(string key, string[] v; entry.metadata) {
                keys[key] = true;
            }
        }
        return keys.keys;
    }

    // get all of the values specified for key in entries
    string[] get_values(UrchinFSEntry[] entries, string key) {
        bool[string] values;
        foreach(entry; entries) {
            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                string[] key_values = *key_values_ptr;
                foreach(val; key_values) {
                    values[val] = true;
                }
            }
        }
        return values.keys;
    }

    // get all of the display names for the given entries
    immutable(UrchinFSResult)[] get_listing(UrchinFSEntry[] entries) {
        immutable(UrchinFSResult)[] result;
        foreach(entry; entries) {
            result ~= new immutable UrchinFSResult(entry.display_name, entry.destination);
        }
        return result;
    }

    // get all the listings from the given result
    string[] get_listing(immutable(UrchinFSResult)[] results) {
        string[] listing;
        foreach(result; results) {
            listing ~= result.name;
        }
        return listing;
    }

    // fitler the entries which have the given key
    UrchinFSEntry[] filter(UrchinFSEntry[] entries, string key) {
        UrchinFSEntry[] result;
        foreach(i, entry; entries) {
            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                result ~= entry;
            }
        }
        return result;
    }

    // filter the entries by the given key and values
    // if an entry has the key and has one of the values, it is retained
    UrchinFSEntry[] filter(UrchinFSEntry[] entries, string key, string[] values) {
        UrchinFSEntry[] result;
        foreach(i, entry; entries) {
            bool keep = false;

            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                string[] key_values = *key_values_ptr;
                foreach(j, val; key_values) {
                    foreach(value; values) {
                        if(val == value) {
                            keep = true;
                            break;
                        }
                    }
                    if(keep) {
                        break;
                    }
                }
            }

            if(keep) {
                result ~= entry;
            }
        }
        return result;
    }

    // set difference
    string[] setdiff(string[] set, string[] minus) {
        // clear way to do this
        bool[string] map;
        foreach(val; set) {
            map[val] = true;
        }
        foreach(val; minus) {
            map.remove(val);
        }
        return map.keys;
    }

    immutable(UrchinFSResult)[] to_result(string[] listing) {
        immutable(UrchinFSResult)[] result;
        foreach(entry; listing) {
            result ~= new immutable UrchinFSResult(entry);
        }
        return result;
    }

    immutable(UrchinFSResult) get_cur(immutable(UrchinFSResult)[] results) {
        foreach(result; results) {
            if(result.name == ".") {
                return result;
            }
        }
        return null;
    }

    // for a split path parts, find the entries matching the specified key-value combinations
    // and return the appropriate directory listing
    immutable(UrchinFSResult)[] get_results(const(char)[][] parts) {
        // strip off any empty leading sections of the path
        int cur = 0;
        while(cur < parts.length && parts[cur].empty) {
            cur++;
        }
        parts = parts[cur..parts.length];

        // start with all entries
        // the entire set of entires must be walked for each query in order to accurately 
        // determine if a directory does or does not exist.
        // FIXME we may wish to reimplement this walking functionality for getattr so 
        // FIXME we're not temporarily creating a big array of objects only to throw most
        // FIXME of them away when looking for "."
        UrchinFSEntry[] found = entries.dup;

        // root dir
        if(parts.length == 0) {
            return get_listing(found) ~ AND_DIR ~ CUR_DIR;
        }

        string[] current_valid_keys = get_keys(found);  // the valid keys for the current entries
        string[] current_valid_values = [];             // the valid values for the current entires + key
        string current_key = null;                      // the currently selected key

        // FIXME see if state can be simplified/ignored
        // FIXME see if we can cache anything
        string[][string] state;
        parsed last = parsed.NONE;

        int index = 0;
        while(index < parts.length) {
            bool is_last = index == parts.length-1;
            string part = to!string(parts[index]);

            if(part == AND) {
                last = parsed.AND;
                current_key = null;
                current_valid_values = [];

                current_valid_keys = setdiff(get_keys(found), state.keys);
                if(is_last) {
                    return to_result(current_valid_keys) ~ CUR_DIR;
                }
            } else if (last == parsed.AND) {
                last = parsed.KEY;
                string key = part;

                // fail on invalid keys 
                if(!current_valid_keys.canFind(key)) {
                    error("Invalid key [%s]", key);
                    throw new FuseException(errno.ENOENT);
                }
                // fail on duplicate keys
                if((key in state) !is null) {
                    error("Duplicate key [%s]", key);
                    throw new FuseException(errno.ENOENT);
                }

                current_key = key;
                current_valid_keys = setdiff(current_valid_keys, [key]);
                state[key] = [];
                found = filter(found, key);

                current_valid_values = get_values(found, key);
                if(is_last) {
                    return to_result(current_valid_values) ~ CUR_DIR;
                }
            } else if (last == parsed.VAL && part == OR) {
                last = parsed.OR;
                if(is_last) {
                    return to_result(current_valid_values) ~ CUR_DIR;
                }
            } else if(last == parsed.KEY || last == parsed.OR) {
                last = parsed.VAL;
                string value = part;

                // fail on not found or already-used values
                if(!current_valid_values.canFind(value)) {
                    error("Invalid value [%s]", value);
                    throw new FuseException(errno.ENOENT);
                }

                // update the currently-valid values list
                current_valid_values = setdiff(current_valid_values, [value]);

                // append a new array to values, containing the current value
                state[current_key] = state[current_key] ~ value;

                // lookahead, and if the next token is _not_ an OR,
                // filter the entries by the current facet
                if(is_last || (!is_last && to!string(parts[index+1]) != OR)) {
                    found = filter(found, current_key, state[current_key]);
                } 

                if(is_last) {
                    immutable(UrchinFSResult)[] ret = get_listing(found);
                    // add AND and OR if appropriate
                    if(current_valid_values.length > 0) {
                        ret ~= OR_DIR;
                    }
                    if(current_valid_keys.length > 0) {
                        ret ~= AND_DIR;
                    }
                    return ret ~ CUR_DIR;
                }
            } else {
                last = parsed.DIR;
                // a "normal directory", i.e. something somewhere else on disk
                // if this isn't the last component in the path, error out
                if(is_last) {
                    // check that the specified dir actually exists
                    string value = part;
                    if(!current_valid_values.canFind(value)) {
                        error("Invalid value [%s]", value);
                        throw new FuseException(errno.ENOENT);
                    }
                    // no contents to return; just return a symlink for "."
                    immutable(UrchinFSResult)[] ret;
                    ret ~= CUR_SYM;
                    return ret;
                }
            }
            index++;
            log("state: %-(%s -> %s%)", state);
        }
        throw new FuseException(errno.ENOENT);
    }

    override void getattr(const(char)[] path, ref stat_t s) {
        log("getattr: %s", path);
        immutable(UrchinFSResult)[] results = get_results(path.split("/"));
        immutable(UrchinFSResult) result = get_cur(results);
        if(null !is result) {
            s.st_mode = result.mode;
            s.st_size = result.size;
            s.st_nlink = 2 + (results.length - 1);  // 2 + number of dirs - 1 "." entry

            s.st_gid = mount_gid;
            s.st_uid = mount_uid;

            s.st_atime = mount_time;
            s.st_mtime = mount_time;
            s.st_ctime = mount_time;

            // supposedly ignored
            s.st_ino = 0;
            s.st_dev = 0;

            log("\t-> OK: {mode: %o, size: %d}", result.mode, result.size);
            return;
        }
        log("\t-> ERROR: %d", errno.ENOENT);
        throw new FuseException(errno.ENOENT);
    }

    override string[] readdir(const(char)[] path) {
        log("readdir: %s", path);
        return get_listing(get_results(path.split("/")));
    }

    override ulong readlink(const(char)[] path, ubyte[] buf) {
        log("readlink: %s", path);
        immutable(UrchinFSResult) result = get_cur(get_results(path.split("/")));
        if(null !is result) {
            ubyte[] dest = cast(ubyte[])result.destination;
            for (int i = 0; i < dest.length; i++) {
                buf[i] = dest[i];
            }
            return (cast(ubyte[])result.destination).length;
        }
        error("readlink ERROR no result");
        throw new FuseException(errno.ENOENT);
    }

    override bool access(const(char)[] path, int mode) {
        log("access: %s (mode %s)", path, mode);
        immutable(UrchinFSResult) result = get_cur(get_results(path.split("/")));
        if(null !is result) {
            log(
                    "\t-> result:{name:%s, mode:%o, size:%d, destination:%s}", 
                    result.name, result.mode, result.size, result.destination
               );
            log("\t-> write? %b", (mode & W_OK) == W_OK);
            if((mode & W_OK) == W_OK) {
                // write not supported
                error("access ERROR wants to write");
                throw new FuseException(errno.EACCES);
            }
            log("\t-> return: true");
            return true;
        }
        error("access ERROR no result");
        throw new FuseException(errno.ENOENT);
    }

}

int main(string[] args) {
    if (args.length != 2) {
        stderr.writeln("urchinfs <MOUNTPOINT>");
        return -1;
    }
    if(DEBUG) {
        stdout.writeln("mounting urchinfs");
    }

    auto fs = new Fuse("UrchinFS", true, false);
    fs.mount(new UrchinFS(), args[1], []);

    return 0;
}
