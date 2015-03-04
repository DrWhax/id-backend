import hashlib
import os, os.path, shutil, sys
import magic
import zipfile
import StringIO
import logging
from datetime import datetime
from copy import deepcopy
import elasticsearch
from distutils.version import StrictVersion

class AuthenticationError(Exception):
    pass

class FileNotFound(Exception):
    def __str__(self):
        return "[File not found]"


def sha256sum(filename, blocksize=65536):
    f = None
    if type(filename) == str:
        f = open(filename, "r+b")
    else:
        f = filename
    
    hash = hashlib.sha256()
    for block in iter(lambda: f.read(blocksize), ""):
        hash.update(block)

    f.seek(0)
    return hash.hexdigest()

COMMON_METADATA_V1 = {
    "name":                 "",     # Everything should have a name
    "date_added":           "",
    "changelog":            [],
    "notes":                [],
    "public_read":          False,
    "allowed_users":        [],
    "allowed_write_users":  [],
}

FILE_METADATA_V2 = {
    "identifier":           "",     # Project-User-6 digits of SHA256
    "created_by":           "",     # User ID
    "schema_version":       2,      # Always version 2
    "is_resident":          True,
    "filename":             "",     # Used if file is resident
    "url":                  "",     # Used if file is non-resident
    "title":                "",
    "hash":                 "",     # Required for resident files
    "size":                 0,      # Size in bytes
    "tags":                 [],
    "mimetype":             "",
    "description":          "",
    "text":                 "",     # Extracted 
    "annotations":          [],
    "is_indexed":           False,
    "extra":                {},     # Any extra structured metadata
}
FILE_METADATA_V2.update(COMMON_METADATA_V1)

TAG_METADATA_V1 = {
    "parents":              [],
    "icon":                 "default",
}
TAG_METADATA_V1.update(COMMON_METADATA_V1)

class MetaMixin:
    def __getitem__(self, item):
        return self.meta[item]

    def __setitem__(self, item, value):
        self.meta[item] = value
        self.sync()

    def get_metadata(self):
        if not self.id: raise ValueError("Cannot get descriptor without an id")
        self.meta.update(self.fs.es.get(index=self.fs.es_index, doc_type=self.DOCTYPE, id=self.id)["_source"])
        return self.meta

    def to_json(self):
        return {"id": self.id, "meta": self.meta}

class PermissionsMixin:
    def log(self, message, sync=False):
        self.meta["changelog"].append({
                "date": datetime.now().isoformat(), 
                "user": self.fs.user.id, 
                "message": message
            })
        if sync:
            self._sync()

    def _create_index(self):
        """Adds an index entry to the Elasticsearch database."""
        if not self.fs.user:
            raise AuthenticationError()
        res = self.fs.es.create(index=self.fs.es_index, doc_type=self.DOCTYPE, body=self.meta)
        if res["created"]:
            self.id = res["_id"]
            self.version = res["_version"]

    def _create_metadata(self):
        """Creates a default metadata template for a new entry."""
        if self.id: raise ValueError("Cannot recreate existing %s" % self.DOCTYPE)
        self.meta = deepcopy(self.METADATA_TEMPLATE)
        self.meta["date_added"] = datetime.now().isoformat()
        self.log("Created")
        if self.fs.user:
            self.meta["allowed_users"].append(self.fs.user.id)
            self.meta["allowed_write_users"].append(self.fs.user.id)

    def _sync(self):
        """Updates an index entry in the Elasticsearch database."""
        if not self.has_write_permission(self.fs.user):
            raise AuthenticationError()
        if not self.id: return
        result = self.fs.es.update(
                index=self.fs.es_index, 
                doc_type=self.DOCTYPE, 
                id=self.id, 
                body={"doc": self.meta, "detect_noop": True}
            )
        return result

    def add_user(self, user, write=False):
        if not user: return
        if user.id not in self.meta["allowed_users"]:
            self.meta["allowed_users"].append(user.id)
        if write and user.id not in self.meta["allowed_write_users"]:
            self.meta["allowed_write_users"].append(user.id)
        self.log("Added user '%s' [%d] (write=%s)" % (user.username, user.id, write))
        self._sync()

    def remove_user(self, user):
        if not user: return
        self.meta["allowed_users"].remove(user.id)
        self.meta["allowed_write_users"].remove(user.id)
        self._sync()

    def has_permission(self, user):
        # FIXME: Add tag support!
        return user.id in self.meta["allowed_users"]

    def has_write_permission(self, user):
        # FIXME: Add tag support!
        return user.id in self.meta["allowed_write_users"]


