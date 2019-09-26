"""
Provides access to additional variables for use in upload_categories.json.
Can be treated as a regular python file (imports, module variables, etc).
"""

from datetime import datetime, timezone
import pytz

pacific_tz = pytz.timezone("America/Los_Angeles")


def generate_variables(twitch_vod: dict):
    """
    The dictionary that is used to place variables in the strings from the categories file (upload_categories.json)
    will be updated to include whatever is returned. If no custom variables are needed, the body can simply be replaced
    with pass, or just return nothing / an empty dict.
    """

    # For example: a human friendly(ish) version of the date and time the VOD was created (in PT)
    created_time = datetime.strptime(twitch_vod["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    created_time = created_time.replace(tzinfo=timezone.utc)
    pt_time = created_time.astimezone(pacific_tz)

    return {
        # strftime formatting: http://strftime.org/
        "friendly_created_at": pt_time.strftime("%B %m, %Y")
    }


# For checking the resulting variables
if __name__ == "__main__":
    test_vod_data = {
        "id": "463953400",
        "user_id": "119434445",
        "user_name": "FriendlyBaron",
        "title": "Speedrun of GTA San Andreas Los Santos% - first time running this game pls help - !sa - !songrequest theme: 1970-1979",
        "description": "",
        "created_at": "2019-08-07T20:00:57Z",
        "published_at": "2019-08-07T20:00:57Z",
        "url": "https://www.twitch.tv/videos/463953400",
        "thumbnail_url": "",
        "viewable": "public",
        "view_count": 18,
        "language": "en",
        "type": "archive",
        "duration": "2h31m1s"
    }

    print(generate_variables(test_vod_data))
