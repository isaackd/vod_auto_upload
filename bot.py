import os
import time
import json

import twitch_api
from resumable_upload import ResumableUpload
from youtube_auth import init_google_session

from config import config

def shorten_video_title(video_title):
    if " - !songrequest" in video_title:
        video_title = video_title.split(" - !songrequest")[0]

    if len(video_title) > 100:
        video_title = video_title[0:97] + "..."

    return video_title

def upload_video(google_session, video_path: str, twitch_video: dict, progress_callback=None, upload_url=None):

    def start_resumable_download(google_session, video_path: str, video_metadata: dict, chunk_size=None, upload_url=None):
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

    try:
        resumable_upload, video = start_resumable_download(google_session, video_path, video_meta, upload_url=upload_url)
        response = resumable_upload.upload(progress_callback)
        video.close()
        return response
    except ResumableUpload.ReachedRetryMax as e:
        print(e)
        print("Reached the maximum amount of retries")



def test_upload_vid(google_session, video_path: str):

    file_size = os.path.getsize(video_path)
    def prog(status, response, uploaded_bytes):
        prog = (uploaded_bytes / file_size) * 100
        print(f"[PROGRESS] status: {status} {prog:.2f}%")
        # print(f"[PROGRESS] status: {status} {response.headers} {response.content}\nREQUEST HEADERS: {response.request.headers}")

    res = upload_video(google, video_path, {
        "title": "Speedrun of GTAV Classic% - what could possibly go wrong! (hint - everything) - !songrequest theme - Jazz & Blues",
        "description": "",
        "url": "https://www.twitch.tv/videos/426700335"
    }, prog)
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
    else:
        print("Unable to upload video:", video_path)



if __name__ == "__main__":

    # google = init_google_session()

    # if google:
    #     test_upload_vid(google, video_path)
    # else:
    #     print("Unable to get initialize a Google session")


    print("config:", config)

    folder_to_watch = config["folder_to_watch"]
    folder_to_move_completed_uploads = config["folder_to_move_completed_uploads"]

    check_interval = config["check_folder_interval"]

    if not os.path.isdir(folder_to_move_completed_uploads):
        os.mkdir(folder_to_move_completed_uploads)

    if not os.path.isfile("config.json"):
        with open("config.json", "w") as file:
            file.write(json.dumps(DEFAULT_CONFIG, indent=4))

    videos_needing_upload = set()

    twitch_videos = twitch_api.fetch_videos()

    while 1:

        video_files = set(
            os.path.join(folder_to_watch, path) for path in os.listdir(folder_to_watch) 
            if os.path.isfile(os.path.join(folder_to_watch, path))
            and path.endswith(".mp4")
        )
        
        for file_path in video_files:

            file_modified_time = os.path.getmtime(file_path)
            file_modified_relative = time.time() - file_modified_time
            file_size = os.path.getsize(file_path)

            # print(f"{file_path}: {file_modified_time} | {file_modified_relative} | {file_size}")

            # TODO: REMOVE 1 FOR USED FOR TESTING
            if 1 or file_size >= config["file_size_threshold"] and file_modified_relative >= config["file_age_threshold"]:

                for video in twitch_videos:
                    vid_tstamp = twitch_api.get_video_timestamp(video)
                    vid_duration = twitch_api.get_video_duration(video)

                    if vid_duration < config["twitch_video_duration_threshold"]:
                        continue

                    # file creation time isn't used here because unix
                    if file_modified_time >= (vid_tstamp - config["file_modified_start_max_delta"]) and file_modified_time < (vid_tstamp + (vid_duration + config["file_modified_end_max_delta"])):
                        print("adding video", file_path, "with clip", video["title"])
                        if not file_path in videos_needing_upload:
                            videos_needing_upload.add(file_path)
                            break


        print("Files that should be uploaded:", videos_needing_upload)
        print()

        time.sleep(check_interval)