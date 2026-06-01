from flask import Flask, render_template, request, send_file, jsonify, send_from_directory
import yt_dlp
import os
import time
import requests

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
YOUTUBE_API_KEY = "AIzaSyAj_ZB8TOSQViO5MYQAfYEnf-T9LlcuFks"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

# ইউটিউব ভিডিও সার্চ
@app.route('/search')
def search():
    query = request.args.get('q', 'Bangla hit songs')
    page_token = request.args.get('pageToken', '')
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=12&q={query}&type=video&pageToken={page_token}&key={YOUTUBE_API_KEY}"
    try:
        r = requests.get(url).json()
        videos = []
        for item in r.get('items', []):
            videos.append({
                "title": item['snippet']['title'],
                "thumbnail": item['snippet']['thumbnails']['high']['url'],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
        return jsonify({"videos": videos, "nextPageToken": r.get('nextPageToken', '')})
    except:
        return jsonify({"videos": [], "nextPageToken": ""})

# ভিডিও ইনফো এবং প্লে লিঙ্ক
@app.route('/get_info', methods=['POST'])
def get_info():
    video_url = request.form.get('url')
    ydl_opts = {'quiet': True, 'noplaylist': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            formats = info.get('formats', [])
            play_url = next((f['url'] for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4'), info.get('url'))
            return jsonify({"title": info['title'], "video_url": play_url, "url": video_url})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ভিডিও ডাউনলোড (ফাইলটি সার্ভারে জমা থাকবে)
@app.route('/download')
def download():
    video_url = request.args.get('url')
    quality = request.args.get('quality', '720p')
    
    q_map = {
        '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        'mp3': 'bestaudio/best'
    }

    ydl_opts = {
        'format': q_map.get(quality, 'best'),
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s', # টাইটেল অনুযায়ী সেভ হবে
    }
    
    if quality == 'mp3':
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)
        if quality == 'mp3': filename = filename.rsplit('.', 1)[0] + '.mp3'
        return send_file(filename, as_attachment=True)

# ডাউনলোড করা ফাইলগুলোর লিস্ট দেখা
@app.route('/get_downloads')
def get_downloads():
    files = os.listdir(DOWNLOAD_FOLDER)
    return jsonify(files)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    
