import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import yt_dlp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# ডাউনলোড করা ফাইলগুলো রাখার জন্য ফোল্ডার তৈরি
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

# ফোনের মেমোরিতে সরাসরি ফাইল ডাউনলোড করানোর রুট (as_attachment=True সহ)
@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

@app.route('/list-downloads')
def list_downloads():
    files = []
    if os.path.exists(DOWNLOAD_FOLDER):
        files = [f for f in os.listdir(DOWNLOAD_FOLDER) if os.path.isfile(os.path.join(DOWNLOAD_FOLDER, f))]
    return jsonify(files)

# yt-dlp এর মাধ্যমে ব্যাকগ্রাউন্ডে ভিডিও ডাউনলোড করার লজিক
@socketio.on('start_download')
def handle_download(data):
    url = data.get('url')
    if not url:
        emit('download_error', {'message': 'URL পাওয়া যায়নি!'})
        return

    def progress_hook(d):
        if d['status'] == 'downloading':
            # ডাউনলোডের শতকরা হার হিসাব করা
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = (downloaded / total) * 100
                emit('download_progress', {'percent': round(percent, 2)})
        elif d['status'] == 'finished':
            emit('download_progress', {'percent': 100})

    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            just_filename = os.path.basename(filename)
            
            # ডাউনলোড শেষ হলে ইউজারকে ফাইল ডাউনলোডের আসল লিঙ্ক পাঠানো
            emit('download_complete', {
                'message': 'ডাউনলোড সফল হয়েছে!',
                'filename': just_filename,
                'download_url': f'/downloads/{just_filename}'
            })
    except Exception as e:
        emit('download_error', {'message': str(e)})

if __name__ == '__main__':
    # রেন্ডার বা লোকাল পোর্টের সাথে মানিয়ে নেওয়ার ব্যবস্থা
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
    
