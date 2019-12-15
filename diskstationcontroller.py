import requests
import json

from controller import PlayController, GenerateController

API_ERROR = {
    100: 'Unknown error',
    101: 'Invalid parameter',
    102: 'The requested API does not exist',
    103: 'The requested method does not exist',
    104: 'The requested version does not support the functionality',
    105: 'The logged in session does not have permission',
    106: 'Session timeout',
    107: 'Session interrupted by duplicate login'
}


class CGIException(Exception):
    print("CGIEXCEPTION")
    pass


class ConsumerFactoryException(Exception):
    print("CONSUMERFACTORYEXCEPTION")
    pass


class SynologyException(Exception):
    print("SYNOLOGYAEXCEPTION")
    pass


def _validate(response):
    status = response.status_code

    if status is not 200:
        raise SynologyException('The API request cannot been made')

    rsp = response.json()

    if not rsp['success']:
        code = rsp['error']['code']
        if code in API_ERROR:
            raise SynologyException(API_ERROR[code])
        else:
            raise SynologyException('Unknown error from API (%d)' % code)

    if 'data' in rsp:
        return rsp['data']


class DiskstationController(PlayController, GenerateController):

    _default_audio_device = ""
    _default_video_device = ""
    sid = None

    def __init__(self, base_url, user, password, video_device="", audio_device=""):
        self._default_video_device = video_device
        self.room = video_device
        self.user = user
        self.password = password
        super().__init__(base_url, "diskstation")
        with open('synology-api.json') as json_file:
            d = json.load(json_file)
            self.api_paths = d['data']

    def auth(self, session="VideoStation"):
        payload = {'api': 'SYNO.API.Auth', 'version': 2, 'method': 'login',
                   'account': self.user, 'passwd': self.password, 'session': session}
        response = requests.get(self.base_url + '/auth.cgi', params=payload)
        data = _validate(response)
        return data['sid']

    def switch_room(self, room, need_to_quote=True):
        self.room = room
        if need_to_quote:
            print("controller is encoding at request time ...")

    def handle_command(self, qrcode):
        if qrcode == 'cmd:playpause':
            params = {
                "api": "SYNO.VideoStation2.Controller.Playback",
                "method": "pause",
                "version": 2
            }
            self.perform_room_request('entry.cgi', params)
            return None
        elif qrcode == 'cmd:stop':
            params = {
                "api": "SYNO.VideoStation2.Controller.Playback",
                "method": "stop",
                "version": 2
            }
            self.perform_room_request('entry.cgi', params)
            return None
        else:
            return 'Hmm, I don\'t recognize that command : {}'.format(qrcode)

    def perform_request(self, path, payload):
        if not payload:
            payload = {}

        print('first', payload)

        if not '_sid' in payload:
            if not self.sid:
                print("need to auth first...")
                self.sid = self.auth()

            payload['_sid'] = self.sid
        print('sid', payload)

        if not path:
            if payload['api']:
                api = payload['api']
                path = self.api_paths[api]['path']

        print('path', payload, path)

        response = requests.get(self.base_url + '/' + path, params=payload)
        print('!!!REQUEST', response.url, response)
        data = _validate(response)

        return data

    def perform_global_request(self, path, payload=None):
        # self.perform_request(path, payload)
        print("global call for %s: %s" % (path, payload))

    def perform_room_request(self, path, payload=None, room=None):
        if room is None:
            if self.room is None:
                room = self._default_video_device
                print("no room set, using default: %s" % room)
        elif room != self.room:
            self.switch_room(room, False)

        if not payload:
            payload = {}

        payload['device_id'] = self.room

        self.perform_request(path, payload)

    def play_video(self, data, device_id=None):

        test = data[8:].split('=')
        print(data, test)
        (key, num) = test

        if not (key or num):
            print("!!!! missing identifier to play ")
            return

        if not device_id:
            if not self._default_video_device:
                print("!!!! missing device ")
                return
            else:
                device_id = self._default_video_device

        params = {
            "device_id": device_id,
            "playback_target": "file_id",
            "api": "SYNO.VideoStation2.Controller.Playback",
            "method": "play",
            "version": 2}
        params[key] = num

        self.perform_room_request('entry.cgi', params)

    def play_audio_playlist(self, data, device_id=None):
        pass
        # payloadPlaylist = {
        #     'api': 'SYNO.AudioStation.RemotePlayer',
        #     method: updateplaylist
        #     library: shared
        #     id: uuid: 0e4e1c00-00f0-1000-b849-78abbb7a67ce
        #     offset: -1
        #     limit: 0
        #     play: false
        #     version: 3
        #     keep_shuffle_order: false
        #     containers_json: [
        #         {"type": "playlist", "id": "playlist_shared_smart/Benjamin Blümchen"}]
        # }
        # payloadPlay = {'api': 'SYNO.AudioStation.RemotePlayer',
        #                'method': 'control',
        #                'id': device_id,  # uuid:0e4e1c00-00f0-1000-b849-78abbb7a67ce
        #                'version': 3,
        #                'action': 'play'
        #
        #
        #       }

    def get_episode(self, id, show_id):
        params = {
            'api': 'SYNO.VideoStation2.TVShowEpisode',
            'version': 1,
            'method': 'getinfo',
            'additional': '["file"]',
            'tvshow_id': show_id,
            'limit': 5000,
            'library_id': '0',
            'id': '[' + id + ']'
        }
        result = self.perform_request('entry.cgi', params)
        episode = result['episode'][0]
        file_id = episode['additional']['file'][0]['id']
        return {
            'song': episode['tagline'],
            'album': episode['title'],
            'arturl': self.base_url+'/entry.cgi?type=tvshow&id='+show_id+'&api=SYNO.VideoStation2.Poster&method=get&version=1&resolution='+'%2'+'22x%22&_sid='+self.sid,
            'data': 'dsvideo:{"api": "SYNO.VideoStation2.Controller.Playback", "method": "play",' +
            '"file_id": %s, "playback_target": "file_id", "version": 2}' % file_id
        }

    def get_movie(self, id):
        params = {
            'api': 'SYNO.VideoStation2.Movie',
            'version': 1,
            'method': 'getinfo',
            'additional': '["file","extra"]',
            'id': '[' + id + ']'
        }
        result = self.perform_request('entry.cgi', params)
        movie = result['movie'][0]
        file_id = movie['additional']['file'][0]['id']
        (title, subtitle) = movie['title'].split('-')
        return {
            'song': title.strip(),
            'album': subtitle.strip() if subtitle else None,
            'arturl': self.base_url+'/entry.cgi?type=movie&id='+id+'&api=SYNO.VideoStation2.Poster&method=get&version=1&resolution='+'%2'+'22x%22&_sid='+self.sid,
            'data': 'dsvideo:{"api": "SYNO.VideoStation2.Controller.Playback", "method": "play",' +
            '"file_id": %s, "playback_target": "file_id", "version": 2}' % file_id
        }

    def get_library_track(self, uri):
        data = uri[8:]
        # TODO check movie, tvshow episode, ...
        if data.startswith("tvshow"):
            (tvshowepisode, tvshow) = data.split("|")
            return self.get_episode(tvshowepisode.split('=')[1], tvshow.split("=")[1])
        elif data.startswith("movie"):
            print('get movie', data)
            return self.get_movie(data.split("=")[1])
        else:
            print('unknown ...', uri)
