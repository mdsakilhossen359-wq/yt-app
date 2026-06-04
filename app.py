from flask import Flask, render_template, request, jsonify, send_from_directory, Response
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

# 🛡️ কুকিজ ছাড়াই ইউটিউব ব্লকিং বাইপাস করার জন্য সবচেয়ে শক্তিশালী অপ্টিমাইজড ক্লায়েন্ট আর্গুমেন্ট
YTDL_CLIENT_ARGS = {
    'quiet': True,
    'noplaylist': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'android', 'web_embedded'],
            'skip': ['webpage', 'player']
        }
    }
}

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
    
    # রেডিমেড ফরম্যাট এভয়েড করে সহজ ভিডিও+অডিও কম্বিনেশন টার্গেট করা হয়েছে
    q_map = {
        '1080p': 'bv*[height<=1080]+ba/b[height<=1080]',
        '720p': 'bv*[height<=720]+ba/b[height<=720]',
        'mp3': 'ba/b'
    }

    ydl_opts = {
        'format': q_map.get(quality, 'b'),
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'progress_hooks': [ytdl_hook],
        **YTDL_CLIENT_ARGS
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

# 🛠️ [FIXED] ফরম্যাট এরর এড়াতে যেকোনো সচল সরাসরি ভিডিও/অডিও লিঙ্ক প্রক্সি করার লজিক
@app.route('/get_info', methods=['POST'])
def get_info():
    video_url = request.form.get('url')
    
    # রেলওয়েতে 'Format not available' এরর দূর করতে একদম ওপেন ফরম্যাট ফিল্টারিং
    ydl_opts = {
        'format': 'b/bv+ba', 
        'noplaylist': True,
        **YTDL_CLIENT_ARGS
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            
            # সরাসরি বেস্ট ইউআরএল তুলে আনা হচ্ছে
            raw_url = info.get('url') or info.get('formats', [{}])[0].get('url')
            
            if not raw_url:
                raise Exception("No streamable URL found")
            
            # প্রক্সি স্ট্রিমিং লিঙ্ক জেনারেশন
            proxy_play_url = f"/stream_proxy?url={requests.utils.quote(raw_url)}"
                
            return jsonify({"title": info['title'], "video_url": proxy_play_url, "url": video_url})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ⚡ [PROXY] রেলওয়ে আইপি দিয়ে ডাটা রিড করে বাফারিং ছাড়া প্লে করার স্ট্রিমার
@app.route('/stream_proxy')
def stream_proxy():
    target_url = request.args.get('url')
    if not target_url:
        return "Missing URL", 400
        
    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Range': request.headers.get('Range', '')
    }
    
    r = requests.get(target_url, headers=req_headers, stream=True)
    
    response_headers = {
        'Content-Type': r.headers.get('Content-Type', 'video/mp4'),
        'Content-Length': r.headers.get('Content-Length', ''),
        'Accept-Ranges': 'bytes'
    }
    if r.headers.get('Content-Range'):
        response_headers['Content-Range'] = r.headers.get('Content-Range')
        
    def generate():
        for chunk in r.iter_content(chunk_size=512*1024): # ৫১২ কেবি চাঙ্ক সাইজ দ্রুত লোডিং এর জন্য
            yield chunk
            
    return Response(generate(), status=r.status_code, headers=response_headers)

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

@app.route('/play_file/<filename>')
def play_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

@app.route('/get_downloads')
def get_downloads():
    files = os.listdir(DOWNLOAD_FOLDER)
    return jsonify(files)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
    
