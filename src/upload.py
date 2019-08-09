"""Higher level functions for starting video uploads."""

import os

from resumable_upload import ResumableUpload
from state import mark_twitch_vod_as_uploaded, move_video_to_uploaded_folder
from state import save_in_progress_upload, remove_in_progress_upload

import logging
logger = logging.getLogger()


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


def upload_video(google_session: dict, video_path: str, twitch_video: dict, progress_callback=None, upload_url: str = None, DRY_RUN_ENABLED=False):
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
                remove_in_progress_upload(twitch_video["id"])
                return response
            else:
                raise ResumableUpload.ReachedRetryMax
        except ResumableUpload.ReachedRetryMax:
            logger.error("Reached the maximum amount of retries", exc_info=True)
        except ResumableUpload.ExceededQuota:
        	raise
        except Exception as e:
        	logger.error(f"An error occurred while uploading {video_path}.", exc_info=True)
        	logger.info("The upload will try to be resumed on next start...")
    else:
        logger.info(f"[DRY RUN] Video would now be uploaded in a real run:\n    video path: {video_path}\n    twitch video: {twitch_video}\n    upload url: {upload_url}")
        # save_in_progress_upload("https://example.org", video_path, twitch_video)
        # time.sleep(5)
        # remove_in_progress_upload(twitch_video["id"])


def quick_upload_video(google_session: dict, video_path: str, video_meta: dict = None, upload_url: str = None, DRY_RUN_ENABLED=False):
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

    res = upload_video(google_session, video_path, video_meta, progress_callback=prog, upload_url=upload_url, DRY_RUN_ENABLED=DRY_RUN_ENABLED)
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
