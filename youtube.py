import yt_dlp

def search_youtube(query: str, max_results=10):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
        'forcejson': True,
        'noplaylist': True,
        'skip_download': True,
        'dump_single_json': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f'ytsearch{max_results}:{query}', download=False)
        entries = result['entries']
        return [{
            'title': e['title'],
            'id': e['id'],
            'url': f"https://www.youtube.com/watch?v={e['id']}"
        } for e in entries]

def get_audio_url(video_url: str):
    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'skip_download': True,
        'forceurl': True,
        'default_search': 'ytsearch',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        if 'url' in info:
            return info['url']
        elif 'formats' in info:
            for f in info['formats']:
                if f.get('acodec', 'none') != 'none':
                    return f['url']
    return None