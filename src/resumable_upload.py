"""
Home of the ResumableUpload class used for starting a resumable upload on YouTube's
servers so that a video can then be uploaded to it.
"""

import requests
import time
import os
import random
import json

import logging
logger = logging.getLogger()


class ResumableUpload():
    """Handles starting a resumable upload with YouTube and uploading video data (in chunks) to the upload URL."""

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

        # Cap chunk size at 512MiB
        self.chunk_size = chunk_size if chunk_size else min(self.file_size / 10, 536_870_912)
        self.chunk_size = 262144 * round(self.chunk_size / 262144)
        logger.info(f"Resumable Upload Chunk Size: {self.chunk_size}")

        self.upload_url = self.request_upload_url() if not upload_url else upload_url

        self.success_statuses = (200, 201)
        self.retry_statuses = (500, 502, 503, 504)

        self.uploaded_bytes = 0

    def request_upload_url(self):
        """
        Requests a resumable URL to upload video data to.
        If successful, returns the URL as a str.
        When an error is encountered, retries self.max_retries times, eventually
        raising ResumableUpload.ReachedRetryMax if self.max_retries is exceeded.
        """

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
                    logger.info(f"Received upload url: {upload_url}")

                    headers = {
                        "Content-Length": str(self.chunk_size),
                        "Content-Type": "video/*",
                    }

                    return upload_url
                elif r.status_code == 403:
                    raise ResumableUpload.ExceededQuota("Exceeded quota")
                else:
                    logger.error(f"Server responded unsuccessfully ({r.status_code}) while requesting upload url. Retrying...")
                    try:
                        error_message = r.json()["error"]["errors"][0]["message"]
                        logger.error(f"Server Error Reason: {error_message}")
                    except Exception:
                        pass

            except Exception as e:
                if isinstance(e, ResumableUpload.ExceededQuota):
                    raise e
                sleep_seconds = self.get_next_retry_sleep()
                logger.error(f"Error while requesting upload url. Retrying in {sleep_seconds} seconds...")
                logger.debug("Request Upload URL error:", exc_info=True)
                time.sleep(sleep_seconds)

    def get_upload_status(self):
        """
        Returns a Requests Response with information such as the amount of bytes the server
        received from our last data upload.
        """

        headers = {"Content-Length": "0", "Content-Range": f"bytes */{self.file_size}"}
        for i in range(self.max_retries):
            try:
                with self.session.put(self.upload_url, headers=headers) as response:
                    return response
            except Exception:
                sleep_seconds = self.get_next_retry_sleep()
                logger.error(f"Error while requesting upload status. Retrying in {sleep_seconds} seconds...")
                logger.debug("Upload Status Error:", exc_info=True)
                time.sleep(sleep_seconds)
                self.sync_with_upload_status()

    def sync_with_upload_status(self, status_response=None):
        """
        Synchronizes the internal uploaded bytes amount with the amount of
        bytes that the server actually received.
        """

        if not status_response:
            status_response = self.get_upload_status()

        if status_response.status_code not in self.success_statuses:
            if "Range" in status_response.headers:
                range_header = status_response.headers["Range"]
                uploaded_amount = int(range_header.split("-", maxsplit=1)[1])

                self.uploaded_bytes = uploaded_amount + 1
                logger.info(f"Synced upload with server | uploaded bytes: {self.uploaded_bytes} | range header: {range_header}")
            else:
                self.uploaded_bytes = 0

    def get_next_retry_sleep(self) -> int:
        """Returns a length (in seconds) to sleep for that exponentially increases with each retry"""

        self.retries += 1

        logger.warning(f"Retries: {self.retries}, Max: {self.max_retries}")

        if self.retries > self.max_retries:
            raise ResumableUpload.ReachedRetryMax(f"Unable to upload video after {self.retries} retries.")

        max_sleep = 2 ** self.retries
        sleep_seconds = random.random() * max_sleep

        return sleep_seconds

    def upload(self, progress_callback=None):
        """
        Kicks off the actual upload. Checks the status of the upload after each chunk
        is uploaded, raising any errors and synchronizing with the server as needed.
        """

        upload_status = self.get_upload_status()
        self.sync_with_upload_status(upload_status)

        if upload_status.status_code in self.success_statuses:
            logger.info("The file has already been uploaded")
            return upload_status
        else:
            for status, response in self.upload_next_chunk():
                if progress_callback:
                    progress_callback(status, response, self.uploaded_bytes)

                if "Retry-After" in response.headers:
                    try:
                        sleep_length = int(response.headers["Retry-After"])
                        logger.info(f"Server response includes a \'Retry-After\' header ({sleep_length}). Waiting...")
                        time.sleep(sleep_length)
                    except Exception:
                        logger.warning("Server response includes a \'Retry-After\' header, but there was an error parsing it. Waiting 20 seconds")
                        time.sleep(20)

                if status == 308:
                    logger.info(f"Server is ready for next chunk ({status}). Uploading...")
                    self.sync_with_upload_status(response)

                elif status in self.success_statuses:
                    logger.info("The file was successfully uploaded")
                    return response
                elif status in self.retry_statuses:
                    sleep_seconds = self.get_next_retry_sleep()
                    logger.warning(f"The server responded with a {status}. Retrying in {sleep_seconds:.2f} seconds...")

                    time.sleep(sleep_seconds)
                    self.sync_with_upload_status()
                elif status == 404:
                    logger.error(f"The server responded with a {status}. The upload session expired")
                    break
                else:
                    logger.critical(f"The server responded with a {status}. Unable to resume")
                    break

    def upload_next_chunk(self):
        """Uploads chunks of the file (size according to self.chunk_size) to self.upload_url"""
        self.file_handle.seek(self.uploaded_bytes)
        while self.uploaded_bytes < self.file_size:
            chunk = self.file_handle.read(self.chunk_size)
            chunk_len = len(chunk)
            logger.debug(f"Position in file: {self.file_handle.tell()}, Uploaded bytes: {self.uploaded_bytes}")
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

                except Exception:
                    sleep_seconds = self.get_next_retry_sleep()
                    logger.error(f"There was an error while uploading video data. Retrying in {sleep_seconds} seconds...")
                    logger.debug("Upload Video Data Error:", exc_info=True)
                    time.sleep(sleep_seconds)
                    self.sync_with_upload_status()
            else:
                time.sleep(5)
                self.sync_with_upload_status()