class Tag(MetaMixin, PermissionsMixin):
    DOCTYPE = "tag"
    METADATA_TEMPLATE = TAG_METADATA_V1
    def __init__(self, fs, tid=None, name=None, prepopulate_meta={}):
        self.fs = fs
        self.id = tid
        self.meta = deepcopy(self.METADATA_TEMPLATE)
        self.meta.update(prepopulate_meta)
        if self.id and not prepopulate_meta:
            self.get_metadata()

    def create(self, name):
        self._create_metadata()
        self.meta["name"] = name
        self._create_index()
        return self.id, self.meta, True

    def delete(self, sure=False):
        if not self.id: raise ValueError("No tag specified")
        if not sure: raise ValueError("You don't seem to be sure. (try sure=True)")
        self.fs.es.delete(index=self.fs.es_index, doc_type="tag", id=self.id)
        return True

    def parent_add(self, parenttag):
        if parenttag not in self.meta["parents"]:
            self.meta["parents"].append(parenttag)
        self._sync()

    def parent_remove(self, parenttag):
        self.meta["parents"].remove(parenttag)
        self._sync()

    def get_files(self):
        if not self.has_permission(self.fs.user):
            raise AuthenticationError("User %s has no access to file %s" % (self.fs.user, self.id))

        # FIXME: This is limited to never get more than the first 1000 files.
        body = {"query":{"match":{"tags": self.id}}}
        res = self.fs.es.search(index=self.fs.es_index, doc_type="file", body=body, size=1000)
        return res["hits"]["total"], [File(self.fs, filemeta["_id"], prepopulate_meta=filemeta["_source"]) for filemeta in res["hits"]["hits"]]

    def get_zip(self):
        # To prevent insane loads, we're going to limit this to 50MB archives for now.
        _50MB = 50 * 1024 * 1024
        files = self.get_files()[1]
        totalsize = sum([x.meta.get("size", 0) for x in files])
        if totalsize > _50MB:
            return False

        zstr = StringIO.StringIO()
        with zipfile.ZipFile(zstr, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f.resident_location(), f.meta["filename"])
        zstr.seek(0)
        return zstr


