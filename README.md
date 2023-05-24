# dropbox-downloader
python script to download publicly shared Dropbox folders into zip files

### This script can

* **download public Dropbox folders as zip files**
* **read links from a file**
* **unzip zip files into folders after download**

### Usage

`$ python dropbox.py --help`

```bash
optional arguments:

  -h, --help                show this help message and exit
  --links link1, link2...   download links
  --read file.txt           read file and download included links
  --dest DEST               specify download directory
  --unzip                   unzip downloaded zipfiles into folders and delete zipfiles
  --retain_zip              don't delete zipfiles after unzipping, when --unzip is used
  ```

### Example

`$ python dropbox.py --read links.txt --dest Downloads --unzip --retain_zip`

this command reads links from the file links.txt, downloads files into the Downloads folder, unzips downloaded zip files, but also keeps the downloaded zip files

**NOTE:** forked from a repo to teach themselves some python & git. 

## Development

this repo uses poetry for dependency management and building.

### Setup

`$ poetry install`
