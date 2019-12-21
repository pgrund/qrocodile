import requests
import json
from urllib.parse import quote, urlencode

from controller import PlayController, GenerateController, TypeMode
import logging

# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(lineno)s:%(funcName)s - %(message)s')

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


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
    pass


class ConsumerFactoryException(Exception):
    pass


class SynologyException(Exception):
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

    logger.debug('successfull call %s' % rsp)


class DiskstationController(PlayController, GenerateController):

    _default_audio_device = ""
    _default_video_device = ""
    sid = None
    _rooms = {
        'audio': {
            'sid': None,
            'session': 'AudioStation',
            'players': {},
            'default': None
        },
        'video': {
            'sid': None,
            'session': 'VideoStation',
            'players': {},
            'default': None
        }
    }

    def __set_players(self):
        audios = self.__get_audio_devices()
        for player in audios['players']:
            self._rooms['audio']['players'][player['name']] = {
                'name': player['name'], 'id': player['id'], 'type': player['type']}

        videos = self.__get_video_devices()
        for player in videos['device']:
            self._rooms['video']['players'][player['title']] = {
                'name': player['title'], 'id': player['id'], 'type': player['type']}

    def __set_defaults(self, default_video_room=None, default_audio_room=None):
        if default_video_room and self._rooms['video']['players'][default_video_room]:
            self._rooms['video']['default'] = self._rooms['video']['players'][default_video_room]['id']
        else:
            self._rooms['video']['default'] = next(
                iter(self._rooms['video']['players'].values()))['id']

        if not default_audio_room or default_audio_room not in self._rooms['audio']['players'].keys():
            default = list(self._rooms['audio']['players'].values())[0]
            self._rooms['audio']['default'] = default['id']
            logger.info('%s not in device list, using %s instead',
                        default_audio_room, default['name'])
        else:
            self._rooms['audio']['default'] = self._rooms['audio']['players'][default_audio_room]['id']

    def __init__(self, base_url, user, password, default_video_room=None, default_audio_room=None):

        self.user = user
        self.password = password
        super().__init__(base_url, "diskstation")
        with open('synology-api.json') as json_file:
            d = json.load(json_file)
            self.api_paths = d['data']

        self.__set_players()
        try:
            self.__set_defauls(default_video_room, default_audio_room)
        except:
            logger.error('could net set defaults: %s, %s',
                         default_video_room, default_audio_room)
        self.current_mode = TypeMode.VIDEO

    def auth(self, session=None):
        if not session:
            session = self._rooms[self.current_mode]['session']
        payload = {'api': 'SYNO.API.Auth', 'version': 2, 'method': 'login',
                   'account': self.user, 'passwd': self.password, 'session': session}
        response = requests.get(self.base_url + '/auth.cgi', params=payload)
        data = _validate(response)
        logger.debug('auth succeeded for %s ' % session)
        self._rooms[self.current_mode]['sid'] = data['sid']
        return data['sid']

    def switch_room(self, room, need_to_quote=True):

        if room in list(self._rooms[self.current_mode]['players'].keys()):
            self._rooms[self.current_mode]['default'] = self._rooms[self.current_mode]['players'][room]['id']
        else:
            logger.warn('cannot switch to room %s, not found ...', room)
        if need_to_quote:
            logger.warning("controller is encoding at request time ...")

    def switch_mode(self, mode):
        try:
            self.current_mode = mode
        except:
            self.current_mode = TypeMode.VIDEO

    def handle_command(self, qrcode):
        if self.current_mode == TypeMode.AUDIO:
            params = {
                'api': "SYNO.AudioStation.RemotePlayer",
                'method': 'control',
                'id': self._rooms[self.current_mode]['default'],
                'version': 2,
                'action': 'pause'
            }
        else:
            params = {
                "api": "SYNO.VideoStation2.Controller.Playback",
                "method": "pause",
                "version": 2
            }

        if qrcode == 'cmd:playpause':
            if self.current_mode == TypeMode.AUDIO:
                params['action'] = 'pause'
                return self.perform_room_request("AudioStation/remote_player.cgi", params)
            else:
                params['method'] = "pause"
                return self.perform_room_request('entry.cgi', params)

        elif qrcode == 'cmd:stop':
            if self.current_mode == TypeMode.AUDIO:
                params['action'] = 'stop'
                return self.perform_room_request("AudioStation/remote_player.cgi", params)
            else:
                params['method'] = "stop"
                return self.perform_room_request('entry.cgi', params)
        elif qrcode == 'cmd:next':
            if self.current_mode == TypeMode.AUDIO:
                params['action'] = 'next'
                return self.perform_room_request("AudioStation/remote_player.cgi", params)
            else:
                params['method'] = "next"
                return self.perform_room_request('entry.cgi', params)
        elif qrcode == 'cmd:previous':
            if self.current_mode == TypeMode.AUDIO:
                params['action'] = 'prev'
                return self.perform_room_request("AudioStation/remote_player.cgi", params)
            else:
                params['method'] = "prev"
                return self.perform_room_request('entry.cgi', params)
        else:
            return 'Hmm, I don\'t recognize that command : {}'.format(qrcode)

    def perform_request(self, path, payload):
        if not payload:
            payload = {}

        if not '_sid' in payload:
            if not self._rooms[self.current_mode]['sid']:
                logger.info("need to auth first...")
                self.auth(self._rooms[self.current_mode]['session'])

            payload['_sid'] = self._rooms[self.current_mode]['sid']

        if not path:
            if payload['api']:
                api = payload['api']
                path = self.api_paths[api]['path']

        params = urlencode(payload, quote_via=quote)
        response = requests.get(self.base_url + '/' + path, params=params)

        logger.debug('URL: %s  ->%s', response.url, response.status_code)
        return _validate(response)

    def perform_global_request(self, path, payload=None):
        # self.perform_request(path, payload)
        print("global call for %s: %s" % (path, payload))

    def perform_room_request(self, path, payload=None, room=None):
        if room is None:
            if self._rooms[self.current_mode]['default'] is None:
                raise SynologyException('no room and no default room')
        elif room != self._rooms[self.current_mode]['default']:
            self.switch_room(room, False)

        if not payload:
            payload = {}

        payload['device_id'] = self._rooms[self.current_mode]['default']

        self.perform_request(path, payload)

    def get_episode(self, id, show_id):
        self.current_mode = TypeMode.VIDEO
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
            'arturl': self.base_url+'/entry.cgi?type=tvshow&id='+show_id+'&api=SYNO.VideoStation2.Poster&method=get&version=1&resolution='+'%2'+'22x%22&_sid='+self._rooms[self.current_mode]['sid'],
            'data': 'dsvideo:{"api": "SYNO.VideoStation2.Controller.Playback", "method": "play",' +
            '"file_id": %s, "playback_target": "file_id", "version": 2}' % file_id
        }

    def get_movie(self, id):
        self.current_mode = TypeMode.VIDEO
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
            'arturl': self.base_url+'/entry.cgi?type=movie&id='+id+'&api=SYNO.VideoStation2.Poster&method=get&version=1&resolution=%222x%22&_sid='+self._rooms[self.current_mode]['sid'],
            'data': 'dsvideo:{"api": "SYNO.VideoStation2.Controller.Playback", "method": "play",' +
            '"file_id": %s, "playback_target": "file_id", "version": 2}' % file_id
        }

    def get_song(self, id):

        self.current_mode = TypeMode.AUDIO

        payload = {
            'api': 'SYNO.AudioStation.Song',
            'version': 3,
            'method': 'getinfo',
            'additional': 'file,song_tag',
            'id': id,
            'library_id': '0'
        }
        
        result = self.perform_request('AudioStation/song.cgi', payload)
        song = result['songs'][0]
        queryParams=urlencode({'api': 'SYNO.AudioStation.Cover',
                                 'output_default': 'true',
                                 'version': 3,
                                 'library': 'shared',
                                 'method': 'getsongcover',
                                 'view': 'default',
                                 'id': id,
                                 '_sid': self._rooms[self.current_mode]['sid']
                                 }, quote_via = quote)

        return {
            'song': song['title'],
            'album': song['additional']['song_tag']['album'],
            'artist':song['additional']['song_tag']['artist'],
            'arturl': self.base_url+'/AudioStation/cover.cgi?'+queryParams,
            'data': 'dsaudio:music_id='+id
        }


    def get_album(self, album, album_artist, artist=None):

        self.current_mode = TypeMode.AUDIO

        payload = {
            'limit': 1000,
            'method': 'list',
            'library': 'shared',
            'api': 'SYNO.AudioStation.Album',
            'album': '%s' % album,
            'album_artist': '%s' % album_artist,
            'additional': '["file","song","extra"]',
            'version': 3,
        }
        if artist:
            payload['artist'] = artist
        result = self.perform_request('AudioStation/album.cgi', payload)
        

        matchedAlbum = None
        for x in result['albums']:
            if x['name'].lower() == album.lower():
                matchedAlbum = x
                break

        if not matchedAlbum:
            raise SynologyException('no album for ' + album)
        else:
            album = matchedAlbum['name']
            album_artist = matchedAlbum['album_artist']
            artist = matchedAlbum['artist'] if matchedAlbum['artist'] != '' else matchedAlbum['display_artist']

        queryParams = urlencode({'api': 'SYNO.AudioStation.Cover',
                                 'output_default': 'true',
                                 'version': 3,
                                 'library': 'shared',
                                 'method': 'getcover',
                                 'view': 'default',
                                 'album_name': album,
                                 'album_artist_name': album_artist,
                                 '_sid': self._rooms[self.current_mode]['sid']
                                 }, quote_via=quote)

        return {
            'song': album,
            'album': album_artist,
            'artist': artist,
            'arturl': self.base_url+'/AudioStation/cover.cgi?'+queryParams,
            'data': 'dsaudio:[{"type":"album","sort_by":"name","sort_direction":"ASC","album":"%s", "album_artist":"%s"}]' % (album, album_artist)
        }

    def get_artist(self, artist=""):

        self.current_mode = TypeMode.AUDIO

        payload = {
            'limit': 1000,
            'method': 'list',
            'library': 'shared',
            'api': 'SYNO.AudioStation.Artist',
            'artist': artist,
            'additional': '["file","song","extra"]',
            'version': 3,
        }
        result = self.perform_request('AudioStation/artist.cgi', payload)
        matchedArtist = None
        for x in result['artists']:
            if x['name'].lower() == artist.lower():
                matchedArtist = x
                break

        if not matchedArtist:
            raise SynologyException('nop artist for ' + artist)
        else:
            artist = matchedArtist['name']

        queryParams = urlencode({'api': 'SYNO.AudioStation.Cover',
                                 'output_default': 'true',
                                 'version': 3,
                                 'library': 'shared',
                                 'method': 'getcover',
                                 'view': 'default',
                                 'artist_name': artist,
                                 '_sid': self._rooms[self.current_mode]['sid']
                                 }, quote_via=quote)

        return {
            'song': artist,
            'arturl': self.base_url+'/AudioStation/cover.cgi?'+queryParams,
            'data': 'dsaudio:[{"type":"artist","sort_by":"name","sort_direction":"ASC","artist":"%s"}]' % artist
        }

    def get_library_track(self, uri):
        dsMode, dsData = uri[:7], uri[8:]
        data = dict(item.strip().split('=') for item in dsData.split('|'))
        
        if dsMode == 'dsvideo':
            if "tvshow_id" in data:
                return self.get_episode(data['tvshowepisode_id'], data['tvshow_id'])
            elif "movie_id" in data:
                return self.get_movie(data['movie_id'])
            else:
                print('unknown video ...', uri)
        elif dsMode == 'dsaudio':
            if  "song" in data:
                return self.get_song(data['song'])

            elif "album" in data:
                return self.get_album(data['album'], data['album_artist'])

            elif "artist" in data:
                return self.get_artist(data['artist'])

            else:
                logger.warn("unknown audio %s ...", uri)
        else:
            logger.warn('unknown %s ...', uri)

    def play_audio(self, containers_json):
        self.current_mode = TypeMode.AUDIO

        if containers_json.startswith('music_'):
            song = containers_json
            containers_json = '[]'

        payloadLoad = {
            'api': 'SYNO.AudioStation.RemotePlayer',
            'method': 'updateplaylist',
            'library': 'shared',
            'id': self._rooms[self.current_mode]['default'],
            'offset': -1,
            'limit': 0,
            'play': 'false',
            'version': 3,
            'keep_shuffle_order': 'false',
            'containers_json': containers_json
        }
        if song:
            payloadLoad['songs']=song

        responseLoad = self.perform_request(
            'AudioStation/remote_player.cgi', payloadLoad)

        logger.debug('==>load %s', responseLoad)

        payloadPlay = {
            'api': 'SYNO.AudioStation.RemotePlayer',
            'method': 'control',
            'id': self._rooms[self.current_mode]['default'],
            'version': 3,
            'action': 'play',
            'value': 0
        }

        responsePlay = self.perform_request(
            'AudioStation/remote_player.cgi', payloadPlay)

        logger.debug('==>play %s', responsePlay)

    def __get_audio_devices(self):
        self.current_mode = TypeMode.AUDIO
        payload = {
            'api': 'SYNO.AudioStation.RemotePlayer',
            'version': 2,
            'method': 'list'
        }
        return self.perform_request(
            'AudioStation/remote_player.cgi', payload)

    def __get_video_devices(self):
        self.current_mode = TypeMode.VIDEO
        payload = {
            'api': 'SYNO.VideoStation2.Controller.Device',
            'version': 1,
            'method': 'list',
            'limit': 500
        }
        return self.perform_request('entry.cgi', payload)

# ??
    def add_playlist(self, playlist, offset=-1):

        self.current_mode = TypeMode.AUDIO

        payloadPlaylist = {
            'api': 'SYNO.AudioStation.RemotePlayer',
            'method': 'updateplaylist',
            'library': 'shared',
            'id': self._rooms[self.current_mode]['default'],
            'offset': offset,
            'limit': 0,
            'play': 'true',
            'version': 3,
            'containers_json': '[{"type": "playlist", "id": "%s"}]' % playlist
        }

        return self.perform_request(
            'AudioStation/remote_player.cgi', payload=payloadPlaylist)
