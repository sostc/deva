---
name: "video-downloader"
description: "Download videos from various websites using yt-dlp. Use when users provide a video link and want to download it, or when they need to download videos from platforms like YouTube, Bilibili, TikTok, and more."
---

# Video Downloader

This skill uses yt-dlp to download videos from thousands of websites. It supports various video platforms including YouTube, Bilibili, TikTok, Twitter, and many more.

## When to Use

Use this skill when:
- User provides a video link and wants to download it
- User needs to download videos from any supported website
- User wants to save videos for offline viewing
- User needs to download multiple videos or playlists

## Dependencies

- **yt-dlp**: The core tool for downloading videos
- **ffmpeg** (recommended): For merging separate video and audio files, and for post-processing tasks
- **Python 3.10+**: Required to run yt-dlp

## Installation

### Install yt-dlp

**Using pip:**
```bash
pip install yt-dlp
```

**Using standalone executable:**
- Download the appropriate binary from [yt-dlp GitHub releases](https://github.com/yt-dlp/yt-dlp/releases)
- For Windows: `yt-dlp.exe`
- For macOS: `yt-dlp_macos`
- For Linux: `yt-dlp` (platform-independent zipimport binary)

### Install ffmpeg (Recommended)

- **Windows**: Download from [FFmpeg官网](https://ffmpeg.org/download.html) and add to PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) or equivalent for other distributions

## Usage

### Basic Download

To download a video, simply provide the video URL:

```bash
yt-dlp [VIDEO_URL]
```

### Download Options

- **Specify output format**: `yt-dlp -f [FORMAT] [VIDEO_URL]`
- **Download best quality**: `yt-dlp -f best [VIDEO_URL]`
- **Download playlist**: `yt-dlp [PLAYLIST_URL]`
- **Limit download rate**: `yt-dlp --limit-rate [RATE] [VIDEO_URL]` (e.g., 500K)
- **Resume interrupted download**: `yt-dlp -c [VIDEO_URL]`
- **Download only audio**: `yt-dlp -x [VIDEO_URL]`
- **Embed subtitles**: `yt-dlp --embed-subs [VIDEO_URL]`

### Advanced Options

- **Custom output filename**: `yt-dlp -o "%(title)s.%(ext)s" [VIDEO_URL]`
- **Download specific playlist items**: `yt-dlp --playlist-items 1,3,5 [PLAYLIST_URL]`
- **Download with proxy**: `yt-dlp --proxy [PROXY_URL] [VIDEO_URL]`
- **Bypass geo-restrictions**: `yt-dlp --geo-verification-proxy [PROXY_URL] [VIDEO_URL]`

## Supported Websites

yt-dlp supports thousands of websites, including but not limited to:

- YouTube (including playlists, channels, and live streams)
- Bilibili
- TikTok
- Twitter/X
- Instagram
- Facebook
- Vimeo
- Dailymotion
- Twitch (including VODs and clips)
- and many more

## Examples

### Example 1: Download a YouTube video
```bash
yt-dlp https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### Example 2: Download a Bilibili video with best quality
```bash
yt-dlp -f best https://www.bilibili.com/video/BV1xx411c7mW
```

### Example 3: Download a playlist
```bash
yt-dlp https://www.youtube.com/playlist?list=PLQVvvaa0QuDfKTOs3Keq_kaG2P55YRn5v
```

### Example 4: Download only audio
```bash
yt-dlp -x https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## Troubleshooting

- **Video not downloading**: Check if the URL is correct and the video is publicly accessible
- **Slow download speed**: Use `--limit-rate` to avoid throttling, or try a different network
- **Geo-restricted content**: Use a proxy with `--proxy` or `--geo-verification-proxy`
- **Missing dependencies**: Install ffmpeg for better compatibility with various video formats

## Notes

- Always respect copyright laws and terms of service of the websites you download from
- Use this tool only for personal, non-commercial purposes
- Large playlists may take significant time and bandwidth to download
- Some websites may have anti-scraping measures that could temporarily block your IP

## Update yt-dlp

To keep yt-dlp up-to-date with the latest features and bug fixes:

```bash
# Using pip
pip install --upgrade yt-dlp

# Using standalone executable
yt-dlp -U
```

For more detailed information, visit the [yt-dlp GitHub repository](https://github.com/yt-dlp/yt-dlp).
