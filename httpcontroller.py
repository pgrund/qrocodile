from abc import ABC, abstractmethod

import urllib
from urllib.request import urlopen
from urllib.parse import quote


class RequestController(ABC):

    def __init__(self, base_url, namespace="default"):
        self.base_url = base_url
        self.room = "default"
        self.namespace = namespace
        super().__init__()

    def perform_request(self, path):
        url = "%s/%s" % (self.base_url, path)
        print("%s: %s" % (self.namespace, url))
        response = urlopen(url)
        result = response.read()
        print(result)

    def switch_room(self, room, need_to_quote=True):
        self.room = need_to_quote if quote(room) else room

    @abstractmethod
    def perform_global_request(self, path):
        pass

    @abstractmethod
    def perform_room_request(self, path):
        pass


class SonosController(RequestController):
    def __init__(self, base_url):
        super().__init__(base_url, "sonos")

    def perform_global_request(self, path):
        self.perform_request(self.base_url + "/" + path)

    def perform_room_request(self, path):
        self.perform_request(self.base_url + '/' + self.room + '/' + path)


class DummyController(RequestController):
    def __init__(self, base_url="local:"):
        super().__init__(base_url, "dummy")

    def perform_request(self, path):
        url = "%s/%s" % (self.base_url, path)
        print("DUMMY --- %s: %s" % (self.namespace, url))

    def perform_global_request(self, path):
        self.perform_request(self.base_url + "/" + path)

    def perform_room_request(self, path):
        self.perform_request("%s/%s/%s" % (self.base_url, self.room, path))
