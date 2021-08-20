import collections
import logging
import os
from copy import copy
from youtube_dl import YoutubeDL
from pytube import *
from flask import Flask, json, render_template, session,request, url_for, flash, redirect, Response, session, stream_with_context
from flask_ask_alphavideo import Ask, question, statement, audio, current_stream, logger, convert_errors
from sentry_sdk import last_event_id, set_user
from sentry_sdk.integrations.flask import FlaskIntegration
from pygtail import Pygtail
import sqlite3
import requests

# version 1.8
set_user('PRODUCTION')


def get_db_connection():
    conn = sqlite3.connect('/data/database.db')
    conn.row_factory = sqlite3.Row
    return conn


def get_post(post_id):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?',
                        (post_id,)).fetchone()
    conn.close()
    if post is None:
        abort(404)
    return post


def start():
    sentry_sdk.init(
        dsn="https://d781c09d67f34a05b2b2d89193f4f2a0@o575799.ingest.sentry.io/5728581",
        integrations=[FlaskIntegration()],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0
    )


ip = '0.0.0.0'  # System Ip
host = '0.0.0.0'  # doesn't require anything else since we're using ngrok
port = 5000  # may want to check and make sure this port isn't being used by anything else

LOG_FILE = 'app.log'
log = logging.getLogger('__name__')
logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG)

ytdl_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': False,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': ip
}

ytdl = YoutubeDL(ytdl_options)

app = Flask(__name__)
app.config["DEBUG"] = os.environ.get("FLASK_DEBUG", True)
app.config["JSON_AS_ASCII"] = False
app.config['SECRET_KEY'] = 'dev'
app.config['PUBLIC'] = os.environ.get("public", "False") == "True"
app.config.from_mapping(
    BASE_URL="http://localhost:5000",
)

print("By AndrewsTech")
queue = "1"

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404


@app.errorhandler(405)
def not_found_error(error):
    return render_template('405.html'), 405


@app.errorhandler(500)
def server_error_handler(error):
    return render_template("500.html", sentry_event_id=last_event_id()), 500


@app.route('/version')
def version():
    return '1.9.0'

@app.route('/api/proxy/<path:url>')
def proxy(url):
    req = requests.get(url, stream = True)
    return Response(stream_with_context(req.iter_content(chunk_size=1024)), content_type = req.headers['content-type'])


@app.route('/api')
def alexafunction():
    return render_template('api.html')


if app.config["PUBLIC"]:
    import public
else:
    import pages

ask = Ask(app, "/api")
logging.getLogger('flask_ask').setLevel(logging.INFO)

p = Playlist('https://www.youtube.com/playlist?list=PLMC9KNkIncKtPzgY-5rmhvj7fax8fdxoj')

playlist = p.video_urls


@app.route('/api')
def api():
    return render_template('api.html')



class QueueManager(object):

    def __init__(self, urls):
        self._urls = urls
        self._queued = collections.deque(urls)
        self._history = collections.deque()
        self._current = None

    @property
    def status(self):
        status = {
            'Current Position': self.current_position,
            'Current URL': self.current,
            'Next URL': self.up_next,
            'Previous': self.previous,
            'History': list(self.history)
        }
        return status

    @property
    def up_next(self):
        """Returns the url at the front of the queue"""
        qcopy = copy(self._queued)
        try:
            return qcopy.popleft()
        except IndexError:
            return None

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, url):
        self._save_to_history()
        self._current = url

    @property
    def history(self):
        return self._history

    @property
    def previous(self):
        history = copy(self.history)
        try:
            return history.pop()
        except IndexError:
            return None

    def add(self, url):
        self._urls.append(url)
        self._queued.append(url)

    def extend(self, urls):
        self._urls.extend(urls)
        self._queued.extend(urls)

    def _save_to_history(self):
        if self._current:
            self._history.append(self._current)

    def end_current(self):
        self._save_to_history()
        self._current = None

    def step(self):
        self.end_current()
        self._current = self._queued.popleft()
        return self._current

    def step_back(self):
        self._queued.appendleft(self._current)
        self._current = self._history.pop()
        return self._current

    def reset(self):
        self._queued = collections.deque(self._urls)
        self._history = []

    def start(self):
        self.__init__(self._urls)
        return self.step()

    @property
    def current_position(self):
        return len(self._history) + 1





def ytplay(video):
    if video.startswith('https://www.youtube.com/'):
        print('youtube url')
        yt = YouTube(video)
        print(yt.streams.all()[0].url)
        return audio().play(yt.streams.all()[0].url)
    else:
        print('stream url')
        return audio().play(video)


@ask.intent('AMAZON.FallbackIntent')
def handle_fallback_intent():
    fallback = render_template('fallback')
    return question(fallback)


