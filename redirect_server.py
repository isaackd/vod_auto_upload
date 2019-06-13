#!/usr/bin/python3

# Simple server to receive the authorization code from Google after the user is redirected

import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

from config import config

host_name = config["redirect_host"]
host_port = config["redirect_port"]

server_should_stop = False

class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global server_should_stop

        query_part = self.path.split("?")
        query_params = {}
        if len(query_part) >= 2:
            qp_pairs = query_part[1].split("&")
            for key, value in (pair.split("=") for pair in qp_pairs):
                query_params[key] = value
        else:
            return

        request_state = query_params["state"]

        if "error" in query_params:
            self.send_response(400)
            self.wfile.write(f"Authorization must be provided in order to upload videos on your behalf".encode("utf-8"))
            self.received_callback(None)
            server_should_stop = True
        elif self.path.startswith("/submit_credentials") and self.state_code == request_state:
            self.send_response(200)
            self.wfile.write(f"Received access token. This window can now be closed".encode("utf-8"))
            self.received_callback(self.path)
            server_should_stop = True
        else:
            self.send_response(400)
            self.wfile.write(f"Bad Request".encode("utf-8"))

    def log_message(self, format, *args):
        return

def wait_for_auth_redirection(state_code, callback, after_server_start, *args):
    my_server = HTTPServer((host_name, host_port), MyHandler)
    print(time.asctime(), "Server Start - %s:%s" % (host_name, host_port))

    after_server_start(*args)

    my_server.RequestHandlerClass.received_callback = callback
    my_server.RequestHandlerClass.state_code = state_code

    while not server_should_stop:
        my_server.handle_request()

    my_server.server_close()
    print(time.asctime(), "Server Stop - %s:%s" % (host_name, host_port))