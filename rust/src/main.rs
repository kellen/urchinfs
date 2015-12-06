extern crate fuse;
extern crate libc;
extern crate time;
extern crate argparse;

use std::string::String;
use std::fmt;
use std::env;
use std::path::Path;
use std::collections::{HashMap, HashSet};
use std::ffi::OsStr;

use libc::{ENOSYS,c_int,ENOENT};
use time::Timespec;
use argparse::{ArgumentParser, StoreTrue, Store};
use fuse::{FileType, FileAttr, Filesystem, Request, ReplyData, ReplyEntry, ReplyAttr, ReplyDirectory};

// FIXME these are ugly as fuck and it seems like a BAD DECISION to have these kind of macros in rust. 
// FIXME in any case, clean up our usage of these later.
// from: http://stackoverflow.com/questions/28392008/more-concise-hashmap-initialization
// auto-converts to String
macro_rules! hashmap {
    ($( $key: expr => $val: expr ),*) => {{
         let mut map = ::std::collections::HashMap::new();
         $( map.insert($key.to_string(), $val); )*
         map
    }}
}
// similar to above, jesus christ this is terrible
macro_rules! hashset {
    ($( $x: expr ),* ) => {{
            let mut set = HashSet::new();
            $( set.insert($x.to_string()); )*
            set 
    }}
}


const TTL: Timespec = Timespec { sec: 1, nsec: 0 };                 // 1 second

const CREATE_TIME: Timespec = Timespec { sec: 1381237736, nsec: 0 };    // 2013-10-08 08:56

const HELLO_DIR_ATTR: FileAttr = FileAttr {
    ino: 1,
    size: 0,
    blocks: 0,
    atime: CREATE_TIME,
    mtime: CREATE_TIME,
    ctime: CREATE_TIME,
    crtime: CREATE_TIME,
    kind: FileType::Directory,
    perm: 0o755,
    nlink: 2,
    uid: 501,
    gid: 20,
    rdev: 0,
    flags: 0,
};

const HELLO_TXT_CONTENT: &'static str = "Hello World!\n";

const HELLO_TXT_ATTR: FileAttr = FileAttr {
    ino: 2,
    size: 13,
    blocks: 1,
    atime: CREATE_TIME,
    mtime: CREATE_TIME,
    ctime: CREATE_TIME,
    crtime: CREATE_TIME,
    kind: FileType::RegularFile,
    perm: 0o644,
    nlink: 1,
    uid: 501,
    gid: 20,
    rdev: 0,
    flags: 0,
};

struct UrchinFSEntry {
    display_name: String,
    destination: String,
    metadata: HashMap<String, HashSet<String>>
}

struct UrchinFS {
    entries: Vec<UrchinFSEntry>
}

impl Filesystem for UrchinFS {
    fn lookup (&mut self, _req: &Request, parent: u64, name: &Path, reply: ReplyEntry) {
        if parent == 1 && name.to_str() == Some("hello.txt") {
            reply.entry(&TTL, &HELLO_TXT_ATTR, 0);
        } else {
            reply.error(ENOENT);
        }
    }

    fn getattr (&mut self, _req: &Request, ino: u64, reply: ReplyAttr) {
        match ino {
            1 => reply.attr(&TTL, &HELLO_DIR_ATTR),
            2 => reply.attr(&TTL, &HELLO_TXT_ATTR),
            _ => reply.error(ENOENT),
        }
    }

    fn read (&mut self, _req: &Request, ino: u64, _fh: u64, offset: u64, _size: u32, reply: ReplyData) {
        if ino == 2 {
            reply.data(&HELLO_TXT_CONTENT.as_bytes()[offset as usize..]);
        } else {
            reply.error(ENOENT);
        }
    }

    fn readdir (&mut self, _req: &Request, ino: u64, _fh: u64, offset: u64, mut reply: ReplyDirectory) {
        if ino == 1 {
            if offset == 0 {
                reply.add(1, 0, FileType::Directory, ".");
                reply.add(1, 1, FileType::Directory, "..");
                reply.add(2, 2, FileType::RegularFile, "hello.txt");
            }
            reply.ok();
        } else {
            reply.error(ENOENT);
        }
    }
}

fn main () {
    let mut mountpoint = String::new();
    let mut optstr = String::new();
    {
        let mut ap = ArgumentParser::new();
        ap.set_description("faceted-search FUSE filesystem");
        ap.refer(&mut optstr).add_option(&["-o", "--options"], Store, "comma-separated mount options");
        ap.refer(&mut mountpoint).add_argument("mountpoint", Store, "the mountpoint").required();
        ap.parse_args_or_exit();
    }

    // FIXME seems weird to have to have two variable refs
    let vec;
    let mut options : &[&OsStr] = &[];
    if optstr!= "" {
        vec = optstr.split(",").map(|s| OsStr::new(s)).collect::<Vec<_>>();
        options = &vec;
    }

    // FIMXE do this better
    let easter = UrchinFSEntry {
        display_name: "Easter Parade (1948, color)".to_string(),
        destination: "/home/kellen/test".to_string(),
        metadata: hashmap!["year" => hashset!["1948"], "color" => hashset!["color"]]
    };
    let city = UrchinFSEntry {
        display_name: "The Naked City (1948, bw)".to_string(),
        destination: "/home/kellen/test".to_string(),
        metadata: hashmap!["year" => hashset!["1948"], "color" => hashset!["black-and-white"]]
    };
    let vanish = UrchinFSEntry {
        display_name: "The Lady Vanishes (1938, bw)".to_string(),
        destination: "/home/kellen/test".to_string(),
        metadata: hashmap!["year" => hashset!["1938"], "color" => hashset!["black-and-white"]]
    };
    let kiss = UrchinFSEntry {
        display_name: "Kiss Me Deadly (1955, bw)".to_string(),
        destination: "/home/kellen/test".to_string(),
        metadata: hashmap!["year" => hashset!["1955"], "color" => hashset!["black-and-white"]]
    };

    fuse::mount(UrchinFS {entries: vec![easter, city, vanish, kiss]}, &mountpoint, options);
}
