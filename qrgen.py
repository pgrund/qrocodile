#!/usr/bin/env python3
#
# Copyright (c) 2018 Chris Campbell
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import argparse
import hashlib
import json
import os.path
import shutil
import spotipy
import spotipy.util as util
import subprocess
import sys
import urllib
from urllib.request import urlopen, Request, build_opener
from urllib.parse import quote, urlencode
from controller import GenerateController, strip_title_junk
from sonoscontroller import SonosController
from diskstationcontroller import DiskstationController

from configparser import ConfigParser
import gettext
parser = ConfigParser(allow_no_value=True)
parser.read('qrocodile.ini')

el = gettext.translation('base', localedir='locales', languages=[
                         parser.get('DEFAULT', 'lang', fallback="en")])
                         
el.install()
_ = el.gettext

# Build a map of the known commands
# TODO: Might be better to specify these in the input file to allow for more customization
# (instead of hardcoding names/images here)
commands = {
  'cmd:stop': (_('Stop'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_stop_black_48dp.png'),
  'cmd:playpause': (_('Play / Pause'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_pause_circle_outline_black_48dp.png'),
  'cmd:next': (_('Skip to Next Song'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_skip_next_black_48dp.png'),
  'cmd:previous': (_('Skip to Previous Song'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_skip_previous_black_48dp.png'),
  'cmd:turntable': (_('Turntable'), 'http://moziru.com/images/record-player-clipart-vector-3.jpg'),
  'cmd:livingroom': (_('Living Room'), 'http://icons.iconarchive.com/icons/icons8/ios7/512/Household-Livingroom-icon.png'),
  'cmd:diningandkitchen': (_('Dining Room / Kitchen'), 'https://png.icons8.com/ios/540//dining-room.png'),
  'cmd:songonly': (_('Play the Song Only'), 'https://raw.githubusercontent.com/google/material-design-icons/master/image/drawable-xxxhdpi/ic_audiotrack_black_48dp.png'),
  'cmd:wholealbum': (_('Play the Whole Album'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_album_black_48dp.png'),
  'cmd:buildqueue': (_('Build List of Songs'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_playlist_add_black_48dp.png'),
  'cmd:whatsong': (_('What\'s Playing?'), 'https://raw.githubusercontent.com/google/material-design-icons/master/action/drawable-xxxhdpi/ic_help_outline_black_48dp.png'),
  'cmd:whatnext': (_('What\'s Next?'), 'https://raw.githubusercontent.com/google/material-design-icons/master/action/drawable-xxxhdpi/ic_help_outline_black_48dp.png'),
  'cmd:clear': (_('Clear Playlist'), 'https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_not_interested_black_48dp.png')
}

# Parse the command line arguments
arg_parser = argparse.ArgumentParser(
    description='Generates an HTML page containing cards with embedded QR codes that can be interpreted by `qrplay`.')
arg_parser.add_argument(
    '--input', help='the file containing the list of commands and songs to generate')
arg_parser.add_argument('--generate-images', action='store_true',
                        help='generate an individual PNG image for each card')
arg_parser.add_argument('--list-library', action='store_true',
                        help='list all available library tracks')
arg_parser.add_argument(
    '--spotify-username', help='the username used to set up Spotify access (only needed if you want to generate cards for Spotify tracks)')
args = arg_parser.parse_args()


sonos=SonosController(parser.get('sonos', 'url') if parser.has_option('sonos', 'url') else "http:localhost")
ds=DiskstationController(
    parser.get('diskstation', 'url') if parser.has_option('diskstation', 'url') else "http://diskstation:5000/webapi",
    parser.get('diskstation', 'user'),
    parser.get('diskstation', 'password')
    )

# TODO move to spotify controller
if args.spotify_username:
    # Set up Spotify access (comment this out if you don't want to generate cards for Spotify tracks)
    scope='user-library-read'
    token=util.prompt_for_user_token(args.spotify_username, scope)
    if token:
        sp=spotipy.Spotify(auth=token)
    else:
        raise ValueError('Can\'t get Spotify token for ' + \
                         args.spotify_username)
else:
    # No Spotify
    sp=None

def process_command(uri, index):
    (cmdname, arturl)=commands[uri]

    # Determine the output image file names
    qrout='out/{0}qr.png'.format(index)
    artout='out/{0}art.jpg'.format(index)

    # Create a QR code from the command URI
    print(subprocess.check_output(['qrencode', '-o', qrout, uri]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(['curl', arturl, '-o', artout]))

    return (cmdname, None, None)


def process_spotify_track(uri, index):
    if not sp:
        raise ValueError(
            'Must configure Spotify API access first using `--spotify-username`')

    track=sp.track(uri)

    print(track)
    # print 'track    : ' + track['name']
    # print 'artist   : ' + track['artists'][0]['name']
    # print 'album    : ' + track['album']['name']
    # print 'cover art: ' + track['album']['images'][0]['url']

    song=strip_title_junk(track['name'])
    artist=strip_title_junk(track['artists'][0]['name'])
    album=strip_title_junk(track['album']['name'])
    arturl=track['album']['images'][0]['url']

    # Determine the output image file names
    qrout='out/{0}qr.png'.format(index)
    artout='out/{0}art.jpg'.format(index)

    # Create a QR code from the track URI
    print(subprocess.check_output(['qrencode', '-o', qrout, uri]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(['curl', arturl, '-o', artout]))

    return (song.encode('utf-8'), album.encode('utf-8'), artist.encode('utf-8'))


def process_library_track(controller, uri, index):

    track=controller.get_library_track(uri)

    artist=track['artist'] if 'artist' in track else ''
    song=track['song'] if 'song' in track else ''
    album=track['album'] if 'album' in track else ''
    data=track['data']if 'data' in track else uri
    arturl=track['arturl'] if 'arturl' in track else 'https://raw.githubusercontent.com/google/material-design-icons/master/action/drawable-xxxhdpi/ic_movie_outline_black_48dp.png'

    # Determine the output image file names
    qrout='out/{0}qr.png'.format(index)
    artout='out/{0}art.jpg'.format(index)

    # Create a QR code from the track URI
    print(subprocess.check_output(['qrencode', '-o', qrout, data.encode('iso-8859-1')]))


    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(['curl', arturl, '-o', artout]))

    return (song, album, artist)


# Return the HTML content for a single card.
def card_content_html(index, artist, album, song, mode=None):
    qrimg='{0}qr.png'.format(index)
    artimg='{0}art.jpg'.format(index)

    html=''
    if mode == 'dsaudio' :
        html +='<img src="https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_library_music_black_48dp.png" class="dstype" />'
    elif mode == 'dsvideo':
        html +='<img src="https://raw.githubusercontent.com/google/material-design-icons/master/av/drawable-xxxhdpi/ic_video_library_black_48dp.png" class="dstype" />'

    html += '  <img src="{0}" class="art"/>\n'.format(artimg)
    html += '  <img src="{0}" class="qrcode"/>\n'.format(qrimg)
    html += '  <div class="labels">\n'
    html += '    <p class="song">{0}</p>\n'.format(song)
    if artist:
        html += '    <p class="artist"><span class="small">'+_('by')+'</span> {0}</p>\n'.format(
            artist)
    if album:
        html += '    <p class="album"><span class="small"></span> {0}</p>\n'.format(
            album)
    html += '  </div>\n'
    return html


# Generate a PNG version of an individual card (with no dashed lines).
def generate_individual_card_image(index, artist, album, song):
    # First generate an HTML file containing the individual card
    html=''
    html += '<html>\n'
    html += '<head>\n'
    html += ' <link rel="stylesheet" href="cards.css">\n'
    html += '</head>\n'
    html += '<body>\n'

    html += '<div class="singlecard">\n'
    html += card_content_html(index, artist, album, song)
    html += '</div>\n'

    html += '</body>\n'
    html += '</html>\n'

    html_filename='out/{0}.html'.format(index)
    with open(html_filename, 'w') as f:
        f.write(html)

    # Then convert the HTML to a PNG image (beware the hardcoded values; these need to align
    # with the dimensions in `cards.css`)
    png_filename='out/{0}'.format(index)
    print(subprocess.check_output(['webkit2png', html_filename, '--scale=1.0',
          '--clipped', '--clipwidth=720', '--clipheight=640', '-o', png_filename]))

    # Rename the file to remove the extra `-clipped` suffix that `webkit2png` includes by default
    os.rename(png_filename + '-clipped.png', png_filename + 'card.png')


def generate_cards():
    # Create the output directory
    dirname=os.getcwd()
    outdir=os.path.join(dirname, 'out')
    print(outdir)
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.mkdir(outdir)

    # Read the file containing the list of commands and songs to generate
    with open(args.input) as f:
        lines=f.readlines()

    # The index of the current item being processed
    index=0

    # Copy the CSS file into the output directory.  (Note the use of 'page-break-inside: avoid'
    # in `cards.css`; this prevents the card divs from being spread across multiple pages
    # when printed.)
    shutil.copyfile('cards.css', 'out/cards.css')

    # Begin the HTML template
    html='''
<html>
<head>
  <link rel="stylesheet" href="cards.css">
</head>
<body>
'''

    for line in lines:
        # Trim newline
        line=line.strip()

        # Remove any trailing comments and newline (and ignore any empty or comment-only lines)
        line=line.split('#')[0]
        line=line.strip()
        if not line:
            continue

        mode = line.split(':')[0]

        if line.startswith('cmd:'):
            (song, album, artist)=process_command(line, index)
        elif line.startswith('spotify:'):
            (song, album, artist)=process_spotify_track(line, index)
        elif line.startswith('lib:'):
            (song, album, artist)=process_library_track(sonos, line, index)
        elif line.startswith('dsvideo:') or line.startswith('dsaudio:'):
            (song, album, artist)=process_library_track(ds, line, index)
        else:
            print('Failed to handle URI: ' + line)
            exit(1)

        # Append the HTML for this card
        html += '<div class="card">\n'
        html += card_content_html(index, artist, album, song, mode)
        html += '</div>\n'

        if args.generate_images:
            # Also generate an individual PNG for the card
            generate_individual_card_image(index, artist, album, song)

        if index % 2 == 1:
            html += '<br style="clear: both;"/>\n'

        index += 1

    html += '</body>\n'
    html += '</html>\n'

    print(html)

    with open('out/index.html', 'w') as f:
        f.write(html)




generate_cards()
