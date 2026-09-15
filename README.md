# RiffVision

**Clone Hero background video downloader** — search YouTube, grab thumbnails, download `video.mp4` to your song folders, and auto-sync the video offset.

Built with Python + CustomTkinter. Handles YouTube's 2025/2026 EJS challenge solver requirement automatically.

---

## Features

- Scans your Clone Hero songs folder and shows your full library
- Filter by song/artist name, or toggle **"Missing video only"**
- Auto-searches YouTube using song metadata from `song.ini`
- Shows up to 8 results as thumbnail cards with title, channel, duration, and view count
- Downloads the video as `video.mp4` directly into the song folder
- Automatically detects the `video_start_time` offset via audio cross-correlation
- Manual offset slider (±15 seconds, 10ms steps) with fine-tune buttons
- Writes `video_start_time` back to `song.ini` on Apply
- First-run wizard installs Deno and ffmpeg automatically (no manual setup)

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
   - Red dot = missing video | Green dot = video present
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

Already have a video but the sync is off? Select the song, go to **Sync & Offset**, and click **Re-run Sync**.

---

## How it Works

| Component | Technology |
|---|---|
| GUI | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| YouTube search & download | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| JS challenge solver | [Deno](https://deno.com) (auto-installed) |
| PO Token bypass | [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) |
| Audio sync | Cross-correlation via NumPy/SciPy + ffmpeg audio extraction |
| song.ini parsing | Python stdlib `configparser` |

---

## Troubleshooting

**"Deno install failed"**
Download Deno manually from https://deno.com and add it to your PATH. RiffVision will detect it automatically.

**"ffmpeg not found"**
Download ffmpeg from https://ffmpeg.org/download.html and add the `bin/` folder to your PATH.

**YouTube search returns no results / download fails**
yt-dlp updates frequently to keep up with YouTube changes. Run this to update:
```
pip install -U "yt-dlp[default]"
```

**Videos are slightly out of sync**
Use the manual slider in the **Sync & Offset** tab to fine-tune. Low-confidence sync results (< 55%) may need manual adjustment — this happens when the video uses a different mix or master than the stems.

**The app won't open / crashes immediately**
Make sure you're running Python 3.10+:
```
python --version
```

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
    │   └── first_run.py          First-run wizard + color palette
    ├── core/
    │   ├── song_scanner.py       Scans songs folder, parses song.ini
    │   ├── downloader.py         yt-dlp wrapper (search + download)
    │   ├── audio_sync.py         Cross-correlation offset detection
    │   └── ini_writer.py         Reads/writes video_start_time in song.ini
    └── ui/
        ├── main_window.py        Root CTk window + app state
        ├── library_panel.py      Song list with filter
        ├── search_panel.py       YouTube results grid
        └── offset_panel.py       Sync result + manual slider
```

---

## License

MIT — do whatever you want with it.
