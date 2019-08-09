"""Handles creating and loading the config file (data/config.json)."""

import math
import os
import json

import logging

from pathlib import Path


class ConfigLoadError(Exception):
    pass


logger = logging.getLogger()

# videos directory isn't a good default value
# just for easier testing
# actually there should probably just be no default video directory
HOME_DIRECTORY = str(Path.home()).replace("\\", "/")

DEFAULT_WATCH_FOLDER = f"{HOME_DIRECTORY}/Videos"

DEFAULT_CONFIG = {
    "youtube_client_id": "",
    "youtube_client_secret": "",

    "twitch_client_id": "",
    "twitch_user_id": "",

    "folder_to_watch": DEFAULT_WATCH_FOLDER,
    "folder_to_move_completed_uploads": DEFAULT_WATCH_FOLDER + "/uploaded",
    # check the folder for video files that can be uploaded every 10 seconds
    # should be increased to around a minute after testing
    "check_folder_interval": 10,
    # # Video files must be at least 1GiB to be uploaded
    "file_size_threshold": math.pow(1024, 3),
    # Video files must not have been modified for at least 5 minutes
    "file_age_threshold": 60 * 5,
    # upload with the specified chunk size instead of filesize / 10
    "file_chunk_size_override": False,

    "twitch_video_duration_threshold": 3_600,
    "file_modified_start_max_delta": 120,
    "file_modified_end_max_delta": 1_800,
    # how often we should call the Twitch API and fetch new VODs
    "twitch_vod_refresh_rate": 3 * 60 * 60
}

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))


def create_default_config():
    with open(ROOT_DIR + "/data/config.json", "w") as file:
        file.write(json.dumps(DEFAULT_CONFIG, indent=4))


def load_config() -> dict:
    """
    Tries to load config.json, creating one with the default values
    if there is an error or the config does not exist.
    """
    if os.path.isfile(ROOT_DIR + "/data/config.json"):
        with open(ROOT_DIR + "/data/config.json", "r") as config_file:
            try:
                config_dict = json.loads(config_file.read())
                for key in DEFAULT_CONFIG:
                    if key not in config_dict:
                        logger.error(f"Invalid config: {config_dict}")
                        raise ConfigLoadError("A key is missing from the config file. Reverting to defaults...")

                return config_dict
            except (json.decoder.JSONDecodeError, ConfigLoadError):
                logger.error("There was an error with the config file. Reverting to defaults...", exc_info=True)
                create_default_config()
                return load_config()
    else:
        create_default_config()
        return load_config()


config = load_config()
