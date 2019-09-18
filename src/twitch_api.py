"""
Handles fetching Twitch VODs, converting duration strings into seconds,
and converting date strings into datetime objects.
"""

import os
import requests
import json

from datetime import datetime, timezone

from config import config

import logging
logger = logging.getLogger()

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

TWITCH_CLIENT_ID = config["twitch_client_id"]
USER_ID = config["twitch_user_id"]

twitch_session = requests.Session()
twitch_session.headers.update({"Client-ID": TWITCH_CLIENT_ID})

if not config["twitch_client_id"] or not config["twitch_user_id"]:
    logger.critical("Please enter your Twitch Client ID and Twitch User ID in data/config.json. (More info in the README)")
    exit(1)


class TwitchAPIError(Exception):
    pass


def fetch_videos(first=100) -> dict:
    """
    Retrieves the 20 most recent VODs from the
    channel specified by 'twitch_user_id' in config.json.
    """

    endpoint = "https://api.twitch.tv/helix/videos"
    params = {"user_id": USER_ID, "first": str(first)}

    with twitch_session.get(endpoint, params=params) as response:
        if response.ok:
            return json.loads(response.text)["data"]
        else:
            raise TwitchAPIError(response.status_code)


def get_video_timestamp(video: dict) -> float:
    """Converts the Twitch API provided datetime string into a Unix timestamp."""
    created_string = video["created_at"]
    # Parse the date string into a datetime object
    created_time = datetime.strptime(created_string, "%Y-%m-%dT%H:%M:%SZ")
    return created_time.replace(tzinfo=timezone.utc).timestamp()


def get_video_duration(video: dict) -> int:
    """Converts the video length string provided by the Twitch API into seconds."""
    dur = video["duration"]

    seconds = 0

    h = dur.split("h", maxsplit=1)
    m = (h[1] if len(h) > 1 else dur).split("m", maxsplit=1)
    s = (m[1] if len(m) > 1 else dur).split("s", maxsplit=1)

    if h[0] and len(h) == 2:
        seconds += int(h[0]) * 60 * 60
    if m[0] and len(m) == 2:
        seconds += int(m[0]) * 60
    if s[0] and len(s) == 2:
        seconds += int(s[0])

    return seconds


def get_contract_release_time(video: dict):
    time_start = get_video_timestamp(video)
    duration = get_video_duration(video)

    release_offset = config["scheduled_upload_wait_time"] * 60

    time_end = time_start + duration + release_offset
    date_end = datetime.utcfromtimestamp(time_end)

    return date_end


def datetime_to_iso(dt):
    return dt.isoformat() + ".0Z"


if __name__ == '__main__':
    print(json.dumps(fetch_videos(), indent=4))

    # with open(ROOT_DIR + "/data/test_data.json", "r") as file:
    #     data = json.loads(file.read())
    #     vod = data[1]
    #     print(datetime_to_iso(get_contract_release_time(vod)))
        # for video in data:
        #     print(get_video_timestamp(video), video["created_at"])
        #     print(get_video_duration(video), video["duration"])
