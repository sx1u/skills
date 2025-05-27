import scrapetube
import requests
from bs4 import BeautifulSoup
import yt_dlp
import os

def find_channel_id(url):
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.content, 'html.parser')
        metas = soup.find_all('meta')
        for meta in metas:
            if meta.get('itemprop') == 'channelId':
                return meta['content']
        return 0
    except:
        return 0

def get_videos_from_channel(id):
    try:
        videos = scrapetube.get_channel(id)
        urls = []
        counter = 0
        for video in videos:
            url = f"https://www.youtube.com/watch?v={video['videoId']}"
            title = video['title']['runs'][0]['text']
            urls.append({'url': url, 'title': title, 'counter': counter})
            counter += 1
        return urls
    except:
        return 0

def find_videos_with_search(word, number):
    urls = []
    counter = 1
    try:
        videos = scrapetube.get_search(word)
        for video in videos:
            url = f"https://www.youtube.com/watch?v={video['videoId']}"
            title = video['title']['runs'][0]['text']
            urls.append({'url': url, 'title': title, 'counter': counter})
            counter += 1
            if counter > int(number):
                break
        return urls
    except:
        return 0

def get_available_qualities(link):
    """
    Returns list like ['2160p@60fps', '1440p@60fps', '1080p@60fps']
    by checking actual stream formats from yt-dlp.
    """
    try:
        ydl_opts = {'quiet': True, 'skip_download': True, 'cookiefile': 'cookies.txt'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            formats = info.get("formats", [])
            resolutions = set()
            for fmt in formats:
                if fmt.get("vcodec", "none") != "none":
                    height = fmt.get("height")
                    fps = fmt.get("fps")
                    if height and fps:
                        label = f"{height}p@{int(fps)}fps"
                        resolutions.add(label)
            return sorted(resolutions, key=lambda x: int(x.split('p')[0]), reverse=True)
    except Exception as e:
        print(f"Error while getting qualities: {e}")
        return []

def Download(link, user_id, mode='video', resolution='720p@30fps'):
    """
    Downloads video/audio from YouTube using yt-dlp and returns (file_path, size_in_MB)
    """
    output_path = f'Downloads/{user_id}'
    os.makedirs(output_path, exist_ok=True)

    try:
        if mode == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{output_path}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'cookiefile': 'cookies.txt',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            height = resolution.split('p')[0]
            fps = resolution.split('@')[1].replace('fps', '')

            ydl_opts = {
                'format': f'bestvideo[height={height}][fps={fps}]+bestaudio/best',
                'outtmpl': f'{output_path}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'cookiefile': 'cookies.txt',
                'merge_output_format': 'mp4',
                'noplaylist': True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            file_path = ydl.prepare_filename(info)
            if mode == 'audio':
                file_path = os.path.splitext(file_path)[0] + ".mp3"

            size_in_mb = os.path.getsize(file_path) / (1024 * 1024)
            return file_path, round(size_in_mb, 2)

    except Exception as e:
        print(f"yt-dlp download error: {e}")
        return 0, 0
