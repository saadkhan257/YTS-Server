# YTS-Server

**# YTS-Server** is a clean, modular, and production-ready Flask backend designed for processing and transferring videos from multiple platforms like YouTube, TikTok, Facebook, and Instagram. It supports safe merging, clean `.mp4` outputs, and is optimized for VPS deployment.

---

## ✅ Features

- 🔥 Lightweight Flask API for media processing
- 📺 YouTube metadata & media extraction using `yt_dlp`
- 🧠 Smart platform detection via unified helper logic
- 📁 Output: clean `.mp4` files only (no `.fXXX.temp`)
- 📡 Supports modular expansion for TikTok, Facebook, Instagram
- ⚙️ Gunicorn + NGINX + HTTPS (Certbot) deployment ready
- 🚫 AdMob-safe (undetectable client-side logic)
- 🔐 Private, secure, and production optimized

---

## 📁 Project Structure

```
# YTS-Server/
│
├── app.py                      # 🔥 Main Flask app (entry point)
├── requirements.txt            # 📦 All dependencies
├── config.py                   # ⚙️ Configs (API keys, limits, paths)
├── README.md                   # 📘 Project overview & setup
│
├── static/
│   └── videos/                 # 📂 Output folder for downloaded media files
│
├── utils/
│   ├── platform_helper.py      # 🌍 Auto-detect platform (YT, TikTok, etc.)
│   ├── downloader.py           # 🎯 Unified download logic (uses yt_dlp)
│   ├── status_manager.py       # 📊 Tracks download status in-memory
│   ├── history_manager.py      # 🧾 Saves completed downloads
│   ├── cleanup.py              # 🧹 Auto delete old files
│   └── logger.py               # 🪵 Optional: Custom logging
│
├── services/
│   ├── youtube_service.py      # 🎥 YouTube-specific logic
│   ├── tiktok_service.py       # 🕺 TikTok-specific logic
│   ├── facebook_service.py     # 📘 Facebook-specific logic
│   ├── instagram_service.py    # 📸 Instagram-specific logic
│   └── snapchat_service.py     # 📸 Snapchat-specific logic
└── .gitignore               

```

---

## 🧪 Local Development

Clone and run:

```bash
git clone https://github.com/saadkhan257/YTS-Server.git
cd YTS-Server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend
python app.py
```

Then visit: [http://localhost:5000](http://localhost:5000)

---

## 🚀 VPS Deployment Guide (Gunicorn + NGINX + HTTPS)

1. Clone the repo on your VPS:
   ```bash
   git clone https://github.com/saadkhan257/YTS-Server.git
   ```

2. Set up a Python virtual environment:
   ```bash
   cd YTS-Server
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Create a Gunicorn systemd service (`/etc/systemd/system/yts-backend.service`):
   ```ini
   [Unit]
   Description=YTS Global Backend
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/var/www/YTS-Server
   Environment="root/yt-server/YTS-Server/venv/bin"
   ExecStart=/YTS-Server/venv/bin/gunicorn --workers 3 --bind unix:yts-backend.sock -m 007 app:app

   [Install]
   WantedBy=multi-user.target
   ```

4. Create an NGINX config (`/etc/nginx/sites-available/yts-server`):
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location / {
           include proxy_params;
           proxy_pass http://unix:/var/www/YTS-Server/yts-backend.sock;
       }
   }
   ```

5. Enable and start everything:
   ```bash
   sudo ln -s /etc/nginx/sites-available/yts-backend /etc/nginx/sites-enabled
   sudo systemctl restart nginx
   sudo systemctl start yts-backend
   sudo systemctl enable yts-backend
   ```

6. Add HTTPS:
   ```bash
   sudo apt install certbot python3-certbot-nginx -y
   sudo certbot --nginx -d yourdomain.com
   ```

---

## 🛠 Tech Stack

- Python 3
- Flask
- yt_dlp
- Gunicorn
- NGINX
- Certbot (HTTPS)

---

## 🙅 Disclaimer

This project is intended for **private use only**. Redistribution or commercial deployment is not allowed without permission. Designed to be undetectable for client-side AdMob safety, but backend remains standard.

---

## 👨‍💻 Author

Made with ❤️ by [Technical Forest](https://technicalforest.com/)