@ask.launch
def launch():
    card_title = render_template('card_title')
    question_text = render_template('welcome')
    return question(question_text).simple_card(card_title, question_text)



@ask.intent('PlaylistIntent')
def start_playlist():
    speech = 'Heres a playlist of some sounds. You can ask me Next, Previous, or Start Over'
    stream_url = queue.start()
    return audio(speech).ytplay(stream_url)


@ask.intent('QueryIntent', mapping={'query': 'Query'})
def handle_query_intent(query):
    if not query or 'query' in convert_errors:
        return question('no results found, try another search query')

    data = ytdl.extract_info(f"ytsearch5:{query}", download=False)
    search_results = data['entries']

    if not search_results:
        noresult = render_template('noresult')
        session.attributes[search_results] = search_results
        return question(noresult)

    result = search_results[0]
    song_name = result['title']
    channel_name = result['uploader']

    search = [data['entries'][0]['url'], data['entries'][1]['url'], data['entries'][2]['url'], data['entries'][3]['url'], data['entries'][4]['url'] ]
    print(search)
    global queue
    queue = QueueManager(search)
    playing = render_template('playing', song_name=song_name, channel_name=channel_name)
    stream_url = queue.start()
    return  audio(playing), ytplay(stream_url)



@ask.on_playback_nearly_finished()
def nearly_finished():
    if queue.up_next:
        _infodump('Alexa is now ready for a Next or Previous Intent')
        # dump_stream_info()
        next_stream_render = queue.up_next
        yt = YouTube(next_stream_render)
        print(yt.streams.all()[0].url)
        next_stream = yt.streams.all()[0].url
        _infodump('Enqueueing {}'.format(next_stream))
        return audio().enqueue(next_stream)
    else:
        _infodump('Nearly finished with last song in playlist')


# QueueManager object is not stepped forward here.
# This allows for Next Intents and on_playback_finished requests to trigger the step
@ask.on_playback_finished()
def play_back_finished():
    _infodump('Finished Audio stream for track {}'.format(queue.current_position))
    if queue.up_next:
        queue.step()
        _infodump('stepped queue forward')
        dump_stream_info()
    else:
        return statement('You have reached the end of the playlist!')


# NextIntent steps queue forward and clears enqueued streams that were already sent to Alexa
# next_stream will match queue.up_next and enqueue Alexa with the correct subsequent stream.
@ask.intent('AMAZON.NextIntent')
def next_song():
    if queue.up_next:
        speech = 'playing next queued song'
        next_stream = queue.step()
        _infodump('Stepped queue forward to {}'.format(next_stream))
        dump_stream_info()
        return ytplay(next_stream)
    else:
        return audio('There are no more songs in the queue')


@ask.intent('AMAZON.PreviousIntent')
def previous_song():
    if queue.previous:
        speech = 'playing previously played song'
        prev_stream = queue.step_back()
        dump_stream_info()
        return ytplay(prev_stream)

    else:
        return audio('There are no songs in your playlist history.')


@ask.intent('AMAZON.StartOverIntent')
def restart_track():
    if queue.current:
        speech = 'Restarting current track'
        dump_stream_info()
        return ytplay(queue.current)
    else:
        return statement('There is no current song')


@ask.on_playback_started()
def started(offset, token, url):
    _infodump('Started audio stream for track {}'.format(queue.current_position))
    dump_stream_info()


@ask.on_playback_stopped()
def stopped(offset, token):
    _infodump('Stopped audio stream for track {}'.format(queue.current_position))

@ask.intent('AMAZON.PauseIntent')
def pause():
    seconds = current_stream.offsetInMilliseconds / 1000
    msg = 'Paused the Playlist on track {}, offset at {} seconds'.format(
        queue.current_position, seconds)
    _infodump(msg)
    dump_stream_info()
    return audio(msg).stop().simple_card(msg)


@ask.intent('AMAZON.ResumeIntent')
def resume():
    seconds = current_stream.offsetInMilliseconds / 1000
    msg = 'Resuming the Playlist on track {}, offset at {} seconds'.format(queue.current_position, seconds)
    _infodump(msg)
    dump_stream_info()
    return audio(msg).resume().simple_card(msg)


@ask.session_ended
def session_ended():
    return "{}", 200


def dump_stream_info():
    status = {
        'Current Stream Status': current_stream.__dict__,
        'Queue status': queue.status
    }
    _infodump(status)


def _infodump(obj, indent=2):
    msg = json.dumps(obj, indent=indent)
    logger.info(msg)



if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', 5000))
    print ('Starting app on port %d' % port)
    app.run(host=host, port=port)
