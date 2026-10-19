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

### 4. Run build_release.bat (to make a new version for TTS)

Double-click **build_release.bat**. It reads everything in `scripts\input` and:

1. prints a summary (factions, detachments, cards, and the game-datacards data version) and
   stops with a clear message if anything doesn't add up, for example a zip with fewer cards
   than the data says it should have (just run pull_all.bat again);
2. names the release after the **game-datacards data version** the cards came from (e.g.
   `v981`), so the TTS dropdown always matches game-datacards. If that data version is
   already published it asks whether to **replace** it: say yes only when you've changed
   how the cards are built (a mod change) and want to republish the same data;
3. asks whether it should be the **latest**, which is the one TTS picks by
   default. Answer **n** if you want to try it in TTS first: it still appears in the TTS
   Dataset dropdown, it just isn't preselected. Make it latest later by editing `"latest"`
   in `11e-stratagems\versions.json`;
4. asks you to confirm, then builds `11e-stratagems\<data version>\` (about 260 files, ~40 MB)
   and adds it to `11e-stratagems\versions.json`.

### Data version vs mod version

- **Data version** (e.g. `v981`): game-datacards' own number for its data. It changes when
  they update the rules text. It's the release folder name and what the TTS dropdown shows.
- **Mod version** (e.g. `v0.3.1`): how this mod builds the cards. It's `MOD_VERSION` at the
  top of `tts\Stratagem_Bag_Builder.lua`; bump it whenever you change how cards are made.
  It doesn't get its own folder.

Both are shown, colour-coded, in the name of the bag TTS spawns. The data version is also
printed on the card back (a small "DATASET v981" plaque at the bottom), added by the build.

Each release holds one `_deck.png` sheet per detachment (all its cards in a grid), the card
back and a `manifest.json` listing every card. That's all TTS needs. Individual card images
aren't published, because nothing uses them and they'd more than double each release. If you
ever do want them, run `.venv\Scripts\python.exe -I scripts\build_release.py --with-cards`.

Some factions get their common name in TTS so players can find them, e.g. game-datacards'
"Asuryani" becomes "Aeldari". The list lives in `scripts\faction_names.json`; edit it to add
or change one. If game-datacards ever renames a faction so a rule no longer matches, the
build prints a warning.

## Known issues

- **TTS stops responding for a while when you click "Build Stratagem Bags".** Building all
  29 factions (about 1,200 cards) at once makes Windows show "Tabletop Simulator is not
  responding". Click **Wait**: it finishes and the bag appears. Not being fixed for now,
  since it only happens when building the bag, not when playing with it.

Nothing goes online until you **commit and push** the new folder and `versions.json`.
Use GitHub Desktop (or git) for that: the GitHub website only uploads 100 files at a time.
After pushing, GitHub can take a few minutes before the new version shows up in TTS.
