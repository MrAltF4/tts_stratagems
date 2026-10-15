# tts_stratagems
Automate the process for getting stratagems as cards within TTS

## How to use the tool

The pull tool downloads the stratagem cards for every faction from the
[game-datacards.eu](https://game-datacards.eu/image-generator) image generator. It does
the same thing as clicking "Generate" on that site yourself, once per faction, but it
does it for you in a hidden browser. You only need Windows and Python; you don't need to
know any programming.

### 1. Install Python (once)

1. Go to <https://www.python.org/downloads/> and click the big yellow
   **Download Python** button.
2. Open the file you downloaded.
3. On the **first screen** of the installer, tick the box at the bottom that says
   **Add python.exe to PATH**. This is the important bit: if you miss it, the tool can't
   find Python. (If you already installed Python without it, run the installer again,
   choose **Modify** or uninstall and reinstall, and make sure the box is ticked.)
4. Click **Install Now** and wait for it to finish.

### 2. Run setup.bat (once)

In the project folder, double-click **setup.bat**. A black window opens and:

- checks that Python is installed;
- creates a folder called `.venv` that holds the tool's own copy of the Python
  packages it needs, so it doesn't interfere with anything else on your computer;
- installs those packages;
- downloads a copy of the Chromium web browser for the tool to use (this can take a few
  minutes).

When it says **Setup finished**, press any key to close the window. You don't need to
run it again unless something changes in `requirements.txt`, though running it again
does no harm.

If it says Python can't be found, go back to step 1 and make sure you ticked
**Add python.exe to PATH**, then restart your computer and try again.

### 3. Run pull_all.bat (whenever you want fresh cards)

Double-click **pull_all.bat**. It goes through every faction one at a time and prints a
line for each as it saves it. A full run takes a while, so leave the window open until it
says **Done**. If any faction fails, it lists them at the end; just run it again later.

### Where the files go

Everything lands in the `scripts\input` folder inside the project. That folder is only
on your computer: it is never uploaded to GitHub.

For each faction you get two files, for example:

- `datacards_necrons.zip`: the same zip of card images you'd get by clicking
  "Generate" on the website.
- `datacards_necrons.source.json`: a small note recording where the cards came from,
  chiefly the **game-datacards data version** they were made from, when that faction's
  data was last updated, and how many stratagems and detachments to expect. This lets you
  tell later which version of the data a set of cards belongs to.
