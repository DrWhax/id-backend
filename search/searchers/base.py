import logging
import requests
import dateutil.parser
from threading import Thread

log = logging.getLogger(__name__)


class ResultSet(list):
    def __init__(self, total, results=[]):
        self.extend(results)
        self.total = total


class ImageSearchResult(dict):
    def __init__(self, provider, imageurl, resulturl, timestamp, caption,
                 linkurl=None, linktitle=None, metadata={}):
        self["provider"] = provider
        self["timestamp"] = timestamp
        self["image_url"] = imageurl
        self["result_url"] = resulturl
        self["caption"] = caption
        self["metadata"] = metadata
        self["link"] = linkurl
        self["linktitle"] = linktitle


class DocumentSearchResult(dict):
    def __init__(self, provider, resulturl, timestamp, text,
                 title, metadata={}):
        self["provider"] = provider
        self["timestamp"] = timestamp
        self["text"] = text
        self["title"] = title
        self["result_url"] = resulturl
        self["metadata"] = metadata


class Searcher(object):

    def start(self, search):
        thread = Thread(target=self.run, args=(search,))
        thread.start()

    def json_api_request(self, meta, force_get=False):
        log.debug('Searcher %r hitting %r: %r', self.PROVIDER, self.URL, meta)
        return requests.get(self.URL, params=meta).json()

    def prepare_query(self, q):
        # Default query preparation is idempotent
        return q

    def run(self, search):
        runner = search.create_runner(self.PROVIDER)
        import json
        query = self.prepare_query(json.loads(search.query))
        results = self.search(**query)
        for r in results:
            search.create_result(self.PROVIDER, r)

        runner.done = True
        runner.results = len(results)
        runner.save()


class SocialSearcher(Searcher):
    TYPE = "social"


class DocumentSearcher(Searcher):
    TYPE = "document"

    def prepare_query(self, query):
        r = {}
        r["q"] = query["q"].encode("utf-8")
        if query["startdate"]:
            r["startdate"] = dateutil.parser.parse(query["startdate"])
        if query["enddate"]:
            r["enddate"] = dateutil.parser.parse(query["enddate"])
        return r


class ImageSearcher(Searcher):
    TYPE = "image"

    def prepare_query(self, query):
        r = {}
        r["q"] = query["q"].encode("utf-8")
        r["lat"] = query["lat"]
        r["lon"] = query["lon"]
        r["radius"] = query["radius"]
        if query["startdate"]:
            r["startdate"] = dateutil.parser.parse(query["startdate"])
        if query["enddate"]:
            r["enddate"] = dateutil.parser.parse(query["enddate"])
        r["offset"] = query["offset"]
        r["count"] = query["count"]
        return r