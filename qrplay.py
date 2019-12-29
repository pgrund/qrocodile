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
import json
import os
import subprocess
import sys
from time import sleep
import cv2
from pyzbar import pyzbar
import imutils
from imutils.video import VideoStream
from sonoscontroller import SonosController
from diskstationcontroller import DiskstationController
from controller import TypeMode

from configparser import ConfigParser

import gettext

parser = ConfigParser(allow_no_value=True)
parser.read('qrocodile.ini')

el = gettext.translation('qrocodile', localedir='locales', languages=[
                         parser.get('DEFAULT', 'lang', fallback="en")])
el.install()
_ = el.gettext

# Parse the command line arguments
arg_parser = argparse.ArgumentParser(
    description='Translates QR codes detected by a camera into Sonos commands.')
arg_parser.add_argument('--default-device', default='Dining Room',
                        help='the name of your default device/room')
arg_parser.add_argument('--linein-source', default='Dining Room',
                        help='the name of the device/room used as the line-in source')
arg_parser.add_argument('--hostname', default='localhost',
                        help='the hostname or IP address of the machine running `node-sonos-http-api`')
arg_parser.add_argument('--skip-load', action='store_true',
                        help='skip loading of the music library (useful if the server has already loaded it)')
arg_parser.add_argument(
    '--debug-file', help='read commands from a file instead of launching scanner')
arg_parser.add_argument(
    '--show-frame', action='store_true', help='display videoframe with recognized code')
args = arg_parser.parse_args()

# sonos=SonosController(parser.get('sonos', 'url') if parser.has_option('sonos', 'url') else "http:localhost")
controller = DiskstationController(
    parser.get('diskstation', 'url') if parser.has_option(
        'diskstation', 'url') else "http://diskstation:5000/webapi",
    parser.get('diskstation', 'user'),
    parser.get('diskstation', 'password'),
    parser.get('rooms', 'tv_living_room'),
    parser.get('rooms', 'tv_living_room')
)

isPI = parser.getboolean('DEFAULT', 'isPI', fallback=True)
# Load the most recently used device, if available, otherwise fall back on the `default-device` argument
try:
    with open('.last-device', 'r') as device_file:
        current_device = device_file.read().replace('\n', '')
        print(_('Defaulting to last used room: ') + current_device)
except:
    current_device = parser.get('rooms', 'tv_living_room')
    print(_('Initial room: ') + current_device)

controller.switch_room(current_device)

# Keep track of the last-seen code
last_qrcode = ''


class Mode:
    PLAY_SONG_IMMEDIATELY = 1
    PLAY_ALBUM_IMMEDIATELY = 2
    BUILD_QUEUE = 3


current_mode = Mode.PLAY_SONG_IMMEDIATELY


def switch_to_room(room):
    # controller.perform_global_request('pauseall')
    controller.switch_room(room)
    with open(".last-device", "w") as device_file:
        device_file.write(room)


def speak(phrase):
    print('SPEAKING: \'{0}\''.format(phrase))
    controller.say(phrase)


# Causes the onboard green LED to blink on and off twice.  (This assumes Raspberry Pi 3 Model B; your
# mileage may vary.)
def blink_led():
    if not isPI:
        print(_('not in PI mode, LED BLINK!!!'))
        return

    duration = 0.15

    def led_off():
        os.system("echo 0 | sudo tee /sys/class/leds/led0/brightness > /dev/null")

    def led_on():
        os.system("echo 1 | sudo tee /sys/class/leds/led0/brightness > /dev/null")

    # Technically we only need to do this once when the script launches
    os.system("echo none | sudo tee /sys/class/leds/led0/trigger > /dev/null")

    led_on()
    sleep(duration)
    led_off()
    sleep(duration)
    led_on()
    sleep(duration)
    led_off()


def handle_command(qrcode):
    global current_mode

    print(_('HANDLING COMMAND: ') + qrcode)

    if qrcode == 'cmd:songonly':
        current_mode = Mode.PLAY_SONG_IMMEDIATELY
        phrase = _('Show me a card and I\'ll play that song right away')
    elif qrcode == 'cmd:wholealbum':
        current_mode = Mode.PLAY_ALBUM_IMMEDIATELY
        phrase = _('Show me a card and I\'ll play the whole album')
    elif qrcode == 'cmd:buildqueue':
        current_mode = Mode.BUILD_QUEUE
        phrase = _('Let\'s build a list of songs')

    print(_("DELEGATING TO CONTROLLER"))
    phrase = controller.handle_command(qrcode)

    if phrase:
        speak(phrase)


