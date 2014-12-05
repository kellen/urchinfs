import dfuse.fuse;
import std.algorithm, std.conv, std.stdio, std.string;
import std.path;

class UrchinFS : Operations {

    // { metadata_key -> { metadata_value -> { display_name -> bool } }}
    // the last nested map is a hack due to no set type in dlang

    bool[string][string][string] metadata_cache;

    this() {
        // TODO fetch actual data from disk
        bool[string] year_dirs_48;
        year_dirs_48["Easter Parade"] = true;
        year_dirs_48["Force of Evil"] = true;

        bool[string] year_dirs_12;
        year_dirs_12["Skyfall"] = true;
        year_dirs_12["Rust and Bone"] = true;

        bool[string][string] years;
        years["1948"] = year_dirs_48;
        years["2012"] = year_dirs_12;

        metadata_cache["year"] = years;
    }

    string[] parse_pair(const(char)[][] parts, string[] so_far) {
        if(parts.length == 0) {
            return so_far;
        }

        bool[string][string] vals = (parts[0] in metadata_cache);
        if(vals !is null) {
            if(parts.length > 1) {
                bool[string] dirs = (parts[1] in vals);
                if(dirs !is null) {
                    




                    return from_parts(parts[1..parts.length], so_far);
                }
                throw new FuseException(errno.ENOENT);

            } 
            return vals.keys;
        }
        throw new FuseException(errno.ENOENT);
    }


    override void getattr(const(char)[] path, ref stat_t s) {
        if (path == "/") {
            s.st_mode = S_IFDIR | octal!755;
            s.st_size = 0;
            return;
        }
        if (path.among("/a", "/b")) {
            s.st_mode = S_IFREG | octal!644;
            s.st_size = 42;
            return;
        }
        throw new FuseException(errno.ENOENT);
    }

    override string[] readdir(const(char)[] path) {
        // FIXME: check if this can actually ever be null?
        if (null != path) {
            if(isValidPath(path)) {
                const(char)[][] parts = path.split("/");
                writeln("parts:");
                writeln(parts);
                if("" == parts[0]) {
                    parts = parts[1..parts.length];
                    if (path == "/") {
                        return metadata_cache.keys;
                        //return ["a", "b"];
                    }
                } else {
                    writeln("WAT");
                }
            }
        }
        throw new FuseException(errno.ENOENT);
    }
}

int main(string[] args) {
    if (args.length != 2) {
        stderr.writeln("urchinfs <MOUNTPOINT>");
        return -1;
    }
    stdout.writeln("mounting urchinfs");

    auto fs = new Fuse("UrchinFS", true, false);
    fs.mount(new UrchinFS(), args[1], []);

    return 0;
}
