import os
import asyncio
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from multiprocessing import Process
import websockets
from datetime import datetime
import json
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "message_db")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logging.info(f"Connecting to MongoDB at {MONGO_URI}")


class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/":
            self.send_html_file("index.html")
        elif parsed_url.path == "/message.html":
            self.send_html_file("message.html")
        elif parsed_url.path.startswith("/static/"):
            self.send_static_file(parsed_url.path[1:])
        else:
            self.send_html_file("error.html", 404)

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        parsed_data = parse_qs(post_data.decode("utf-8"))
        username = parsed_data.get("username", [None])[0]
        message = parsed_data.get("message", [None])[0]

        if not username or not message:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid request data")
            return

        message_data = json.dumps({"username": username, "message": message})

        async def send_message():
            uri = "ws://localhost:6000"
            async with websockets.connect(uri) as websocket:
                await websocket.send(message_data)

        asyncio.run(send_message())

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Message successfully sent!")

    def send_html_file(self, filename, status=200):
        try:
            with open(filename, "rb") as file:
                self.send_response(status)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(file.read())
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")

    def send_static_file(self, filename, status=200):
        try:
            with open(filename, "rb") as file:
                self.send_response(status)
                if filename.endswith(".css"):
                    self.send_header("Content-type", "text/css")
                elif filename.endswith(".png"):
                    self.send_header("Content-type", "image/png")
                self.end_headers()
                self.wfile.write(file.read())
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")


class WebSocketServer:
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[MONGO_DB]
        self.collection = self.db["messages"]

    async def ws_handler(self, websocket):
        async for message in websocket:
            data = json.loads(message)
            logging.info(f"Received message: {data}")
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

            message_data = {
                "date": date,
                "username": data["username"],
                "message": data["message"],
            }
            try:
                self.collection.insert_one(message_data)
                logging.info(f"Saved message: {message_data}")
            except Exception as e:
                logging.error(f"Failed to insert message: {e}")


async def run_websocket_server():
    server = WebSocketServer()
    async with websockets.serve(server.ws_handler, "0.0.0.0", 6000):
        logging.info("WebSocket server started on port 6000")
        await asyncio.Future()


def start_websocket_server():
    asyncio.run(run_websocket_server())


def run_http_server():
    server_address = ("", 3000)
    httpd = HTTPServer(server_address, HttpHandler)
    logging.info("HTTP server started on port 3000")
    httpd.serve_forever()


if __name__ == "__main__":
    http_process = Process(target=run_http_server)
    ws_process = Process(target=start_websocket_server)

    http_process.start()
    ws_process.start()

    http_process.join()
    ws_process.join()