class File(MetaMixin, PermissionsMixin):
    DOCTYPE = "file"
    METADATA_TEMPLATE = FILE_METADATA_V2
    def __init__(self, fs, fid=None, prepopulate_meta={}):
        self.fs = fs
        self.id = fid
        self.meta = deepcopy(self.METADATA_TEMPLATE)
        self.meta.update(prepopulate_meta)
        if self.id and not prepopulate_meta:
            self.get_metadata()

    def __unicode__(self):
        if not self.id: return "[Uninitialized file object]"
        if not self.meta: self.get_metadata()
        return "[File %s] %s title='%s', mimetype='%s', tags='%s', is_resident='%s'." % (
            self.id, 
            "filename='%s'" % self.meta.get("filename") if self.meta.has_key("filename") else
            "url='%s'" % self.meta.get("url"),
            self.meta.get("title", ""), self.meta.get("mimetype", ""), 
            self.meta.get("tags", []), self.meta.get("is_resident", False))

    def __str__(self):
        return self.__unicode__()

    def get(self):
        if not self.has_permission(self.fs.user):
            raise AuthenticationError("User %s has no access to file %s" % (self.fs.user, self.id))
        if not self.id: raise ValueError("Cannot get file without an id")
        if self.meta["is_resident"]:
            return open(self.resident_location())
        else:
            return urllib2.urlopen(self.meta["url"])

    def resident_location(self):
        if self.meta["hash"] == "": raise Exception("File hash missing")
        if self.meta["filename"] == "": raise Exception("Filename missing")
        hashdirs = os.path.join(*map(lambda x,y: x+y, *([iter(self.meta["hash"])] * 2))[:3])
        directory = os.path.join(self.fs.data_root, hashdirs)
        try:
            os.makedirs(directory)
        except os.error:
            pass
        return os.path.join(directory, self.meta["filename"])

    def _build_index(self):
        """Reads the file and tries basic details extraction."""
        pass

    def create_from_url(self, url, make_resident=False):
        self._create_metadata()
        self.meta["url"] = url
        self.meta["is_resident"] = False
        if self.fs.file_exists_by_url(self.meta["url"]):
            return None, None, False

        self._build_index()
        self._create_index()

        if make_resident:
            self._make_resident()

        return self.id, self.meta, True

    def _make_resident(self, buf=None):
        """Makes a resident copy of an URL-based file entry."""
        raise NotImplementedError()
        self.meta["is_resident"] = True

    def create_from_filehandle(self, fh):
        self._create_metadata()
        filename = fh.name
        self.meta["filename"] = filename
        self.meta["hash"] = sha256sum(fh)
        # FIXME: "ID" is a temporary identifier. At some point, we need some kind of "project" notion.
        self.meta["identifier"] = "%s-%s-%6s" % ("ID", self.fs.user.profile.abbr, self.meta["hash"][-6:])
        self.meta["mimetype"] = magic.Magic(mime=True).from_buffer(fh.read(100))
        if self.fs.file_exists_by_hash(self.meta["hash"]):
            print "Warning: File exists!"
            f = self.fs.get_file_by_hash(self.meta["hash"])
            if (self.fs.user):
                f.add_user(self.fs.user)
            return f.id, f.meta, False

        fh.seek(0)
        f = open(self.resident_location(), "w+")
        f.write(fh.read())
        f.close()

        self.meta["size"] = os.stat(self.resident_location()).st_size

        self._build_index()
        self._create_index()

        return self.id, self.meta, True

    def create_from_file(self, filename):
        if not os.path.isfile(filename): raise ValueError("File does not exist")
        self._create_metadata()
        self.meta["filename"] = os.path.split(filename)[-1]
        self.meta["hash"] = sha256sum(filename)
        self.meta["mimetype"] = magic.Magic(mime=True).from_file(filename)
        if self.fs.file_exists_by_hash(self.meta["hash"]):
            print "Warning: File exists!"
            f = self.fs.get_file_by_hash(self.meta["hash"])
            if (self.fs.user):
                f.add_user(self.fs.user)
            return f.id, f.meta, False

        shutil.copy(filename, self.resident_location())
        self.meta["size"] = os.stat(self.resident_location()).st_size
        self._build_index()
        self._create_index()

        return self.id, self.meta, True

    def delete(self, sure=False):
        if not self.id: raise ValueError("No file specified")
        if not sure: raise ValueError("You don't seem to be sure. (try sure=True)")
        if self.meta["filename"]:
            try:
                os.unlink(self.resident_location())
            except OSError:
                pass
        self.fs.es.delete(index=self.fs.es_index, doc_type="file", id=self.id)
        return True

    def add_tag(self, tagid):
        if tagid in self.meta["tags"]: return
        self.meta["tags"].append(tagid)
        self.log("Added tag '%s'" % tagid)
        self._sync()

    def remove_tag(self, tagname):
        self.meta["tags"].remove(tagid)
        self.log("Removed tag '%s'" % tagid)
        self._sync()

    def add_note(self, text):
        note = {
            "user": self.fs.user.id,
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "text": text,
            "score": 0,
        }
        self.meta["notes"].append(note)
        self.log("Added note")
        return self._sync()

    def get_thumbnail(self, width=680, height=460):
        if self.meta["mimetype"]:
            basetype, subtype = self.meta["mimetype"].split("/")
        else:
            return False

        if basetype == "image":
            # We are dealing with an image!
            #from PIL import Image
            #i = Image.open(self.resident_location())
            #i.thumbnail((width,height), Image.ANTIALIAS)
            return False
        elif basetype == "application":
            return False
        # TODO: Build me
        return False

    def get_thumbnail_as_img_tag(self):
        img = self.get_thumbnail()
        if img:
            return '<img src="%s"/>' % img
        else:
            return ''


