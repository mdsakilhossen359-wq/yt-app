from flask import Flask, render_template, request, send_from_directory, jsonify, make_response
import yt_dlp
import os
import threading
import requests

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
YOUTUBE_API_KEY = "AIzaSyAj_ZB8TOSQViO5MYQAfYEnf-T9LlcuFks"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_status = {
    "status": "idle",
    "progress": 0,
    "speed": "0 KB/s",
    "eta": "00:00",
    "filename": ""
}
cancel_event = threading.Event()

def ytdl_hook(d):
    global download_status
    if cancel_event.is_set():
        raise Exception("Download cancelled by user")
    
    if d['status'] == 'downloading':
        download_status['status'] = 'downloading'
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            download_status['progress'] = round((downloaded / total) * 100, 2)
        
        download_status['speed'] = d.get('_speed_str', '0 KB/s')
        download_status['eta'] = d.get('_eta_str', '00:00')
    elif d['status'] == 'finished':
        download_status['status'] = 'completed'
        download_status['progress'] = 100

def run_download(video_url, quality):
    global download_status
    cancel_event.clear()
    
    q_map = {
        '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        'mp3': 'bestaudio/best'
    }

    ydl_opts = {
        'format': q_map.get(quality, 'best'),
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'restrictfilenames': True, 
        'progress_hooks': [ytdl_hook],
        'quiet': True
    }
    
    if quality == 'mp3':
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info)
            if quality == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            download_status['filename'] = os.path.basename(filename)
            download_status['status'] = 'completed'
            download_status['progress'] = 100
    except Exception as e:
        if "cancelled" in str(e):
            download_status['status'] = 'cancelled'
        else:
            download_status['status'] = 'error'
        download_status['progress'] = 0

@app.route('/')
def index():
    return render_template('index.html')

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

@app.route('/start_download')
def start_download_route():
    global download_status
    video_url = request.args.get('url')
    quality = request.args.get('quality', '720p')
    
    if download_status['status'] == 'downloading':
        return jsonify({"error": "একটি ডাউনলোড ইতিমধ্যে চলছে!"}), 400
        
    download_status = {"status": "downloading", "progress": 0, "speed": "0 KB/s", "eta": "00:00", "filename": ""}
    threading.Thread(target=run_download, args=(video_url, quality)).start()
    return jsonify({"message": "Download started"})

@app.route('/progress')
def progress():
    return jsonify(download_status)

@app.route('/cancel_download')
def cancel_download():
    global download_status
    cancel_event.set()
    download_status['status'] = 'cancelled'
    return jsonify({"message": "Download cancellation requested"})

@app.route('/play_file/<path:filename>')
def play_file(filename):
    response = make_response(send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True))
    response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
    response.headers["Content-Type"] = "application/octet-stream"
    return response

@app.route('/get_downloads')
def get_downloads():
    if os.path.exists(DOWNLOAD_FOLDER):
        files = [f for f in os.listdir(DOWNLOAD_FOLDER) if os.path.isfile(os.path.join(DOWNLOAD_FOLDER, f))]
    else:
        files = []
    return jsonify(files)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
    
