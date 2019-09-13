import json
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))
UPLOAD_CATEGORIES_PATH = ROOT_DIR + "/data/upload_categories.json"


def create_default_categories():

    data = {
        "_default": {
            "metadata": {
                "title": "{title}",
                "description": "This video was published on {published_at} and is available on Twitch at: {url}",
            }
        }
    }

    with open(UPLOAD_CATEGORIES_PATH, "w") as cats:
        cats.write(json.dumps(data, indent=4))


def get_categories_file():
    try:
        with open(UPLOAD_CATEGORIES_PATH, "r", encoding="utf8") as cats:
            res = json.loads(cats.read())
            if "_default" in res:
                return res
            else:
                raise Exception("A \"_default\" category is required (in data/upload_categories.json)")
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        create_default_categories()
        with open(UPLOAD_CATEGORIES_PATH, "r", encoding="utf8") as cats:
            res = json.loads(cats.read())
            if "_default" in res:
                return res
            else:
                raise Exception("A \"_default\" category is required (in data/upload_categories.json)")


def detect_vod_game(categories, vod_data):
    title = vod_data["title"]

    for game_name, game_keywords in ((game_name, categories[game_name]["keywords"]) for game_name in categories if game_name != "_default"):
        for keyword in game_keywords:
            if keyword.lower() in title.lower():
                return game_name

    return "_default"


def get_formatted_metadata(categories, vod_data):

    game_name = detect_vod_game(categories, vod_data)
    game_meta = categories[game_name]["metadata"]

    formatted = {}
    for prop in game_meta:
        if not isinstance(game_meta[prop], list):
            formatted[prop] = game_meta[prop].format(**vod_data)
        else:
            formatted[prop] = []
            for val in game_meta[prop]:
                formatted[prop].append(val.format(**vod_data))

    return formatted


categories = get_categories_file()

if __name__ == '__main__':
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
    print(get_formatted_metadata(categories, test_vod_data))
