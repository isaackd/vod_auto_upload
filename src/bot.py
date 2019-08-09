"""
Main File
Watches the folder for new videos, matches them with their VODs, then uploads them to YouTube.
Handles quota exceeding, resuming interrupted uploads, and refreshing Twitch VOD information.
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
import pytz

import twitch_api
from resumable_upload import ResumableUpload
from youtube_auth import init_google_session

from upload import quick_upload_video

from state import check_in_progress_uploads, move_video_to_uploaded_folder
from state import check_vod_uploaded

from config import config

from logs import setup_logger

# Command Line Arguments
DRY_RUN_ENABLED = "--dry-run" in sys.argv
DEBUG_ENABLED = "--debug" in sys.argv

MATCH_VODS_ONLY = "--match-vods-only" in sys.argv
IGNORE_FILE_SIZE_AND_AGE = "--no-size-age" in sys.argv

# Google APIs reset quota at midnight PT
pacific_tz = pytz.timezone("America/Los_Angeles")


ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

STATE_FILE_PATH = ROOT_DIR + "/data/state.json"
CONFIG_FILE_PATH = ROOT_DIR + "/data/config.json"
UPLOAD_HISTORY_PATH = ROOT_DIR + "/data/upload_history.txt"

logger = setup_logger(debug_enabled=DEBUG_ENABLED)


def watch_recordings_folder(google: dict):
    """
    Watches the recodings folder for new video files to show up that need to be uploaded.
    Once a Twitch VOD corresponding to a video file is found, the video is uploaded using
    the metadata from the Twitch VOD as it's own.

    Refreshes the Twitch VOD information every twitch_vod_refresh_rate seconds (specified in config.json).
    If no YouTube API quota remains, sleeps until midnight PT (+ 10 minutes to be safe).
    """

    logger.debug(f"config: {config}")

    folder_to_move_completed_uploads = config["folder_to_move_completed_uploads"]

    check_interval = config["check_folder_interval"]

    if not os.path.isdir(folder_to_move_completed_uploads):
        os.mkdir(folder_to_move_completed_uploads)

    twitch_videos = get_twitch_vod_information()

    checks_count = 0

    while 1:

        videos_needing_upload: dict = {}

        if checks_count * config["check_folder_interval"] >= config["twitch_vod_refresh_rate"]:

            logger.debug(f"Refreshing twitch vods {checks_count}")

            twitch_videos = [
                vid for vid in twitch_api.fetch_videos()
                if twitch_api.get_video_duration(vid) > config["twitch_video_duration_threshold"]
            ]
            checks_count = 0

        video_files: set = get_valid_videos_in_watch_folder()

        for file_path in video_files:
            file_modified_time = os.path.getmtime(file_path)
            vod = match_video_with_vod(file_path, file_modified_time, twitch_videos)

            vod_tstamp = twitch_api.get_video_timestamp(vod)

            if check_vod_uploaded(vod["id"]):
                print_video_vod_info("VIDEO UPLOADED PREVIOUSLY", file_path, file_modified_time, vod["title"], vod_tstamp, vod["id"])
                logger.info(f"Video was already uploaded: {vod['id']}. Moving to uploaded folder.")
                move_video_to_uploaded_folder(file_path)

            elif file_path not in videos_needing_upload:
                print_video_vod_info("ADDING VIDEO", file_path, file_modified_time, vod["title"], vod_tstamp, vod["id"])
                videos_needing_upload[file_path] = vod

        logger.debug(f"Files that should be uploaded: {json.dumps(videos_needing_upload, indent=4)}")

        for video_path in videos_needing_upload:
            video_meta = videos_needing_upload[video_path]

            logger.debug(f"Uploading: {video_path}\nwith VOD: {video_meta}")

            if not DEBUG_ENABLED:
                logger.info(f"Uploading: {video_path}\nwith VOD: {video_meta['title']}\n")

            try:
                quick_upload_video(google, video_path, video_meta, DRY_RUN_ENABLED=DRY_RUN_ENABLED)
            except ResumableUpload.ExceededQuota:
                time_until_reset = get_time_until_quota_reset()

                local_reset = datetime.now() + time_until_reset
                logger.warning(f"The daily quota limit has been reached.")
                logger.info(f"Sleeping until midnight Pacific Time ({pretty_print_time(local_reset)} local time)")
                time.sleep(time_until_reset.total_seconds())

        time.sleep(check_interval)

        checks_count += 1


def get_valid_videos_in_watch_folder() -> set:
    folder_to_watch = config["folder_to_watch"]
    file_size_threshold = config["file_size_threshold"]
    file_age_threshold = config["file_age_threshold"]

    video_files = set(
        os.path.join(folder_to_watch, path) for path in os.listdir(folder_to_watch)
        if os.path.isfile(os.path.join(folder_to_watch, path)) and path.endswith(".mp4")
    )

    def filter_videos(file_path):
        # File creation time isn't used here because unix
        file_modified_time = os.path.getmtime(file_path)
        file_modified_relative = time.time() - file_modified_time
        file_size = os.path.getsize(file_path)

        logger.debug(f"{file_path}: {file_modified_time} | {file_modified_relative} | {file_size}")

        meets_file_size = file_size >= file_size_threshold
        meets_file_age = file_modified_relative >= file_age_threshold

        if not (meets_file_size and meets_file_age) and not IGNORE_FILE_SIZE_AND_AGE:
            return False
        else:
            return True

    return set(filter(filter_videos, video_files))


def match_video_with_vod(file_path, file_modified_time, twitch_vods):
    for video in twitch_vods:
        vid_tstamp = twitch_api.get_video_timestamp(video)
        vid_duration = twitch_api.get_video_duration(video)

        # The start date and time of the VOD minus a bit of padding for margin of error
        min_video_start_date = (vid_tstamp - config["file_modified_start_max_delta"])

        # The end date and time of the VOD plus a bit of padding for margin of error
        max_video_end_date = (vid_tstamp + (vid_duration + config["file_modified_end_max_delta"]))

        # Check if the current VOD and video start and end near eachother
        if file_modified_time >= min_video_start_date and file_modified_time < max_video_end_date:
            return video

    return None


def get_twitch_vod_information():
    """Retrieves and filters VOD information for the channel specified in config.json"""
    twitch_retries = 10

    for i in range(twitch_retries):
        try:
            return [
                vid for vid in twitch_api.fetch_videos()
                if twitch_api.get_video_duration(vid) > config["twitch_video_duration_threshold"]
            ]
        except twitch_api.TwitchAPIError as e:
            logger.error(f"Twitch API request unsuccessful ({e})")
            if i + 1 == twitch_retries:
                logger.critical(f"\nUnable to fetch twitch vod information after {twitch_retries} retries...")
                sys.exit(1)
                # raise
            else:
                time_to_sleep = (i + 1) * 60
                logger.info(f"Trying again in {time_to_sleep} seconds")
                time.sleep(time_to_sleep)


def get_time_until_quota_reset():
    """Calculates the amount of time until midnight Pacific Time (+ 10 minutes to be safe)"""

    dt = datetime.now().astimezone(pacific_tz)
    quota_reset = (dt + timedelta(days=1)).replace(hour=0, minute=10, second=0).astimezone(pacific_tz)

    time_to_quota_reset = quota_reset - dt

    if DEBUG_ENABLED:
        logger.debug(f"current time: {dt}")
        logger.debug(f"quota reset: {quota_reset}")
        logger.debug(f"time to quota reset: {time_to_quota_reset}")

    return time_to_quota_reset


def pretty_print_time(dt):
    return dt.strftime('%I:%M %p').lstrip("0")


def print_video_vod_info(message, video_path, video_modified, vod_title, vod_date_created, vod_id):
    logger.info(f"""
    --- {message} ---
    | VOD ID:         {vod_id}
    | Video Path:     {video_path}
    | VOD Title:      {vod_title.encode('utf8')}
    | Video Modified: {video_modified}
    | VOD Timestamp:  {vod_date_created}\n""")


def match_vods_only():
    videos_needing_upload: dict = {}
    videos_not_matched: list = []
    videos_already_uploaded: list = []

    twitch_videos = get_twitch_vod_information()
    video_files: set = get_valid_videos_in_watch_folder()

    folder_to_watch = config["folder_to_watch"]
    file_count = len([
        f for f in os.listdir(folder_to_watch)
        if os.path.isfile(os.path.join(folder_to_watch, f)) and f.endswith(".mp4")
    ])

    for file_path in video_files:
        file_modified_time = os.path.getmtime(file_path)
        vod = match_video_with_vod(file_path, file_modified_time, twitch_videos)

        if vod:
            vod_tstamp = twitch_api.get_video_timestamp(vod)

            if check_vod_uploaded(vod["id"]):
                print_video_vod_info("VIDEO UPLOADED PREVIOUSLY", file_path, file_modified_time, vod["title"], vod_tstamp, vod["id"])
                logger.info(f"Video was already uploaded: {vod['id']}. File will be moved to uploaded folder on the next real run.")
                # move_video_to_uploaded_folder(file_path)
                videos_already_uploaded.append(file_path)

            elif file_path not in videos_needing_upload:
                print_video_vod_info("ADDING VIDEO", file_path, file_modified_time, vod["title"], vod_tstamp, vod["id"])
                videos_needing_upload[file_path] = vod
        else:
            videos_not_matched.append(file_path)

    logger.info(f"{len(videos_needing_upload)}/{file_count} video(s) were added to upload queue")
    logger.info(f"{len(videos_already_uploaded)}/{file_count} video(s) were already uploaded")

    full_video_text = "\n    ".join(videos_not_matched)
    logger.info(f"{len(videos_not_matched)}/{file_count} video(s) were not added to queue: \n    {full_video_text}")


def main():
    if DRY_RUN_ENABLED:
        logger.warning("[DRY RUN] Dry run enabled. Nothing will be uploaded")
        logger.warning("[DRY RUN] Dry run enabled. Nothing will be uploaded")

    google = init_google_session()
    for file_path, twitch_vod, upload_url in check_in_progress_uploads():
        quick_upload_video(google, file_path, twitch_vod, upload_url, DRY_RUN_ENABLED=DRY_RUN_ENABLED)

    logger.info("Watching recordings folder...")
    watch_recordings_folder(google)


if __name__ == "__main__":

    logger.info("Starting up...")

    if MATCH_VODS_ONLY:
        match_vods_only()
    else:
        main()

    # save_in_progress_upload("googleapis.com/1232847827381", ROOT_DIR + "/videos/vid.mp4", {
    #     "title": "Speedrun of GTAV Classic% - what could possibly go wrong! (hint - everything) - !songrequest theme - Jazz & Blues",
    #     "description": "",
    #     "url": "https://www.twitch.tv/videos/426700335",
    #     "id": "426700335"
    # })

    # remove_in_progress_upload("426700335")
