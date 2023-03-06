import librosa
import numpy as np
from scipy import signal
import feedparser
import requests
from dotenv import load_dotenv
import os
import asyncio
from mutagen.mp3 import MP3
import sqlite3

async def download_episode(episode) -> asyncio.coroutine:
    print(f"downloading episode #{episode.itunes_episode} -> '{episode.title}'")
    
    download_link = find_link(episode, 'audio/mpeg')
    
    # Download file and put it into the media dir
    with open(os.getenv('EPISODE_PATH'), 'wb') as file:
        res = requests.get(download_link)
        file.write(res.content)

# links are kind of hidden in an array
def find_link(episode, link_type):
    for link in episode.links:
        if link.type == link_type:
            return link.href

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

def find_commercials():
    print('finding commercials')
    
    # define audio files
    episode = os.getenv('EPISODE_PATH')
    commercial_start = os.getenv('START_JINGLE_PATH')
    commercial_end = os.getenv('END_JINGLE_PATH')

    # find commercial starts
    start = np.sort(find_offset(episode, commercial_start))

    # find commercial end
    end = np.sort(find_offset(episode, commercial_end))

    #calc length of commercials
    return list(zip(start,end))
    

def write_data_to_db(episode, commercials):
    con = sqlite3.connect("commercialinfo.db")
    cur = con.cursor()
    
    # alter the commercial array for easier handling
    commercial_info = extract_commercial_info(commercials)
    
    print("writing to database")
    write_to_commercial_table(episode, commercial_info, cur)
    write_to_episode_table(episode, commercials, cur)
    
    con.commit()


def extract_commercial_info(commercials):
    commercial_info = []
    for pair in commercials:
        start = pair[0]
        end = pair[1]
        commercial_length = end - start
        commercial_info.append([start, end, commercial_length])
    
    return commercial_info


def write_to_commercial_table(episode, commercial_info, cur):
    for commercial in commercial_info:
        cur.execute(f"""
        INSERT INTO commercial VALUES
        ({commercial[0]}, {commercial[1]}, {commercial[2]}, "{episode.id}")
    """)


def write_to_episode_table(episode, commercials, cur): 
    total_commercial_length_seconds = round(sum(list(map(lambda x: x[1] - x[0], commercials))), 2)
    episode_length = calc_episode_length()
    episode_href = find_link(episode, 'text/html')
    
    cur.execute(f"""
    INSERT INTO episode VALUES
        ("{episode.title}","{episode.id}", "{episode_href}", {episode.itunes_episode}, {episode_length}, {total_commercial_length_seconds})
    """)

# there is a tag for the episode length in the rss feed but its often wrong
# so we calc the length from the mp3
def calc_episode_length():
    return round(MP3(os.getenv('EPISODE_PATH')).info.length, 2)


# starting point of script
load_dotenv()
con = sqlite3.connect(os.getenv('DB_PATH'))
cur = con.cursor()
feed = feedparser.parse(os.getenv('PODCAST_RSS_URL'))

# one entry is one podcast episode from the rss feed
for entry in feed.entries:
    print('########################')
    # download the mp3 file
    asyncio.run(download_episode(entry))
    
    # do some math to find the commercials in the episode
    commercials = find_commercials()
    
    # write the info to the database
    write_data_to_db(entry, commercials)