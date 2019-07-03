import os
import sys
import time
import json

import twitch_api
from resumable_upload import ResumableUpload
# from youtube_auth import init_google_session

from config import config

DRY_RUN_ENABLED = "--dry-run" in sys.argv or 1
# TODO: use logging for this
DEBUG_ENABLED = "--debug" in sys.argv or 1

ROOT_DIR = os.path.dirname(os.path.abspath(__file__ + "/.."))

STATE_FILE_PATH = ROOT_DIR + "/data/state.json"
CONFIG_FILE_PATH = ROOT_DIR + "/data/config.json"
UPLOAD_HISTORY_PATH = ROOT_DIR + "/data/upload_history.txt"

def shorten_video_title(video_title: str) -> str:
    if " - !songrequest" in video_title:
        video_title = video_title.split(" - !songrequest")[0]

    if len(video_title) > 100:
        video_title = video_title[0:97] + "..."

    return video_title


def mark_twitch_vod_as_uploaded(twitch_vod_id: str):
    if os.path.isfile(UPLOAD_HISTORY_PATH):
        with open(UPLOAD_HISTORY_PATH, "a") as file:
            file.write(twitch_vod_id + "\n")
    else:
        with open(UPLOAD_HISTORY_PATH, "w") as file:
            file.write(twitch_vod_id + "\n")


def check_vod_uploaded(twitch_vod_id: str) -> bool:
    if os.path.isfile(UPLOAD_HISTORY_PATH):
        with open(UPLOAD_HISTORY_PATH, "r") as file:
            for vod_id in file:
                if vod_id == twitch_vod_id:
                    return True

    return False


def save_in_progress_upload(upload_url: str, video_path: str, twitch_vod: dict):

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

    def start_resumable_download(google_session: dict, video_path: str, video_metadata: dict, chunk_size=None, upload_url: str = None):
        if not os.path.isfile(video_path):
            print("Invalid file path:", video_path)
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
            save_in_progress_upload(resumable_upload.upload_url, video_path, twitch_video)
            response = resumable_upload.upload(progress_callback)
            video.close()
            return response
        except ResumableUpload.ReachedRetryMax as e:
            print(e)
            print("Reached the maximum amount of retries")
        finally:
            remove_in_progress_upload(twitch_video["id"])
    else:
        print(f"[DRY RUN] Video would now be uploaded in a real run:\n    video path: {video_path}\n    twitch video: {twitch_video}\n    upload url: {upload_url}")
        save_in_progress_upload("https://example.org", video_path, twitch_video)
        time.sleep(5)
        remove_in_progress_upload(twitch_video["id"])


def quick_upload_video(google_session: dict, video_path: str, video_meta: dict = None, upload_url: str = None):

    file_size = os.path.getsize(video_path)

    def prog(status, response, uploaded_bytes):
        prog = (uploaded_bytes / file_size) * 100
        print(f"[PROGRESS] status: {status} {prog:.2f}%")
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
        print("Final response:", res_json)

        title = res_json["snippet"]["title"]
        channel = res_json["snippet"]["channelTitle"]
        channel_id = res_json["snippet"]["channelId"]
        link = "https://youtube.com/watch?v=" + res_json["id"]
        privacy = res_json["status"]["privacyStatus"]
        published = res_json["snippet"]["publishedAt"]
        print(f"\ntitle: {title}\nchannel: {channel} ({channel_id})\nlink: {link}\nprivacy: {privacy}\npublished: {published}")

        mark_twitch_vod_as_uploaded(video_meta["id"])

    else:
        print("Unable to upload video:", video_path)


def check_in_progress_uploads(google_session: dict):
    if os.path.isfile(STATE_FILE_PATH):
        with open(STATE_FILE_PATH, "r", encoding="utf8") as file:
            contents = json.loads(file.read())

            for twitch_video_id in contents:
                entry = contents[twitch_video_id]
                file_path = entry["video_path"]
                if os.path.isfile(file_path):
                    print(f"Resuming incomplete upload: {twitch_video_id} ({file_path})")
                    quick_upload_video(google_session, file_path, entry["twitch_vod"], entry["upload_url"])
                else:
                    print(f"File in incomplete upload no longer exists: {twitch_video_id} ({file_path})")


def watch_recordings_folder(google: dict):
    if DEBUG_ENABLED:
        print("config:", config)

    folder_to_watch = config["folder_to_watch"]
    folder_to_move_completed_uploads = config["folder_to_move_completed_uploads"]

    check_interval = config["check_folder_interval"]

    if not os.path.isdir(folder_to_move_completed_uploads):
        os.mkdir(folder_to_move_completed_uploads)

    videos_needing_upload: dict = {}

    twitch_videos = [
        vid for vid in twitch_api.fetch_videos() 
        if twitch_api.get_video_duration(vid) > config["twitch_video_duration_threshold"]
    ]

    checks_count = 0

    while 1:

        if checks_count * config["check_folder_interval"] >= config["twitch_vod_refresh_rate"]:
            if DEBUG_ENABLED:
                print("Refreshing twitch vods", checks_count)
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

            # print(f"{file_path}: {file_modified_time} | {file_modified_relative} | {file_size}")

            if file_size >= config["file_size_threshold"] and file_modified_relative >= config["file_age_threshold"]:

                for video in twitch_videos:
                    vid_tstamp = twitch_api.get_video_timestamp(video)
                    vid_duration = twitch_api.get_video_duration(video)

                    # file creation time isn't used here because unix
                    if file_modified_time >= (vid_tstamp - config["file_modified_start_max_delta"]) and file_modified_time < (vid_tstamp + (vid_duration + config["file_modified_end_max_delta"])):
                        # print("adding video", file_path, "with VOD", video["title"])
                        if check_vod_uploaded(video["id"]):
                            print(f"VIDEO WAS ALREADY UPLOADED:", video["id"])
                            break
                        if not file_path in videos_needing_upload:
                            videos_needing_upload[file_path] = video
                            break

        print("Files that should be uploaded:", videos_needing_upload)
        for video_path in videos_needing_upload:
            video_meta = videos_needing_upload[video_path]
            print("Uploading:", video_path + " with metadata:", video_meta)
            quick_upload_video(google, video_path, video_meta)
        print()

        time.sleep(check_interval)

        checks_count += 1


if __name__ == "__main__":

    if DRY_RUN_ENABLED:
        print("[DRY RUN] WARNING: Dry run enabled. Nothing will be uploaded")
        print("[DRY RUN] WARNING: Dry run enabled. Nothing will be uploaded")

    # save_in_progress_upload("googleapis.com/1232847827381", ROOT_DIR + "/videos/vid.mp4", {
    #     "title": "Speedrun of GTAV Classic% - what could possibly go wrong! (hint - everything) - !songrequest theme - Jazz & Blues",
    #     "description": "",
    #     "url": "https://www.twitch.tv/videos/426700335",
    #     "id": "426700335"
    # })

    # remove_in_progress_upload("426700335")


    # google = init_google_session()

    # check_in_progress_uploads(google)

    # if google:
    #     quick_upload_video(google, ROOT_DIR + "/videos/vid.mp4")
    # else:
    #     print("Unable to initialize a Google session")

    watch_recordings_folder(None)
