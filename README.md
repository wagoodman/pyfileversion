## FileVersioner
A simple module to see if any source files have changed since a last
known run.

Potential use cases are:

* You're in production and want to check if there are any patches that
have been applied (and need to be reapplied) before performing a fresh install. 

* You've handed out various copies of a set of python scripts 
to folks and they are saying that "it's not working anymore!"...
Run this to check which lines of code have been changed without 
needing to drop a copy of the original and run `diff` against it.

* You want your application to check itself for modifications on application startup.

*Note*: This is not intended to protect against malicious tampering, only accidental modifications.

### Usage
Use it to show changes to your script source files. If anything has been modified, show the changed line number for each file and exit:
``` python
import fileVersion

listOfFiles = [ "src.py", "deps.py", "main.py" ]

with fileVersion.VersionManager(".version.json", listOfFiles) as mgr:
    if mgr.hasVersionChanged():
        print("This application has been modified!")
        mgr.versionReport()
        sys.exit()
    else:
        print("Version %s" % mgr.getVersion())

# Go on executing your script as normal...
```

This could show output similar to:
```
This application has been modified!

[unchanged]          src.py
[unchanged]          deps.py
[modified]           main.py
   Modified Lines: [12]
   Missing Lines:  [4, 8, 14]

Version: b3c0cc79c84a3911507754785b3c3f3c
```

Or if you just want output similar to `md5sum` you can do:
``` python
import fileVersion

listOfFiles = [ "src.py", "deps.py", "main.py" ]

with fileVersion.VersionManager(".version.json", listOfFiles) as mgr:
    print(mgr.getFileVersions())
```

This could show output similar to:
```
1da0f46abcbd91e75123e5e630d0dfd5  src.py
6821bc5a92851b0afde3bce96b58121d  deps.py
f985a3eb24d6fffe902243d1f038b11c  main.py
```

The `VersionManager` class takes an optional `hashAlgorithm` parameter (default is `md5`, the fastest is tied between `mmh3` and `xxh64`). The supported algorithms are:

**From `hashlib`**
* SHA1
* SHA224
* SHA
* SHA384
* ecdsa-with-SHA1
* SHA256
* SHA512
* md4
* md5
* sha1
* dsaWithSHA
* DSA-SHA
* sha224
* dsaEncryption
* DSA
* ripemd160
* sha
* MD5
* MD4
* sha384
* sha256
* sha512
* RIPEMD160
* whirlpool

**From `xxhash`** (`pip install xxhash`)
* xxh32
* xxh64

**From `mmh3`** (`pip install mmh3`)
* mmh3

**From `pyhash`** (`pip install pyhash`... needs a few other depencencies too)
* city_128
* city_64
* fnv1_32
* fnv1_64
* fnv1a_32
* fnv1a_64
* logging
* lookup3
* lookup3_big
* lookup3_little
* murmur1_32
* murmur1_aligned_32
* murmur2_32
* murmur2_aligned_32
* murmur2_neutral_32
* murmur2_x64_64a
* murmur2_x86_64b
* murmur2a_32
* murmur3_32
* murmur3_x64_128
* murmur3_x86_128
* spooky_128
* spooky_32
* spooky_64
* super_fast_hash