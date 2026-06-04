from flask import Flask, render_template, request, jsonify, send_from_directory, Response, redirect, url_for, session
import yt_dlp
import os
import threading
import requests
from google_auth_oauthlib.flow import Flow

# ওঅথ (OAuth) সেশন প্রোটোকল সচল করা
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
# অ্যাপের সেশন সিকিউর রাখার জন্য একটি সিক্রেট কি
app.secret_key = "MY_SUPER_SECRET_MUSIC_APP_KEY_2026" 

DOWNLOAD_FOLDER = 'downloads'
YOUTUBE_API_KEY = "AIzaSyAj_ZB8TOSQViO5MYQAfYEnf-T9LlcuFks"

# 🔴 আপনার গুগল ক্লাউড ক্রেডেনশিয়ালস (আপনার আইডি নিচে যুক্ত করা হয়েছে)
CLIENT_ID = "187272375748-r72s3bf81b5fcj8isf9hk7a72adm2tar.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"  # ← এখানে আপনার গোপন Client Secret-টি বসিয়ে দিন
REDIRECT_URI = "https://web-production-da519.up.railway.app/callback"

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

download_status = {"status": "idle", "progress": 0, "speed": "0 KB/s", "eta": "00:00", "filename": ""}
cancel_event = threading.Event()

def get_ytdl_opts(access_token=None):
    """ইউজারের ওঅথ টোকেন দিয়ে yt-dlp রিকোয়েস্ট হেডার কনফিগার করা"""
    opts = {
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web_embedded'],
                'skip': ['webpage', 'player']
            }
        }
    }
    # ইউজার লগইন থাকলে কুকিজের বদলে টোকেন পাঠানো হবে, যা ব্লক খাবে না
    if access_token:
        opts['http_headers'] = {
            'Authorization': f'Bearer {access_token}'
        }
    return opts

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

def run_download(video_url, quality, access_token):
    global download_status
    cancel_event.clear()
    
    q_map = {
        '1080p': 'bv*[height<=1080]+ba/b[height<=1080]',
        '720p': 'bv*[height<=720]+ba/b[height<=720]',
        'mp3': 'ba/b'
    }

    ydl_opts = get_ytdl_opts(access_token)
    ydl_opts.update({
        'format': q_map.get(quality, 'b'),
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'progress_hooks': [ytdl_hook]
    })
    
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
        download_status['status'] = 'error'
        download_status['progress'] = 0

# 🔐 গুগল লগইন শুরু করার রুট
@app.route('/login')
def login():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

# 🔄 গুগল ভেরিফিকেশন শেষে ফিরে আসার রুট (Callback)
@app.route('/callback')
def callback():
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI, state=session.get('state'))
    flow.fetch_token(authorization_response=request.url)
    
    credentials = flow.credentials
    session['access_token'] = credentials.token
    return redirect(url_for('index'))

@app.route('/')
def index():
    # ইউজার লগইন না থাকলে তাকে প্রথমে গুগল সাইন-ইন পেজে পাঠানো হবে
    if 'access_token' not in session:
        return redirect(url_for('login'))
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
            if 'videoId' in item['id']:
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
    access_token = session.get('access_token')
    
    ydl_opts = get_ytdl_opts(access_token)
    ydl_opts['format'] = 'best'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            raw_url = info.get('url') or info.get('formats', [{}])[0].get('url')
            
            if not raw_url:
                return jsonify({"error": "ভিডিও ইউআরএল জেনারেট করা যায়নি।"}), 500
            
            proxy_play_url = f"/stream_proxy?url={requests.utils.quote(raw_url)}"
            return jsonify({"title": info.get('title', 'Video'), "video_url": proxy_play_url, "url": video_url})
    except Exception as e:
        return jsonify({"error": "লগইন সেশন শেষ, দয়া করে পেজটি রিফ্রেশ বা পুনরায় লগইন করুন।"}), 500

@app.route('/stream_proxy')
def stream_proxy():
    target_url = request.args.get('url')
    if not target_url:
        return "Missing URL", 400
        
    req_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Range': request.headers.get('Range', '')
    }
    try:
        r = requests.get(target_url, headers=req_headers, stream=True, timeout=15)
        response_headers = {
            'Content-Type': r.headers.get('Content-Type', 'video/mp4'),
            'Content-Length': r.headers.get('Content-Length', ''),
            'Accept-Ranges': 'bytes'
        }
        if r.headers.get('Content-Range'):
            response_headers['Content-Range'] = r.headers.get('Content-Range')
            
        def generate():
            for chunk in r.iter_content(chunk_size=512*1024):
                yield chunk
        return Response(generate(), status=r.status_code, headers=response_headers)
    except:
        return "Streaming Error", 500

@app.route('/start_download')
def start_download_route():
    global download_status
    video_url = request.args.get('url')
    quality = request.args.get('quality', '720p')
    access_token = session.get('access_token')
    
    if download_status['status'] == 'downloading':
        return jsonify({"error": "একটি ডাউনলোড ইতিমধ্যে চলছে!"}), 400
        
    download_status = {"status": "downloading", "progress": 0, "speed": "0 KB/s", "eta": "00:00", "filename": ""}
    threading.Thread(target=run_download, args=(video_url, quality, access_token)).start()
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

@app.route('/get_downloads'):
def get_downloads():
    try:
        files = os.listdir(DOWNLOAD_FOLDER)
        return jsonify(files)
    except:
        return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
    
