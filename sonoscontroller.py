from controller import PlayController, GenerateController, strip_title_junk
import json
import subprocess

# Removes extra junk from titles, e.g:
#   (Original Motion Picture Soundtrack)
#   - From <Movie>
#   (Remastered & Expanded Edition)


class SonosController(PlayController, GenerateController):
    def __init__(self, base_url, linein_source=None):
        self.linein_source = linein_source
        super().__init__(base_url, "sonos")

    def perform_global_request(self, path):
        self.perform_request(path)

    def perform_room_request(self, path):
        self.perform_request(self.room + '/' + path)

    def load_library_if_needed(self):
        self.perform_room_request('musicsearch/library/loadifneeded')

    def say(self, data):
        self.perform_room_request('say/' + data)

    def playpause(self):
        self.perform_room_request('playpause')

    def handle_command(self, qrcode):
        if qrcode == 'cmd:playpause':
            self.perform_room_request('playpause')
            return None
        elif qrcode == 'cmd:next':
            self.perform_room_request('next')
            return None
        elif qrcode == 'cmd:turntable':
            self.perform_room_request(
                'linein/' + self.linein_source)
            self.perform_room_request('play')
            return 'I\'ve activated the turntable'
        elif qrcode == 'cmd:livingroom':
            self.switch_room('Living Room')
            return 'I\'m switching to the living room'
        elif qrcode == 'cmd:diningandkitchen':
            self.switch_room('Dining Room')
            return 'I\'m switching to the dining room'
        elif qrcode == 'cmd:buildqueue':
            # controller.perform_room_request('pause')
            self.perform_room_request('clearqueue')
            return 'Let\'s build a list of songs'
        elif qrcode == 'cmd:whatsong':
            self.perform_room_request('saysong')
            return None
        elif qrcode == 'cmd:whatnext':
            self.perform_room_request('saynext')
            return None
        else:
            return 'Hmm, I don\'t recognize that command : {}'.format(qrcode)

    def get_library_track(self, uri):
        track_json = self.perform_request(
            self.base_url + '/musicsearch/library/metadata/' + uri)
        track = json.loads(track_json)
        print(track)

        song, artist, album, arturl = [strip_title_junk(track[k]) for k in (
            'trackName', 'artistName', 'albumName', 'artworkUrl')]

        # XXX: Sonos strips the "The" prefix for bands that start with "The" (it appears to do this
        # only in listing contexts; when querying the current/next queue track it still includes
        # the "The").  As a dumb hack (to preserve the "The") we can look at the raw URI for the
        # track (this assumes an iTunes-style directory structure), parse out the artist directory
        # name and see if it starts with "The".

        uri_parts = urlparse(track['uri'])
        uri_path = uri_parts.path
        print(uri_path)
        (uri_path, song_part) = os.path.split(uri_path)
        (uri_path, album_part) = os.path.split(uri_path)
        (uri_path, artist_part) = os.path.split(uri_path)

        if artist_part.startswith('The%20'):
            artist = 'The ' + artist

        return {'song': song, 'artist': artist, 'album': album, 'arturl': arturl}
