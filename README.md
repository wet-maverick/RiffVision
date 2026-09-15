# RiffVision

**Clone Hero background video downloader** — search YouTube, grab thumbnails, download `video.mp4` to your song folders, and auto-sync the video offset.

Built with Python + CustomTkinter. Handles YouTube's 2025/2026 EJS challenge solver requirement automatically.

---

## Features

- Scans your Clone Hero songs folder and shows your full library
- Filter by song/artist name, or toggle **"Missing video only"**
- Auto-searches YouTube using song metadata from `song.ini`
- Shows up to 8 results as thumbnail cards with title, channel, duration, and view count
- Downloads the video as `video.mp4` directly into the song folder — **always H.264, always Clone Hero compatible**
- Automatically detects the `video_start_time` offset via audio cross-correlation
- Manual offset slider (±15 seconds, 10ms steps) with fine-tune buttons
- Writes `video_start_time` back to `song.ini` on Apply
- Batch download mode — queue your entire missing-video library and walk away
- Settings panel — search template, max results, browser for cookies, and more
- First-run wizard installs Deno and ffmpeg automatically (no manual setup)
- yt-dlp auto-updates on launch so YouTube changes never break it

---

## Requirements

- **Python 3.10 or newer**
  Download: https://www.python.org/downloads/
  > On Windows: check **"Add Python to PATH"** during install

- **Internet connection** (for YouTube search and first-run dependency download)

That's it. Everything else is handled automatically.

---

## Installation

### Windows (recommended)

1. **Install Python 3.10+** from https://python.org — check "Add Python to PATH"

2. **Clone this repo:**
   Open Command Prompt (`Win + R` → type `cmd` → Enter) and run:
   ```
   git clone https://github.com/wet-maverick/RiffVision.git
   cd RiffVision
   ```
   > If you don't have Git: download it at https://git-scm.com and re-open cmd after installing.

3. **Run the app:**
   Double-click `run.bat`
   — or from Command Prompt inside the RiffVision folder:
   ```
   run.bat
   ```

   On first launch, `run.bat` installs Python dependencies automatically, then opens the app.

4. **First-run wizard:**
   - Confirm your songs folder path (default: `D:/CloneHeroSongs/`)
   - Click **"Install All"** — this downloads Deno and ffmpeg (~60MB total, one time only)
   - Click **"Continue"** when everything shows green

---

## Usage

### Downloading a video

1. **Select a song** from the library on the left
   - Use the filter box or "Missing video only" toggle to find songs that need videos

2. The app automatically searches YouTube using the song's artist and title
   - You can edit the search query and click **Search** to try different terms

3. Browse the result cards — each shows a thumbnail, title, channel, and duration

4. Click **"Download This Video"** on the card you want

5. The video downloads to the song's folder as `video.mp4`

### Syncing the offset

After download, the app automatically runs audio sync:

1. Switch to the **Sync & Offset** tab (opens automatically after download)
2. Review the detected offset and confidence level
3. Use the **slider** or **± buttons** to fine-tune if needed
4. Click **"Apply & Save to song.ini"**

Clone Hero will now play the video in sync with the chart.

### Re-running sync

Already have a video but the sync is off? Select the song — the Sync & Offset tab opens automatically with the current offset pre-loaded. Hit **Re-run Sync** or adjust the slider manually.

### Batch downloading

1. Go to the **Batch Download** tab
2. Click **Load Missing Songs** — fills a queue with every song that has no video
3. Click **Start Queue** — RiffVision auto-searches, downloads, and syncs each one
4. Pause or stop at any time. Right-click any row to skip or retry individual songs.

---

## Age-Restricted Videos

Some YouTube videos require you to be signed in to download them. If you see an error like **"Sign in to confirm your age"**, follow these steps:

### Fix it in 3 steps

1. **Open your browser** (Edge, Chrome, Firefox — whichever you use for YouTube)

2. **Sign into YouTube** at https://youtube.com — just make sure you're logged in

3. **Tell RiffVision which browser to use:**
   - Go to the **Settings** tab in RiffVision
   - Find **"Browser for cookies"**
   - Select your browser from the dropdown
   - Try the download again

RiffVision reads your browser's saved login cookies — no password is ever stored or sent anywhere. This is the same mechanism yt-dlp uses, which is the standard tool for this.

### Supported browsers
`Chrome` · `Edge` · `Firefox` · `Brave` · `Opera`

> **Note:** Edge is installed on every Windows 10/11 machine by default. If you don't want to use your main browser, just open Edge, go to youtube.com, and sign in there. Then select `edge` in Settings.

### If it still fails

Some videos are restricted to signed-in users with verified ages on the account. If the error persists after setting the browser:
- Try a different search result for the same song — there's often an alternate upload that isn't age-gated
- Search for a live version, lyric video, or fan-uploaded version instead

---

## How it Works

| Component | Technology |
|---|---|
| GUI | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| YouTube search & download | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| JS challenge solver | [Deno](https://deno.com) (auto-installed) |
| PO Token bypass | [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) |
| Audio sync | Cross-correlation via NumPy/SciPy + ffmpeg audio extraction |
| Video codec | H.264 (avc1) forced — guaranteed Clone Hero compatible |
| song.ini parsing | Python stdlib `configparser` |

---

## Troubleshooting

**"Deno install failed"**
Download Deno manually from https://deno.com and add it to your PATH. RiffVision will detect it automatically.

**"ffmpeg not found"**
Download ffmpeg from https://ffmpeg.org/download.html and add the `bin/` folder to your PATH.

**YouTube search returns no results / download fails**
yt-dlp updates frequently to keep up with YouTube changes. RiffVision auto-updates on launch, but you can also run:
```
pip install -U "yt-dlp[default]"
```

**Video downloads but doesn't play in Clone Hero (blank background)**
This shouldn't happen with RiffVision — it forces H.264 on every download. If you have an old `video.mp4` from another tool, delete it and re-download through RiffVision.

**Videos are slightly out of sync**
Use the manual slider in the **Sync & Offset** tab to fine-tune. Low-confidence sync results (< 55%) may need manual adjustment — this happens when the video uses a different mix or master than the chart's stems.

**The app won't open / crashes immediately**
Make sure you're running Python 3.10+:
```
python --version
```

**Age-restricted video won't download even after setting browser**
See the [Age-Restricted Videos](#age-restricted-videos) section above. Try a different search result — most popular songs have multiple uploads, and not all of them are age-gated.

---

## Project Structure

```
RiffVision/
├── main.py                  Entry point
├── requirements.txt         Python dependencies
├── run.bat                  Windows launcher
└── app/
    ├── setup/
    │   ├── dependency_check.py   Deno/ffmpeg detection & install
    │   └── first_run.py          First-run wizard + color palette + config
    ├── core/
    │   ├── song_scanner.py       Scans songs folder, parses song.ini
    │   ├── downloader.py         yt-dlp wrapper (search + download)
    │   ├── audio_sync.py         Cross-correlation offset detection
    │   └── ini_writer.py         Reads/writes video_start_time in song.ini
    └── ui/
        ├── main_window.py        Root CTk window + app state
        ├── banner.py             Animated header banner
        ├── library_panel.py      Song list with filter
        ├── search_panel.py       YouTube results grid
        ├── offset_panel.py       Sync result + manual slider
        ├── batch_panel.py        Batch download queue
        └── settings_panel.py     User preferences
```

---

## License

MIT — do whatever you want with it.

