import os
import requests
import json

from datetime import datetime

from config import config

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

TWITCH_CLIENT_ID = config["twitch_client_id"]
USER_ID = config["twitch_user_id"]

twitch_session = requests.Session()
twitch_session.headers.update({"Client-ID": TWITCH_CLIENT_ID})

if not config["twitch_client_id"] or not config["twitch_user_id"]:
    print("Please enter your Twitch Client ID and Twitch User ID in data/config.json. (More info in the README)")
    exit(1)

class TwitchAPIError(Exception):
    pass

def fetch_videos() -> dict:
    endpoint = "https://api.twitch.tv/helix/videos"
    params = {"user_id": USER_ID}

    with twitch_session.get(endpoint, params=params) as response:
        if response.ok:
            return json.loads(response.text)["data"]
        else:
            raise TwitchAPIError(response.status_code)

def get_video_timestamp(video: dict) -> float:
    created_string = video["created_at"]
    created_time = datetime.strptime(created_string, "%Y-%m-%dT%H:%M:%SZ")
    return created_time.timestamp()

def get_video_duration(video: dict) -> int:
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


if __name__ == '__main__':
    print(json.dumps(fetch_videos(), indent=4))

    # with open(ROOT_DIR + "/data/test_data.json", "r") as file:
    #     data = json.loads(file.read())
    #     for video in data:
    #         print(get_video_timestamp(video), video["created_at"])
            # print(get_video_duration(video), video["duration"])
