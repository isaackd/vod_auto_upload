"""
Handles upload state such as which video is currently being uploaded and which videos
have been uploaded in the past.
"""

import os
import json

from config import config

import logging
logger = logging.getLogger()

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))
STATE_FILE_PATH = ROOT_DIR + "/data/state.json"
UPLOAD_HISTORY_PATH = ROOT_DIR + "/data/upload_history.txt"


def check_in_progress_uploads():
    """
    Checks to see if there were any interrupted uploads in state.json,
    and uploads them if so.
    """

    if os.path.isfile(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r", encoding="utf8") as file:
            contents = json.loads(file.read())

            for twitch_video_id in contents:
                entry = contents[twitch_video_id]
                file_path = entry["video_path"]
                if os.path.isfile(file_path):
                    logger.info(f"Resuming incomplete upload: {twitch_video_id} ({file_path})")
                    yield file_path, entry["twitch_vod"], entry["upload_url"]
                else:
                    logger.error(f"File in incomplete upload no longer exists: {twitch_video_id} ({file_path})")


def remove_in_progress_upload(twitch_vod_id: str) -> bool:
    """Removes a given entry from state.json"""

    if os.path.isfile(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r+", encoding="utf8") as file:
            try:
                contents = json.loads(file.read())
                contents.pop(twitch_vod_id, None)

                file.truncate(0)
                file.seek(0)

                file.write(json.dumps(contents, indent=4))
                return True

            except json.decoder.JSONDecodeError:
                return False
    else:
        return False


def mark_twitch_vod_as_uploaded(twitch_vod_id: str):
    """
    Marks a given Twitch VOD's ID as uploaded so that we don't
    accidentally upload the same video twice.
    """

    if os.path.isfile(UPLOAD_HISTORY_PATH):
        with open(UPLOAD_HISTORY_PATH, "a") as file:
            file.write(twitch_vod_id + "\n")
    else:
        with open(UPLOAD_HISTORY_PATH, "w") as file:
            file.write(twitch_vod_id + "\n")


def check_vod_uploaded(twitch_vod_id: str) -> bool:
    """Checks upload_history.txt for a given Twitch ID"""

    if os.path.isfile(UPLOAD_HISTORY_PATH):
        with open(UPLOAD_HISTORY_PATH, "r") as file:
            for vod_id in file:
                vod_id = vod_id.strip()
                if vod_id == twitch_vod_id:
                    return True

    return False


def save_in_progress_upload(upload_url: str, video_path: str, twitch_vod: dict):
    """
    Creates an entry in state.json with a given video's
    upload url, file path, and Twitch VOD information, so that an
    interrupted upload can be resumed at a later date.
    """

    def create_json_structure(file):
        contents = {}
        contents[twitch_vod["id"]] = {
            "upload_url": upload_url,
            "video_path": video_path,
            "twitch_vod": twitch_vod
        }

        file.write(json.dumps(contents, indent=4))

    if os.path.isfile(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r+", encoding="utf8") as file:
            try:
                contents = json.loads(file.read())

                contents[twitch_vod["id"]] = {
                    "upload_url": upload_url,
                    "video_path": video_path,
                    "twitch_vod": twitch_vod
                }

                file.truncate(0)
                file.seek(0)

                file.write(json.dumps(contents, indent=4))

            except json.decoder.JSONDecodeError:
                file.truncate(0)
                file.seek(0)
                create_json_structure(file)
    else:
        with open(STATE_FILE_PATH, "w", encoding="utf8") as file:
            create_json_structure(file)


def move_video_to_uploaded_folder(video_path):
    os.rename(video_path, config["folder_to_move_completed_uploads"] + "/" + os.path.basename(video_path))
