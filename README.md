# EiMM-Hostbot

a

## Installation

Install Python 3.6 or greater. I would suggest setting up a virtualenv, but you do you.

Run `pip install -r pip-requirements.txt`.


## Setting up gspread

1. Create a new [Google Application](https://console.developers.google.com/apis/dashboard).
2. Enable the [Google Sheets API](https://console.developers.google.com/apis/library/sheets.googleapis.com) for your new application.
3. Create new Service Account credentials; visit the [Credentials page](https://console.developers.google.com/apis/api/sheets.googleapis.com/credentials) and click around. Click "Create Credentials" in the top bar, then select "Service Account Key." There's also a short tutorial in the [gspread documentation](https://gspread.readthedocs.io/en/latest/oauth2.html#using-signed-credentials) that has a few screenshots.
4. Fill in the New Service Account info as you wish.
5. Download the credentials JSON when prompted; store securely. Rename to `google_creds.json` and store in the `conf/` folder in this project. If you're forking this project, do NOT upload this file to github! Put it in your gitignore!


## Setting up the bot

You'll need to fill in `conf/settings.py` with your bot's settings. Do this. Don't ever upload it to github. Put it in your gitignore.
