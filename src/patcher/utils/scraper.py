import asyncio
import subprocess
from html.parser import HTMLParser
from typing import List

from .exceptions import PatcherError
from .logger import LogMe


class SoftwareTitlesHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_target_ul = False
        self.in_li = False
        self.software_titles = []

    def handle_starttag(self, tag, attrs):
        if tag == "ul":
            # Check if this is the ul we are interested in
            for attr in attrs:
                if attr == ("id", "reference-1208__auto-update-list"):
                    self.in_target_ul = True

        if self.in_target_ul and tag == "li":
            self.in_li = True

    def handle_endtag(self, tag):
        if tag == "ul" and self.in_target_ul:
            self.in_target_ul = False
        if tag == "li" and self.in_li:
            self.in_li = False

    def handle_data(self, data):
        if self.in_li:
            self.software_titles.append(data.strip())

    def get_software_titles(self):
        return self.software_titles


class Scraper:
    def __init__(self):
        self.url = "https://learn-be.jamf.com/bundle/jamf-app-catalog/page/Patch_Management_Software_Titles.html"
        self.log = LogMe(self.__class__.__name__)

    async def fetch_html(self) -> str:
        curl_command = ["curl", "-s", self.url]

        process = await asyncio.create_subprocess_exec(
            *curl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            self.log.error(f"Curl command failed with error: {stderr.decode()}")
            raise PatcherError(f"Curl command failed with error: {stderr.decode()}")

        return stdout.decode()

    @staticmethod
    def parse_software_titles(html: str) -> List[str]:
        parser = SoftwareTitlesHTMLParser()
        parser.feed(html)
        return parser.get_software_titles()
