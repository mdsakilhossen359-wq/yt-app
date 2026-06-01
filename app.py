from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import requests

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
# ইউটিউব এপিআই কি
YOUTUBE_API_KEY = "AIzaSyAj_ZB8TOSQViO5MYQAfYEnf-T9LlcuFks"

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

# ইউটিউব ভিডিও সার্চ রাউট
@app.route('/search')
def search():
    query = request.args.get('q', 'Bangla hit songs')
    page_token = request.args.get('pageToken', '')
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=12&q={query}&type=video&pageToken={page_token}&key={YOUTUBE_API_KEY}"
    try:
        r = requests.get(url).json()
        videos = []
        for item in r.get('items', []):
            # টাইটেল থেকে কোটেশন মার্ক সেফ করা হচ্ছে জাভাস্ক্রিপ্ট এরর এড়াতে
            safe_title = item['snippet']['title'].replace('"', '&quot;').replace("'", "&#39;")
            videos.append({
                "title": safe_title,
                "thumbnail": item['snippet']['thumbnails']['high']['url'],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
        return jsonify({"videos": videos, "nextPageToken": r.get('nextPageToken', '')})
    except Exception as e:
        return jsonify({"videos": [], "nextPageToken": ""})

# ভিডিও ইনফো এবং ব্রাউজার প্লে-লিংক জেনারেটর (সম্পূর্ণ ফিক্সড)
@app.route('/get_info', methods=['POST'])
def get_info():
    video_url = request.form.get('url')
    
    # ব্রাউজারে ডিরেক্ট প্লে করার উপযোগী এবং দ্রুত লোড হওয়ার অপশনস
    ydl_opts = {
        'quiet': True, 
        'noplaylist': True,
        'format': 'best[ext=mp4]/best', # অডিও+ভিডিও একসাথে আছে এমন এমপি৪ খুঁজবে
        'skip_download': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            play_url = None
            
            # প্রথম চয়েস: সরাসরি 'url' কি-তে ওয়ার্কিং স্ট্রিমিং লিংক আছে কিনা দেখা
            if info.get('url'):
                play_url = info.get('url')
            
            # দ্বিতীয় চয়েস: যদি না থাকে, তবে formats লিস্ট ফিল্টার করা
            elif 'formats' in info:
                # যেসব ফরম্যাটে অডিও ও ভিডিও দুটিই সচল এবং ext = mp4
                valid_formats = [
                    f for f in info['formats']
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none'
                ]
                if valid_formats:
                    # সবচেয়ে স্টেবল প্রথম লিংকটি নেবে
                    play_url = valid_formats[0].get('url')
                else:
                    play_url = info['formats'][0].get('url')

            if not play_url:
                return jsonify({"error": "No playable URL found"}), 400

            clean_title = info.get('title', 'Unknown Title').replace('"', '&quot;').replace("'", "&#39;")

            return jsonify({
                "title": clean_title, 
                "video_url": play_url, 
                "url": video_url
            })
        except Exception as e:
            print(f"yt-dlp error: {str(e)}") # সার্ভার লগে এরর ট্র্যাক করার জন্য
            return jsonify({"error": str(e)}), 500

# ভিডিও এবং অডিও ডাউনলোড রাউট
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

# ডাউনলোড করা ফাইলের তালিকা
@app.route('/get_downloads')
def get_downloads():
    try:
        files = os.listdir(DOWNLOAD_FOLDER)
    except:
        files = []
    return jsonify(files)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
                
