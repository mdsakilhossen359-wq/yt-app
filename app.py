from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import requests

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
# মনে রাখবেন: এই এপিআই কি-টি পাবলিকলি শেয়ার করা নিরাপদ নয়। প্রোডাকশনে এটি .env ফাইলে রাখা উচিত।
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
                "title": item['snippet']['title'].replace('"', '&quot;').replace("'", "&#39;"),
                "thumbnail": item['snippet']['thumbnails']['high']['url'],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
        return jsonify({"videos": videos, "nextPageToken": r.get('nextPageToken', '')})
    except:
        return jsonify({"videos": [], "nextPageToken": ""})

# ভিডিও ইনফো এবং প্লে লিংক জেনারেটর (ফিক্সড)
@app.route('/get_info', methods=['POST'])
def get_info():
    video_url = request.form.get('url')
    # ১৮০ বা ৭২০ পিক্সেলের কম্বাইন্ড ফরম্যাট খোঁজার চেষ্টা করবে
    ydl_opts = {
        'quiet': True, 
        'noplaylist': True,
        'format': 'best[ext=mp4]/best' 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            formats = info.get('formats', [])
            
            # অডিও এবং ভিডিও উভয়ই আছে এমন ডিরেক্ট mp4 লিংক খোঁজা হচ্ছে
            play_url = None
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                    play_url = f.get('url')
                    break
            
            if not play_url:
                play_url = info.get('url')

            return jsonify({
                "title": info.get('title', 'Unknown Title').replace('"', '&quot;').replace("'", "&#39;"), 
                "video_url": play_url, 
                "url": video_url
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# ভিডিও ডাউনলোড
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
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
    }
    
    if quality == 'mp3':
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info)
            if quality == 'mp3': 
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return send_file(filename, as_attachment=True)
        except Exception as e:
            return f"ডাউনলোড ব্যর্থ হয়েছে: {str(e)}", 500

# ডাউনলোড ফাইল লিস্ট
@app.route('/get_downloads')
def get_downloads():
    try:
        files = os.listdir(DOWNLOAD_FOLDER)
    except:
        files = []
    return jsonify(files)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    
