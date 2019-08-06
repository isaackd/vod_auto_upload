import os
import sys
import time
import json
from datetime import datetime, timedelta
import pytz

import twitch_api
from resumable_upload import ResumableUpload
from youtube_auth import init_google_session

from config import config

from logs import setup_logger

# Google APIs reset quota at midnight PT
pacific_tz = pytz.timezone("America/Los_Angeles")

DRY_RUN_ENABLED = "--dry-run" in sys.argv

DEBUG_ENABLED = "--debug" in sys.argv

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

STATE_FILE_PATH = ROOT_DIR + "/data/state.json"
CONFIG_FILE_PATH = ROOT_DIR + "/data/config.json"
UPLOAD_HISTORY_PATH = ROOT_DIR + "/data/upload_history.txt"

logger = setup_logger(debug_enabled=DEBUG_ENABLED)


def shorten_video_title(video_title: str) -> str:
    """
    YouTube video titles have a maximum length of
    100 characters (assuming english), while Twitch allows 140.
    Replaces the last 3 characters of a 100 length str with ellipsis (...).
    Also removes the string ' - !songrequest' if it's present.
    """

    if " - !songrequest" in video_title:
        video_title = video_title.split(" - !songrequest")[0]

    if len(video_title) > 100:
        video_title = video_title[0:97] + "..."

    return video_title


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


def upload_video(google_session: dict, video_path: str, twitch_video: dict, progress_callback=None, upload_url: str = None):
    """
    Starts a resumable upload, configures the metadata used for the YouTube video (given by twitch_video),
    and uploads the file at video_path.
    """

    def start_resumable_download(google_session: dict, video_path: str, video_metadata: dict, chunk_size=None, upload_url: str = None):
        if not os.path.isfile(video_path):
            logger.error(f"Invalid file path: {video_path}")
            return

        video = open(video_path, "rb")
        resumable_upload = ResumableUpload(video_metadata, video, chunk_size=chunk_size, upload_url=upload_url, session=google_session)
        return resumable_upload, video

    video_title = twitch_video["title"]
    if len(video_title) > 100:
        video_title = shorten_video_title(video_title)

    original_title = twitch_video["title"]
    twitch_url = twitch_video["url"]
    video_desc = f"{original_title}\nTwitch Video: {twitch_url}\n" + twitch_video["description"]

    video_meta = {
        "snippet": {
            "title": video_title,
            "description": video_desc,
            "categoryId": "20"
        },
        "status": {
            "privacyStatus": "unlisted"
        }
    }

    if not DRY_RUN_ENABLED:
        try:
            resumable_upload, video = start_resumable_download(google_session, video_path, video_meta, upload_url=upload_url)
            if resumable_upload.upload_url:
                save_in_progress_upload(resumable_upload.upload_url, video_path, twitch_video)
                response = resumable_upload.upload(progress_callback)
                video.close()
                return response
            else:
                raise ResumableUpload.ReachedRetryMax
        except ResumableUpload.ReachedRetryMax:
            logger.error("Reached the maximum amount of retries", exc_info=True)
        finally:
            remove_in_progress_upload(twitch_video["id"])
    else:
        logger.info(f"[DRY RUN] Video would now be uploaded in a real run:\n    video path: {video_path}\n    twitch video: {twitch_video}\n    upload url: {upload_url}")
        # save_in_progress_upload("https://example.org", video_path, twitch_video)
        # time.sleep(5)
        # remove_in_progress_upload(twitch_video["id"])


def quick_upload_video(google_session: dict, video_path: str, video_meta: dict = None, upload_url: str = None):
    """Handles starting a resumable upload automatically, and just uploads a video with the given metadata"""

    file_size = os.path.getsize(video_path)

    def prog(status, response, uploaded_bytes):
        prog = (uploaded_bytes / file_size) * 100
        logger.info(f"[PROGRESS] status: {status} {prog:.2f}%")
        # print(f"[PROGRESS] status: {status} {response.headers} {response.content}\nREQUEST HEADERS: {response.request.headers}")

    if not video_meta:
        video_meta = {
            "title": "Speedrun of GTAV Classic% - what could possibly go wrong! (hint - everything) - !songrequest theme - Jazz & Blues",
            "description": "",
            "url": "https://www.twitch.tv/videos/426700335",
            "id": "426700335"
        }

    res = upload_video(google_session, video_path, video_meta, progress_callback=prog, upload_url=upload_url)
    if res and res.status_code in (200, 201):

        res_json = res.json()
        logger.info(f"Final response: {res_json}")

        title = res_json["snippet"]["title"]
        channel = res_json["snippet"]["channelTitle"]
        channel_id = res_json["snippet"]["channelId"]
        link = "https://youtube.com/watch?v=" + res_json["id"]
        privacy = res_json["status"]["privacyStatus"]
        published = res_json["snippet"]["publishedAt"]
        logger.info(f"\ntitle: {title}\nchannel: {channel} ({channel_id})\nlink: {link}\nprivacy: {privacy}\npublished: {published}")

        mark_twitch_vod_as_uploaded(video_meta["id"])
        move_video_to_uploaded_folder(video_path)
    else:
        logger.error(f"Unable to upload video: {video_path}")


