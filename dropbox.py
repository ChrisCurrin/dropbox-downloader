import argparse
import logging
import math
import os
import sys
import textwrap
import time
import zipfile
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3 import Retry

# config
DOMAIN = "www.dropbox.com"
WGET_AGENT = "Wget/1.19.4 (linux-gnu)"
RETRIES = Retry(total=10, backoff_factor=2)
ERASE = "\033[2K"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dropbox-downloader")


# helper function


def format_bytes(bytes):
    """function returns formatted bytes"""
    if bytes == 0:
        return "0B"
    suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    index = int(math.floor(math.log(bytes, 1024)))
    formatted = round(float(bytes) / (1024**index), 2)
    return f"{formatted} {suffixes[index]}"


def download_file(
    link: str, destination: str | Path = ".", unzip=False, retain_zip=False
):
    parsed_URL = urlparse(link)
    destination = Path(destination)

    # check if link belongs to www.dropbox.com
    if not parsed_URL.netloc == DOMAIN:
        logger.error(f"{link} does not belong to {DOMAIN}, skipping it ")
        return

    # add/edit query to make link downloadable as zip
    query = parsed_URL.query
    query = query.replace("dl=0", "dl=1")
    if not query.endswith("dl=1"):
        if query:
            # multiple query parameters (non-empty query string)
            query += "&"
        query += "dl=1"
    zipped_download_URL = urlunparse(parsed_URL._replace(query=query))
    logger.info(f"Downloading from URL : {zipped_download_URL}")

    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=RETRIES))

        try:
            zip_file_resp = session.get(
                link.replace("dl=0", "dl=1"),
                headers={"User-Agent": WGET_AGENT},
                timeout=60,
                stream=True,
            )
            start_time = time.time()
            zip_file_resp.raise_for_status()

        except requests.exceptions.ConnectionError:
            logger.error(f"Unable to retrieve {link}, due to network error")
            return

        except requests.exceptions.Timeout:
            logger.error(f"Unable to retrieve {link}, connection timed out")
            return

        except requests.exceptions.HTTPError as err:
            logger.error(f"{err}")
            return

        if len(destination.parts) == 1:
            zip_file_name = str(destination)
            destination = Path.cwd()  # current directory
        else:
            # get filename from response headers
            try:
                zip_file_name = (
                    zip_file_resp.headers["content-disposition"]
                    .split(";")[1]
                    .split('"')[1]
                )
            except KeyError:
                zip_file_name = "dropbox.zip"

        # get file size from response headers
        zip_file_size = float(zip_file_resp.headers.get("content-length", 0))
        fmt_zip_file_size = format_bytes(zip_file_size)
        # path to store the file
        file_path = (destination.resolve() / zip_file_name).with_suffix(".zip")
        # path to store file with temporary filename
        temp_file_path = file_path.with_suffix(".zip.part")
        Path(destination).mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading file : {zip_file_name}")

        short_link = textwrap.shorten(zipped_download_URL, width=50, placeholder="...")
        short_file_path = textwrap.shorten(str(temp_file_path), width=50, placeholder="...")

        current_size = 0
        try:
            chunk_size = 2**20
            with open(temp_file_path, "wb") as zipFile:  # write file to disk
                for chunk in tqdm(
                    zip_file_resp.iter_content(chunk_size=chunk_size),
                    # total=math.ceil(zip_file_size // chunk_size),
                    unit="MB",
                    unit_scale=True,
                    postfix=f"{fmt_zip_file_size}",
                    desc=f"{short_link} -> {short_file_path}",
                ):
                    if chunk:
                        current_size += len(chunk)
                        zipFile.write(chunk)
                        # zipFile.flush()
                        # os.fsync(zipFile.fileno())

        except KeyboardInterrupt:
            logger.error("Interrupted by user, removing incomplete file")
            try:
                os.remove(temp_file_path)
            except OSError:
                logger.error(f"Unable to remove {temp_file_path}")
                pass
            sys.exit(0)

    # print messaage when download is over
    if os.stat(temp_file_path).st_size == zip_file_size:
        temp_file_path.replace(file_path)
        elapsed_time = timedelta(seconds=time.time() - start_time)
        logger.info(f"Downloaded {link} to {file_path} in" f" {elapsed_time}")

    # if unzip argument is used unzip files
    if unzip:
        with zipfile.ZipFile(file_path, "r") as zipFile:
            directory_name = zip_file_name.replace(".zip", "")
            directory_path = destination / directory_name
            directory_path.mkdir(parents=True, exist_ok=True)
            zipFile.extractall(directory_path)

        logger.info(f"Extracted {file_path} to {directory_path}")

        # check if zip files should be deleted
        if not retain_zip:
            os.remove(file_path)
            logger.info(f"Removed {file_path}")


def download_files(links: list[str], destination, unzip=False, retain_zip=False):
    for suppliedLink in links:
        download_file(suppliedLink, destination, unzip, retain_zip)


if __name__ == "__main__":
    # argument parser
    argsParser = argparse.ArgumentParser(
        description="python script to download dropbox public folders as zip files"
    )
    groupArgsParser = argsParser.add_mutually_exclusive_group()
    groupArgsParser.add_argument(
        "--links", type=str, nargs="+", const=None, help="download links"
    )
    groupArgsParser.add_argument(
        "--read",
        metavar="file.txt",
        type=argparse.FileType("r", encoding="UTF-8"),
        const=None,
        help="read file and download included links",
    )
    argsParser.add_argument(
        "--dest", type=str, default=os.getcwd(), help="specify download directory"
    )
    argsParser.add_argument(
        "--unzip",
        action="store_true",
        help="unzip downloaded zipfiles into folders and delete zipfiles",
    )
    argsParser.add_argument(
        "--retain_zip",
        action="store_true",
        help="don't delete zipfiles after unzipping when --unzip is used",
    )
    arguments = argsParser.parse_args()  # use this to access supplied arguments

    # check if argument is supplied, if not, exit
    if not (arguments.read or arguments.links):
        logger.error("No options specified, use --help for available options")
        exit()

    if arguments.links:
        # convert the supplied links into list
        links = list(dict.fromkeys(arguments.links))
    else:
        # read given file and add each line to list
        with arguments.read as file:
            links = file.read().splitlines()

    # destination folder supplied by the user
    destination = arguments.dest
    logger.info(f"Specified download location: {destination}")

    # check if unzip argument is supplied
    if arguments.unzip:
        if arguments.retain_zip:
            logger.info("zipfiles will not be deleted after unzipping")
        elif not arguments.retain_zip:
            logger.info(
                "--unzip was used without --retain_zip, "
                "zipfiles will be deleted after unzipping"
            )

    # download files
    download_files(
        links,
        destination,
        unzip=arguments.unzip,
        retain_zip=arguments.retain_zip,
    )
