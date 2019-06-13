import requests
import json

from dateutil.parser import parse

from config import config

TWITCH_CLIENT_ID = config["twitch_client_id"]
USER_ID = config["twitch_user_id"]

twitch_session = requests.Session()
twitch_session.headers.update({"Client-ID": TWITCH_CLIENT_ID})


def fetch_videos() -> str:
    endpoint = "https://api.twitch.tv/helix/videos"
    params = {"user_id": USER_ID}

    with twitch_session.get(endpoint, params=params) as response:
        return json.loads(response.text)["data"]

def get_video_timestamp(video) -> float:
    created_string = video["created_at"]
    created_time = parse(created_string)
    return created_time.timestamp()

def get_video_duration(video) -> int:
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
    with open("test_data.json", "r") as file:
        data = json.loads(file.read())["data"]
        for video in data:
            print(get_video_duration(video), video["duration"])