def check_in_progress_uploads(google_session: dict):
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
                    quick_upload_video(google_session, file_path, entry["twitch_vod"], entry["upload_url"])
                else:
                    logger.error(f"File in incomplete upload no longer exists: {twitch_video_id} ({file_path})")


def watch_recordings_folder(google: dict):
    """
    Watches the recodings folder for new video files to show up that need to be uploaded.
    Once a Twitch VOD corresponding to a video file is found, the video is uploaded using
    the metadata from the Twitch VOD as it's own.

    Refreshes the Twitch VOD information every twitch_vod_refresh_rate seconds (specified in config.json).
    If no YouTube API quota remains, sleeps until midnight PT (+ 10 minutes to be safe).
    """

    logger.debug(f"config: {config}")

    folder_to_watch = config["folder_to_watch"]
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

        video_files = set(
            os.path.join(folder_to_watch, path) for path in os.listdir(folder_to_watch)
            if os.path.isfile(os.path.join(folder_to_watch, path)) and path.endswith(".mp4")
        )

        for file_path in video_files:

            file_modified_time = os.path.getmtime(file_path)
            file_modified_relative = time.time() - file_modified_time
            file_size = os.path.getsize(file_path)

            logger.debug(f"{file_path}: {file_modified_time} | {file_modified_relative} | {file_size}")

            if 1 or file_size >= config["file_size_threshold"] and file_modified_relative >= config["file_age_threshold"]:

                for video in twitch_videos:
                    vid_tstamp = twitch_api.get_video_timestamp(video)
                    vid_duration = twitch_api.get_video_duration(video)

                    # file creation time isn't used here because unix
                    if file_modified_time >= (vid_tstamp - config["file_modified_start_max_delta"]) and file_modified_time < (vid_tstamp + (vid_duration + config["file_modified_end_max_delta"])):
                        print_video_vod_info("ADDING VIDEO", file_path, file_modified_time, video["title"], vid_tstamp, video["id"])
                        if check_vod_uploaded(video["id"]):
                            logger.info(f"Video was already uploaded: {video['id']}. Moving to uploaded folder.")
                            move_video_to_uploaded_folder(file_path)
                            break
                        if file_path not in videos_needing_upload:
                            videos_needing_upload[file_path] = video
                            break

        logger.debug(f"Files that should be uploaded: {json.dumps(videos_needing_upload, indent=4)}")

        for video_path in videos_needing_upload:
            video_meta = videos_needing_upload[video_path]

            logger.debug(f"Uploading: {video_path}\nwith VOD: {video_meta}")

            if not DEBUG_ENABLED:
                logger.info(f"Uploading: {video_path}\nwith VOD: {video_meta['title']}\n")

            try:
                quick_upload_video(google, video_path, video_meta)
            except ResumableUpload.ExceededQuota:
                time_until_reset = get_time_until_quota_reset()

                local_reset = datetime.now() + time_until_reset
                logger.warning(f"The daily quota limit has been reached.")
                logger.info(f"Sleeping until midnight Pacific Time ({pretty_print_time(local_reset)} local time)")
                time.sleep(time_until_reset.total_seconds())

        time.sleep(check_interval)

        checks_count += 1


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
    | VOD Title:      {vod_title}
    | Video Modified: {video_modified}
    | VOD Timestamp:  {vod_date_created}\n""")


def move_video_to_uploaded_folder(video_path):
    os.rename(video_path, config["folder_to_move_completed_uploads"] + "/" + os.path.basename(video_path))


if __name__ == "__main__":

    logger.info("Starting up...")

    if DRY_RUN_ENABLED:
        logger.warning("[DRY RUN] Dry run enabled. Nothing will be uploaded")
        logger.warning("[DRY RUN] Dry run enabled. Nothing will be uploaded")

    google = init_google_session()
    check_in_progress_uploads(google)
    watch_recordings_folder(google)

    # save_in_progress_upload("googleapis.com/1232847827381", ROOT_DIR + "/videos/vid.mp4", {
    #     "title": "Speedrun of GTAV Classic% - what could possibly go wrong! (hint - everything) - !songrequest theme - Jazz & Blues",
    #     "description": "",
    #     "url": "https://www.twitch.tv/videos/426700335",
    #     "id": "426700335"
    # })

    # remove_in_progress_upload("426700335")
