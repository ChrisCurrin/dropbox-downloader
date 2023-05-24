import argparse
import logging
import math
import os
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


def formatBytes(bytes):
    """function returns formatted bytes"""
    if bytes == 0:
        return "0B"
    suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    index = int(math.floor(math.log(bytes, 1024)))
    formatted = round(float(bytes) / (1024**index), 2)
    return f"{formatted} {suffixes[index]}"


def downloadFile(suppliedLink: str, destination: str, unzip=False, retain_zip=False):
    parsedURL = urlparse(suppliedLink)

    # check if link belongs to www.dropbox.com
    if not parsedURL.netloc == DOMAIN:
        logger.error(f"{suppliedLink} does not belong to {DOMAIN}, skipping it ")
        return

    # add query to make link downloadable as zip
    zippedDownloadURL = urlunparse(parsedURL._replace(query="dl=1"))
    logger.info(f"Downloading from URL : {suppliedLink}")

    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=RETRIES))

        try:
            zipFileResp = session.get(
                zippedDownloadURL,
                headers={"User-Agent": WGET_AGENT},
                timeout=60,
                stream=True,
            )
            start_time = time.time()
            zipFileResp.raise_for_status()

        except requests.exceptions.ConnectionError:
            logger.error(f"Unable to retrieve {suppliedLink}, due to network error")
            return

        except requests.exceptions.Timeout:
            logger.error(f"Unable to retrieve {suppliedLink}, connection timed out")
            return

        except requests.exceptions.HTTPError as err:
            logger.error(f"{err}")
            return

        # get filename from response headers
        zipFilename = (
            zipFileResp.headers["content-disposition"].split(";")[1].split('"')[1]
        )
        # get file size from response headers
        zipFileSize = float(zipFileResp.headers.get("content-length", 0))
        formattedZipFileSize = formatBytes(zipFileSize)
        # path to store the file
        filePath = os.path.join(destination, zipFilename)
        # path to store file with temporary filename
        tempFilePath = os.path.join(destination, f"{zipFilename}.part")
        Path(destination).mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading file : {zipFilename}")

        currentSize = 0
        try:
            chunk_size = 2**20
            with open(tempFilePath, "wb") as zipFile:  # write file to disk
                for chunk in tqdm(
                    zipFileResp.iter_content(chunk_size=chunk_size),
                    total=math.ceil(zipFileSize // chunk_size),
                    unit="MB",
                    unit_scale=True,
                    postfix=f"{formattedZipFileSize}",
                    desc=f"{suppliedLink} -> {tempFilePath}",
                ):
                    if chunk:
                        currentSize += len(chunk)
                        zipFile.write(chunk)
                        # zipFile.flush()
                        # os.fsync(zipFile.fileno())

        except KeyboardInterrupt:
            logger.error("Interrupted by user, removing incomplete file")
            try:
                os.remove(tempFilePath)
            except OSError:
                logger.error(f"Unable to remove {tempFilePath}")
                pass
            exit()

        # print messaage when download is over
        if os.stat(tempFilePath).st_size == zipFileSize:
            os.rename(tempFilePath, filePath)
            elapsedTime = timedelta(seconds=time.time() - start_time)
            logger.info(
                f"Downloaded {suppliedLink} to {filePath} in"
                f" {elapsedTime}"
            )

    # if unzip argument is used unzip files
    if unzip:
        with zipfile.ZipFile(filePath, "r") as zipFile:
            directoryName = zipFilename.replace(".zip", "")
            directoryPath = os.path.join(destination, directoryName)
            os.makedirs(directoryPath, exist_ok=True)
            zipFile.extractall(directoryPath)

        logger.info(f"Extracted {filePath} to {directoryPath}")

        # check if zip files should be deleted
        if not retain_zip:
            os.remove(filePath)
            logger.info(f"Removed {filePath}")


def downloadFiles(suppliedLinks: list[str], destination, unzip=False, retain_zip=False):
    for suppliedLink in suppliedLinks:
        downloadFile(suppliedLink, destination, unzip, retain_zip)


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
        suppliedLinks = list(dict.fromkeys(arguments.links))
    else:
        # read given file and add each line to list
        with arguments.read as file:
            suppliedLinks = file.read().splitlines()

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
    downloadFiles(
        suppliedLinks,
        destination,
        unzip=arguments.unzip,
        retain_zip=arguments.retain_zip,
    )
