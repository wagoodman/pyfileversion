"""
Example Usage:
   - Patch preventor at runtime
   - Patch detector (and determines the lines changed)
   - Aware of modifications and change execution
"""
from __future__ import print_function
import mmap
import collections
import hashlib
import json
import os
from functools import partial


_PYHASH_ALGORITHMS = ['city_128', 'city_64', 'fnv1_32', 'fnv1_64', 'fnv1a_32', 'fnv1a_64', 'logging', 'lookup3', 'lookup3_big', 'lookup3_little', 'murmur1_32', 'murmur1_aligned_32', 'murmur2_32', 'murmur2_aligned_32', 'murmur2_neutral_32', 'murmur2_x64_64a', 'murmur2_x86_64b', 'murmur2a_32', 'murmur3_32', 'murmur3_x64_128', 'murmur3_x86_128', 'spooky_128', 'spooky_32', 'spooky_64', 'super_fast_hash']
_XXHASH_ALGORITHMS = ['xxh32', 'xxh64']
_HASHLIB_ALGORITHMS = list(hashlib.algorithms_available)
_WRAPPED_ALGORITHMS = _PYHASH_ALGORITHMS + ["mmh3"]
ALGORITHMS = _PYHASH_ALGORITHMS + _XXHASH_ALGORITHMS + _HASHLIB_ALGORITHMS + ["mmh3"]

_HASHOBJ = None

class HashWrapper(object):
   def __init__(self, hashObj):
      self.hashObj = hashObj
      self.soFar = []

   def update(self, payload):
      self.soFar.append(payload)
   
   def hexdigest(self):
      return hex(self.hashObj("".join(self.soFar)))[2:-1]

class HashObject(object):

   def __init__(self, algorithm):
      self.algorithm = algorithm
      if algorithm in _HASHLIB_ALGORITHMS:
         self.hashObj = eval("hashlib.%s" % algorithm)
         self.newEntrypoint = partial(hashlib.new, algorithm)
      elif algorithm in _XXHASH_ALGORITHMS:
         import xxhash
         self.hashObj = xxhash.xxh64
         self.newEntrypoint = xxhash.xxh64
      elif algorithm == "mmh3":
         import mmh3
         self.hashObj = mmh3.hash
         self.newEntrypoint = partial(HashWrapper, self.hashObj)
      elif algorithm in _PYHASH_ALGORITHMS:
         import pyhash
         self.hashObj = eval("pyhash.%s()" % algorithm)
         self.newEntrypoint = partial(HashWrapper, self.hashObj)
      else:
         raise RuntimeError("Could not find hash algorithm %s" % repr(algorithm))
         

   def new(self):
      return self.newEntrypoint()

   def hash(self, payload):
      if self.algorithm in _WRAPPED_ALGORITHMS:
         return hex(self.hashObj(payload))[2:-1]
      return self.hashObj(payload).hexdigest()


class FileVersion(object):

   def __init__(self, filePath, version=None, lineHash=None, hashAlgorithm=None, processLineCallback=None):
      self.hashAlgorithm = hashAlgorithm
      self.filePath = filePath
      self.version = version
      # {hash : lineno}
      # Using the dict.keys() view to detect content differences (^) and then
      # the affected line numbers will be listed.
      self.lineHash = lineHash if lineHash else {}
      self.processLineCallback = processLineCallback

   def normalize(self):
      return {"filePath": self.filePath, 
              "version": self.version, 
              "lineHash": self.lineHash}

   def build(self):
      fileHashObj = _HASHOBJ.new()
      with open(self.filePath, 'r') as inFile: 
         lineno = 1
         for line in inFile:
            line = line.encode('utf-8')
            fileHashObj.update(line)
            self._processLine(line, lineno)
            lineno += 1
      self.version = fileHashObj.hexdigest()

   def _processLine(self, line, lineno):
      theHash = _HASHOBJ.hash(line)
      self.lineHash[theHash] = lineno
      if self.processLineCallback:
         self.processLineCallback(line)


class VersionTable(object):

   def __init__(self, fileList, hashAlgorithm):
      self.fileList = sorted(fileList)
      self.hashAlgorithm = hashAlgorithm
      self.fileVersions = None
      self.version = None

   def read(self, obj):
      self.hashAlgorithm = obj["hashAlgorithm"]
      self.fileList = obj["fileList"]
      self.version = obj["version"]
      self.fileVersions = {}

      for filePath, normalizedObj in obj["files"].items():
         if os.path.exists(filePath):
            self.fileVersions[filePath] = FileVersion(normalizedObj["filePath"], 
                                                      normalizedObj["version"], 
                                                      normalizedObj["lineHash"], 
                                                      self.hashAlgorithm)

   def build(self):
      self.hashObj = _HASHOBJ.new()
      self.fileVersions = {}
      for filePath in self.fileList:
         if os.path.exists(filePath):
            fileObj = FileVersion(filePath, 
                                  hashAlgorithm=self.hashAlgorithm, 
                                  processLineCallback=self._processLine)
            fileObj.build()
            self.fileVersions[filePath] = fileObj
      self.version = self.hashObj.hexdigest()

   def _processLine(self, line):
      self.hashObj.update(line)

   def normalize(self):
      versionTables = {}
      for fileName, versionObj in self.fileVersions.items():
         versionTables[fileName] = versionObj.normalize()

      return {"version": self.version, 
              "hashAlgorithm": self.hashAlgorithm,
              "fileList": self.fileList,
              "files": versionTables}



