import librosa
import numpy as np
from scipy import signal
import feedparser
import requests
from dotenv import load_dotenv
import os
import asyncio

# init
load_dotenv()
PODCAST_RSS_URL=os.getenv('PODCAST_RSS_URL')

async def download_episode(rss_feed_url) -> asyncio.coroutine:
    feed = feedparser.parse(rss_feed_url)
    current_episode = feed.entries[0]
    # Debugging output
    print(f'Downloading {current_episode.title}')
    
    # Get download link
    for link in current_episode.links:
        # find the mp3 link
        if link.type == 'audio/mpeg':
            download_link = link.href
            break

    # Download file and put it into the media dir
    with open('./media/episode.mp3', 'wb') as file:
        res = requests.get(download_link)
        file.write(res.content)


# thanks to hiisi13 for the code (https://github.com/hiisi13/audio-offset-finder)
def find_offset(episode, commercial_jingle):
    # load files
    y_within, sr_within = librosa.load(episode, sr=None)
    y_find, _ = librosa.load(commercial_jingle, sr=sr_within)

    # correlate function to find matches
    correlation = signal.correlate(y_within, y_find, mode='valid', method='fft')

    # peak is our first match
    peak = np.argmax(correlation)
    occurrences = [peak]
    max_value = correlation[peak]

    # remove peak
    correlation = np.delete(correlation, peak)
    value = max_value

    # we define a threshold to find the other matches, everything in the range of
    # peak - threshold we consider a match
    threshold = 10
    
    # same logic as with the peak, repeat until we leave threshold range
    while value > max_value - threshold:
        occ = np.argmax(correlation) # correct correleation array change (few frames don't matter though)
        value = correlation[occ]
        occurrences.append(occ)
        correlation = np.delete(correlation, occ)

    # convert indicies to timestamps (offset in seconds) with the sampling rate
    timestamps = list(map(lambda o: round(o / sr_within, 2), occurrences))

    # remove duplicates
    return list(set(timestamps))

    
asyncio.run(download_episode(PODCAST_RSS_URL))

# define audio files
episode = "./media/episode.mp3"
commercial_start = "./media/start_jingle.mp3"
commercial_end = "./media/end_jingle.mp3"

# find commercial starts
start = np.sort(find_offset(episode, commercial_start))
print(start)

# find commercial end
end = np.sort(find_offset(episode, commercial_end))
print(end)

#calc length of commercials
paired = list(zip(start,end))
print(f"{round(sum(list(map(lambda x: x[1] - x[0], paired))), 2)} seconds")