def handle_library_item(uri):
    if not uri.startswith('lib:'):
        if not uri.startswith('ds'):
            return

        dsMode, dsData = uri[:7], uri[8:]
        if dsMode == 'dsvideo':
            controller.switch_mode(TypeMode.VIDEO)

            print(_('PLAYING DS VIDEO: ') + dsData + ' (' + dsMode + ')')
            params = json.loads(dsData)

            controller.perform_room_request(None, params)

        elif dsMode == 'dsaudio':
            controller.switch_mode(TypeMode.AUDIO)

            print(_('PLAYING DS AUDIO: ') + dsData + ' (' + dsMode + ')')

            controller.play_audio(dsData)
        else:
            print(_('UNKNOWN DS ITEM : ') + dsData + ' (' + dsMode + ')')

    else:
        print(_('PLAYING FROM LIBRARY: ') + uri)
        if current_mode == Mode.BUILD_QUEUE:
            action = 'queuesongfromhash'
        elif current_mode == Mode.PLAY_ALBUM_IMMEDIATELY:
            action = 'playalbumfromhash'
        else:
            action = 'playsongfromhash'

        controller.perform_room_request(
            'musicsearch/library/{0}/{1}'.format(action, uri))


def handle_spotify_item(uri):
    print(_('PLAYING FROM SPOTIFY: ') + uri)

    if current_mode == Mode.BUILD_QUEUE:
        action = 'queue'
    elif current_mode == Mode.PLAY_ALBUM_IMMEDIATELY:
        action = 'clearqueueandplayalbum'
    else:
        action = 'clearqueueandplaysong'

    controller.perform_room_request('spotify/{0}/{1}'.format(action, uri))


def handle_qrcode(qrcode):
    global last_qrcode

    # Ignore redundant codes, except for commands like "whatsong", where you might
    # want to perform it multiple times
    if qrcode == last_qrcode and not qrcode.startswith('cmd:'):
        print(_('IGNORING REDUNDANT QRCODE: ') + qrcode)
        return

    print(_('HANDLING QRCODE: ') + qrcode)

    if qrcode.startswith('cmd:'):
        handle_command(qrcode)
    elif qrcode.startswith('spotify:'):
        handle_spotify_item(qrcode)
    else:
        handle_library_item(qrcode)

    # Blink the onboard LED to give some visual indication that a code was handled
    # (especially useful for cases where there's no other auditory feedback, like
    # when adding songs to the queue)
    if not args.debug_file:
        blink_led()

    last_qrcode = qrcode


# Read from the `debug.txt` file and handle one code at a time.
def read_debug_script():
    # Read codes from `debug.txt`
    with open(args.debug_file) as f:
        debug_codes = f.readlines()

    # Handle each code followed by a short delay
    for code in debug_codes:
        # Remove any trailing comments and newline (and ignore any empty or comment-only lines)
        code = code.split("#")[0]
        code = code.strip()
        if code:
            handle_qrcode(code)
            sleep(4)


controller.perform_global_request('pauseall')
speak(_('Hello, I\'m qrocodile.'))

if not args.skip_load:
    # Preload library on startup (it takes a few seconds to prepare the cache)
    print(_('Indexing the library...'))
    speak(_('Please give me a moment to gather my thoughts.'))
    controller.load_library_if_needed()
    print(_('Indexing complete!'))
    speak(_('I\'m ready now!'))

speak(_('Show me a card!'))

if args.debug_file:
    # Run through a list of codes from a local file
    read_debug_script()
else:
    # initialize video stream and wait
    vs = VideoStream(usePiCamera=isPI).start()
    sleep(2.0)

    lastCommand = ''
    try:
        while True:
            frame = vs.read()
            # for better performance, resize the image
            frame = imutils.resize(frame, width=400)
            # find and decode all barcodes in this frame
            barcodes = pyzbar.decode(frame)
            for barcode in barcodes:
                # the barcode data is a bytes object so if we want to draw it
                # on our output image we need to convert it to a string first
                barcodeData = barcode.data.decode("utf-8")
                barcodeType = barcode.type

                # display enabled
                if args.show_frame:
                    # extract the bounding box location of the barcode and draw
                    # the bounding box surrounding the barcode on the image
                    (x, y, w, h) = barcode.rect
                    cv2.rectangle(frame, (x, y), (x + w, y + h),
                                  (0, 0, 255), 2)

                    # draw the barcode data and barcode type on the image
                    text = "{} ({})".format(barcodeData, barcodeType)
                    cv2.putText(frame, text, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                if barcodeData == "cmd:playpause":
                    handle_qrcode(barcodeData)
                    lastCommand = barcodeData
                    print(_('special handling play/pause, wait 5s'))
                    sleep(5)
                    print(_('... now checking again'))

                elif barcodeData != lastCommand:
                    handle_qrcode(barcodeData)
                    lastCommand = barcodeData

            if args.show_frame:
                # show the output frame
                cv2.imshow("Barcode Scanner", frame)
                key = cv2.waitKey(1) & 0xFF

    except KeyboardInterrupt:
        print(_('Stopping scanner ...'))
    finally:
         # close the output CSV file do a bit of cleanup
        print(_("[INFO] cleaning up..."))
        cv2.destroyAllWindows()
        vs.stop()