class VersionManager(object):

   def __init__(self, revisionFileName, fileList, hashAlgorithm='md5', write=False):
      global _HASHOBJ
      _HASHOBJ = HashObject(hashAlgorithm)

      self.revisionFileName = revisionFileName
      self.curVersions = VersionTable(fileList, hashAlgorithm)
      self.build = self.curVersions.build
      self.lastVersions = VersionTable([], hashAlgorithm)
      self.doWrite = write
      self.diffs = None # {filepath: diffLinesObj }
      
   def read(self):
      if not os.path.exists(self.revisionFileName):
         return {} 

      with open(self.revisionFileName, 'r') as fh:
         revisionInfo = json.load(fh)

      self.lastVersions.read(revisionInfo)

   def write(self):
      if self.curVersions.version is None:
         self.curVersions.build()

      obj = self.curVersions.normalize()
      with open(self.revisionFileName, 'w') as fh:
         json.dump(obj, fh)

   def compare(self):
      if not all( (self.curVersions, self.lastVersions) ) :
         raise RuntimeError("Must call read() and build() to compare versions.")

      if self.curVersions.hashAlgorithm != self.lastVersions.hashAlgorithm:
         raise RuntimeError("read() and build() hash algorithms differ.")

      DiffFile = collections.namedtuple("DiffFile","missing new modifiedLines missingLines")

      lastFileSet = set(self.lastVersions.fileList)
      curFileSet = set(self.curVersions.fileList)
      self.diffs = collections.OrderedDict()

      newFiles = curFileSet - lastFileSet
      removedFiles = lastFileSet - curFileSet
      overlappingFiles = curFileSet & lastFileSet

      # Add new files
      for filePath in newFiles:
         self.diffs[filePath] = DiffFile(missing=not os.path.exists(filePath), # it is possible for files listed in the fileList to not exist in the first place
                                         new=True,
                                         modifiedLines=[],
                                         missingLines=[])

      # Add removed files
      for filePath in removedFiles:
         self.diffs[filePath] = DiffFile(missing=True,
                                         new=False,
                                         modifiedLines=[],
                                         missingLines=[])

      # Check overlapping files for changes
      for filePath in overlappingFiles:
         try:
            try:
               # python 2 dictionary views are explicit
               lastLines = self.lastVersions.fileVersions[filePath].lineHash.viewkeys() 
               curLines = self.curVersions.fileVersions[filePath].lineHash.viewkeys()
            except AttributeError:
               # python 3 dictinoary views are by default
               lastLines = self.lastVersions.fileVersions[filePath].lineHash.keys()
               curLines = self.curVersions.fileVersions[filePath].lineHash.keys()
         except KeyError:
            self.diffs[filePath] = DiffFile(missing=True,
                                            new=True,
                                            modifiedLines=[],
                                            missingLines=[])
            continue

         modifiedLines = sorted(list(curLines - lastLines))
         missingLines = sorted(list(lastLines - curLines))

         curLineTbl = self.curVersions.fileVersions[filePath].lineHash
         lastLineTbl = self.lastVersions.fileVersions[filePath].lineHash

         self.diffs[filePath] = DiffFile(missing=False,
                                         new=False,
                                         modifiedLines=[curLineTbl[hsh] for hsh in modifiedLines],
                                         missingLines=[lastLineTbl[hsh] for hsh in missingLines])

   def __enter__(self):
      self.read()
      self.build()
      self.compare()
      return self

   def __exit__(self, exc_type, exc_value, traceback):
      if self.revisionFileName and (self.doWrite or os.path.exists(self.revisionFileName)):
         self.write()

   def hasVersionChanged(self):
      return self.curVersions.version != self.lastVersions.version

   def getVersion(self):
      return self.curVersions.version
   
   def getFileVersions(self, format='text'):
      versions = self.curVersions.fileVersions
      versions = { filePath:vObj.version for filePath, vObj in versions.items() }
      if format == "text":
         return "\n".join( [ "{1}  {0}".format(*items) for items in versions.items()  ] )
      elif format == "json":
         return json.dumps(versions, indent=2)
      else:
         raise RuntimeError("Unknown format %s" % repr(format))

   def versionReport(self, showUnchanged=True):
      lineTemplate = "%-20s %s"
      for filePath, diffObj in self.diffs.items():
         if diffObj.missing and diffObj.new:
            print(lineTemplate % ("[new & missing]", filePath) )
            
         elif diffObj.missing:
            print(lineTemplate % ("[missing]", filePath) )
            
         elif diffObj.new:
            print(lineTemplate % ("[new]", filePath) )
            
         elif len(diffObj.modifiedLines) == 0 and len(diffObj.modifiedLines) == 0:
            if showUnchanged:
               print(lineTemplate % ("[unchanged]", filePath) )
            
         else:
            print(lineTemplate % ("[modified]", filePath) )
            print("   Modified Lines: %s" % diffObj.modifiedLines )
            print("   Missing Lines:  %s" % diffObj.missingLines )

      print("\nVersion: %s" % self.getVersion())