class FileSystem:
    def __init__(self, es_servers = None, es_index = None, data_root = None, user=None):
        self.es_servers = es_servers
        self.es_index = es_index
        self.data_root = data_root
        self.user = user
        self.connect()

    def connect(self):
        self.es = elasticsearch.Elasticsearch(self.es_servers)
        # Get version info:
        info = self.es.info()
        ver = StrictVersion(info["version"]["number"])
        if ver < StrictVersion("1.4.0"):
            raise Exception("Podaci requires an ElasticSearch server version >= 1.4.0")

        # Guarantee that the index exists...
        if not self.es.indices.exists(index=self.es_index):
            self.es.indices.create(index=self.es_index, ignore=400)

            print "#"*50
            print "## %-44s ##" % ""
            print "## %-44s ##" % "Initialized ElasticSearch Index"
            print "## %-44s ##" % ""
            print "#"*50


    def create_file_from_url(self, url):
        f = File(self)
        fid, meta, created = f.create_from_url(url)
        return f

    def create_file(self, filename):
        f = File(self)
        if type(filename) in [str, unicode]:
            fid, meta, created = f.create_from_file(filename)
        else:
            fid, meta, created = f.create_from_filehandle(filename)
        if not created:
            f.id = fid
            f.meta = meta
        return f

    def get_file_by_hash(self, sha):
        body = {"query":{"term":{"hash":sha}}}
        res = self.es.search(index=self.es_index, doc_type="file", body=body)
        print res
        if len(res["hits"]["hits"]) == 0: return FileNotFound()
        return self.get_file_by_id(res["hits"]["hits"][0]["_id"])

    def get_file_by_id(self, fid):
        return File(self, fid)

    def file_exists_by_hash(self, sha):
        body = {"query":{"term":{"hash":sha}}}
        try:
            res = self.es.search_exists(index=self.es_index, doc_type="file", body=body)
        except elasticsearch.exceptions.NotFoundError, e:
            return False
        return res["exists"]

    def file_exists_by_url(self, url):
        body = {"query":{"term":{"url":url}}}
        try:
            res = self.es.search_exists(index=self.es_index, doc_type="file", body=body)
        except elasticsearch.exceptions.NotFoundError, e:
            return False
        return res["exists"]

    def list_user_tags(self, user, root=None, _from=0, _size=1000):
        if root:
            body = {
                    "query": {
                        "bool": {
                            "must": [
                                {"match":{"allowed_users":user.id}},
                                {"match":{"parents":root}}
                            ]
                        }
                    }
                }
        elif root == False: # Explicitly disallow non-root items
            body = {
                    "query": {
                        "term": {"allowed_users": user.id}
                    },
                    "filter": {
                        "missing": {"field": "parents"}
                    }
                }
        else:
            body = {"query":{"term":{"allowed_users":user.id}}}
        res = self.es.search(index=self.es_index, doc_type="tag", body=body, from_=_from, size=_size)
        return res["hits"]["total"], [Tag(self, tagmeta["_id"], prepopulate_meta=tagmeta["_source"]) for tagmeta in res["hits"]["hits"]]

    def list_user_files(self, user, root=None, _from=0, _size=1000):
        if root:
            body = {"query":{"bool":
                    {"must":
                        [
                            {"match":{"allowed_users":user.id}},
                            {"match":{"tags":root}}
                        ]
                    }
                }}
        else:
            body = {"query":{"term":{"allowed_users":user.id}}}
        res = self.es.search(index=self.es_index, doc_type="file", body=body, from_=_from, size=_size)
        return res["hits"]["total"], [File(self, filemeta["_id"], prepopulate_meta=filemeta["_source"]) for filemeta in res["hits"]["hits"]]

    def list_files(self, tag, _from=0, _size=1000):
        body = {"query":{"term":{"tags": tag.lower()}}}
        res = self.es.search(index=self.es_index, doc_type="file", body=body, from_=_from, size=_size)
        return res["hits"]["total"], [File(self, filemeta["_id"], prepopulate_meta=filemeta["_source"]) for filemeta in res["hits"]["hits"]]

    def search_files(self, query, _from=0, _size=1000):
        res = self.es.search(index=self.es_index, doc_type="file", body=query, from_=_from, size=_size)
        return res["hits"]["total"], [File(self, filemeta["_id"], prepopulate_meta=filemeta["_source"]) for filemeta in res["hits"]["hits"]]

    def search_all_by_name(self, query, _from=0, _size=1000):
        body = {
                "query": { 
                    "fuzzy_like_this": { 
                        "like_text": query,
                        "fields": [ "name", "title", "identifier", "description", "filename"],
                    }
                },
            }
        res = self.es.search(index=self.es_index, body=body, from_=_from, size=_size)
        items = []
        for item in res["hits"]["hits"]:
            x = {}
            x["id"] = item["_id"]
            x["type"] = item["_type"]
            if item["_source"].has_key("name"):
                x["name"] = item["_source"]["name"]
            else:
                x["name"] = item["_source"]["filename"]
            items.append(x)
        return items

    def get_tag(self, tagid):
        t = Tag(self, tagid)
        t.get_metadata()
        return t

    def create_tag(self, tagname):
        t = Tag(self)
        res = t.create(tagname)
        return t


