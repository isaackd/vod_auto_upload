import requests
import math
import time
import os
import random
import json

class ResumableUpload():

    class ReachedRetryMax(Exception):
        pass

    class ExceededQuota(Exception):
        pass

    def __init__(self, video_metadata: dict, file_handle, chunk_size=None, session=requests.Session(), upload_url: str = None):
        self.video_metadata = video_metadata
        self.file_handle = file_handle

        self.max_retries = 4
        self.retries = 0

        self.session = session

        self.file_size = os.path.getsize(self.file_handle.name)

        # cap chunk size at 512MiB
        self.chunk_size = chunk_size if chunk_size else min(self.file_size / 10, 536_870_912)
        self.chunk_size = 262144 * round(self.chunk_size / 262144)
        print("Chunk Size:", self.chunk_size)

        self.upload_url = self.request_upload_url() if not upload_url else upload_url

        self.success_statuses = (200, 201)
        self.retry_statuses = (500, 502, 503, 504)

        self.uploaded_bytes = 0

    def request_upload_url(self):

        params = {"uploadType": "resumable", "part": "id,status,snippet"}

        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(self.file_size),
            "X-Upload-Content-Type": "video/*"
        }

        for i in range(self.max_retries):
            try:
                r = self.session.post(
                    "https://www.googleapis.com/upload/youtube/v3/videos", 
                    data=json.dumps(self.video_metadata), 
                    params=params,
                    headers=headers
                )

                if r.status_code == 200 and "Location" in r.headers:
                    upload_url = r.headers["Location"]
                    print(f"Received upload url: {upload_url}")

                    headers = {
                        "Content-Length": str(self.chunk_size),
                        "Content-Type": "video/*",
                    }

                    return upload_url
                elif r.status_code == 403:
                    raise ResumableUpload.ExceededQuota("Exceeded quota")
                else:
                    print(f"Server responded unsuccessfully ({r.status_code}) while requesting upload url. Retrying...")
                    try:
                        error_message = r.json()["error"]["errors"][0]["message"]
                        print("Reason:", error_message)
                    except Exception:
                        pass

            except Exception as e:
                if isinstance(e, ResumableUpload.ExceededQuota):
                    raise e
                print("Error while requesting upload url. Retrying...:", e)
                sleep_seconds = self.get_next_retry_sleep()
                time.sleep(sleep_seconds)

    def get_upload_status(self):
        headers = {"Content-Length": "0", "Content-Range": f"bytes */{self.file_size}"}
        for i in range(self.max_retries):
            try:
                with self.session.put(self.upload_url, headers=headers) as response:
                    return response
            except Exception as e:
                print("Error while requesting upload status. Retrying...:", e)
                sleep_seconds = self.get_next_retry_sleep()
                time.sleep(sleep_seconds)
                self.sync_with_upload_status()

    def sync_with_upload_status(self, status_response=None):

        if not status_response:
            status_response = self.get_upload_status()

        if status_response.status_code not in self.success_statuses:
            if "Range" in status_response.headers:
                range_header = status_response.headers["Range"]
                uploaded_amount = int(range_header.split("-", maxsplit=1)[1])

                self.uploaded_bytes = uploaded_amount + 1
                print("Synced upload with server:", self.uploaded_bytes, range_header)
            else:
                self.uploaded_bytes = 0

    def get_next_retry_sleep(self):
        self.retries += 1

        print(f"Retries: {self.retries}, Max: {self.max_retries}")

        if self.retries > self.max_retries:
            raise ResumableUpload.ReachedRetryMax(f"Unable to upload video after {self.retries} retries.")

        max_sleep = 2 ** self.retries
        sleep_seconds = random.random() * max_sleep

        return sleep_seconds

    def upload(self, progress_callback=None):

        upload_status = self.get_upload_status()
        self.sync_with_upload_status(upload_status)

        if upload_status.status_code in self.success_statuses:
            print("The file has already been uploaded")
            return upload_status
        else:
            for status, response in self.upload_next_chunk():
                if progress_callback:
                    progress_callback(status, response, self.uploaded_bytes)

                if "Retry-After" in response.headers:
                    try:
                        print("Server response includes a \'Retry-After\' header. Waiting..")
                        sleep_length = int(response.headers["Retry-After"])
                        time.sleep(sleep_length)
                    except Exception as e:
                        print("Server response includes a \'Retry-After\' header, but there was an error parsing it. Waiting 20 seconds")
                        time.sleep(20)

                if status == 308:
                    print(f"Server is ready for next chunk ({status}). Uploading...")
                    self.sync_with_upload_status(response)

                elif status in self.success_statuses:
                    print("The file was successfully uploaded")
                    return response
                elif status in self.retry_statuses:
                    
                    sleep_seconds = self.get_next_retry_sleep()
                    print(f"The server responded with a {status}. Retrying in {sleep_seconds:.2f} seconds...")

                    time.sleep(sleep_seconds)
                    self.sync_with_upload_status()
                elif status == 404:
                    print(f"The server responded with a {status}. The upload session expired")
                    break
                else:
                    print(f"The server responded with a {status}. Unable to resume")
                    break

    def upload_next_chunk(self):
        self.file_handle.seek(self.uploaded_bytes)
        while self.uploaded_bytes < self.file_size:
            chunk = self.file_handle.read(self.chunk_size)
            chunk_len = len(chunk)
            print(f"Position in file: {self.file_handle.tell()}, Uploaded bytes: {self.uploaded_bytes}")
            if chunk:
                headers = {
                    "Content-Length": str(chunk_len),
                    "Content-Type": "video/*"
                }

                req = requests.Request("PUT", self.upload_url, data=chunk, headers=headers)
                del chunk
                prepped = self.session.prepare_request(req)

                prepped.headers["Content-Type"] = "video/*"
                prepped.headers["Content-Range"] = f"bytes {self.uploaded_bytes}-{(self.uploaded_bytes + chunk_len) - 1}/{self.file_size}"

                try:
                    response = self.session.send(prepped)
                    response.request.body = None

                    yield response.status_code, response

                    if response.status_code in self.success_statuses:
                        break

                except Exception as e:
                    print("There was an error while uploading video data. Retrying...")
                    sleep_seconds = self.get_next_retry_sleep()
                    time.sleep(sleep_seconds)
                    self.sync_with_upload_status()
            else:
                time.sleep(5)
                self.sync_with_upload_status()
