import requests
from abc import ABC, abstractmethod

import urllib
from urllib.request import urlopen
from urllib.parse import quote


def strip_title_junk(title):
    junk = [' (Original', ' - From', ' (Remaster', ' [Remaster']
    for j in junk:
        index = title.find(j)
        if index >= 0:
            return title[:index]
    return title


class RequestController(ABC):

    def __init__(self, base_url, namespace="default"):
        self.base_url = base_url
        self.room = "default"
        self.namespace = namespace
        super().__init__()

    def perform_request(self, path):
        url = "%s/%s" % (self.base_url, path)
        response = urlopen(url)
        result = response.read()
        print(result)


class PlayController(RequestController):
    def switch_room(self, room, need_to_quote=True):
        self.room = quote(room) if need_to_quote else room

    @abstractmethod
    def perform_global_request(self, path, payload=None):
        pass

    @abstractmethod
    def perform_room_request(self, path, payload=None):
        pass

    @abstractmethod
    def handle_command(self, qrcode):
        pass

    def load_library_if_needed(self):
        pass

    def say(self, phrase):
        pass


class GenerateController(RequestController):
    @abstractmethod
    def get_library_track(self, uri):
        pass


class DummyController(PlayController):
    def __init__(self, base_url="local::"):
        super().__init__(base_url, "dummy")

    def perform_request(self, path):
        print("DUMMY --- %s: %s/%s" % (self.namespace, self.base_url, path))

    def perform_global_request(self, path):
        self.perform_request(path)

    def perform_room_request(self, path):
        self.perform_request("%s/%s" % (self.room, path))

    def handle_command(self, qrcode):
        print("DUMMY --- command: %s" & qrcode)
        return None