if __name__ == "__main__":
    class Strawman:
        def __init__(self, id):
            self.id = id

    #logging.basicConfig(level=logging.DEBUG)
    # logging.getLogger("elasticsearch.trace").addHandler(logging.StreamHandler(stream=sys.stderr))
    #logging.getLogger("elasticsearch").addHandler(logging.StreamHandler(stream=sys.stderr))
    SERVERS = [{"host": "localhost"}]
    # SERVERS = [{"host": "54.227.243.186", "port": 9200}]
    fs = FileSystem(SERVERS, "podaci", "/home/smari/Projects/OCCRP/data/", user=Strawman("smari"))

    for fe in fs.search_files({"query":{"term":{"is_resident":True}}}):
        fe.delete(sure=True)

    ## Test 1: Create a file!
    print "Creating a file:"
    f = fs.create_file("/home/smari/Projects/OCCRP/tech_overview.pdf")
    print "   -- Created %s" % f

    ## Test 2: Add tag
    print "Adding a 'tech' tag to file %s" % (f)
    f.add_tag("tech")
    
    ## Test 3: Listing a tag:
    print "Listing files in 'tech':"
    for f in fs.list_files("tech"):
        print f, f.meta["hash"]
    print "-----"

    ## Test 4: Get file by hash
    v = fs.get_file_by_hash("c3b22e9f470fcbc50cdf149aa2009259641f8ee47d204659172794e5a780b109")
    print "Found file by hash: %s" % v

    ## Test 5: Check for non-existent file by hash:
    print "Nonexistent file exists: %s" % fs.file_exists_by_hash("not a real hash")

    ## Test 6: Delete file created earlier
    print "Deleting file %s" % f
    f.delete(sure=True)

    ## Test 7: Make sure data store is empty:
    print "Checking for files:"
    print fs.search_files({"query":{"term":{"public_read":False}}})
