# Upload songs to Telegram channel

Use `upload_to_telegram.py` to send a folder of songs (or any files) to your Telegram channel [@wing_karaoke](https://t.me/wing_karaoke).

## 1. Create a bot and get a token

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`, choose a name and username for the bot.
3. Copy the **token** BotFather gives you (looks like `123456789:ABCdefGHI...`).

## 2. Add the bot to your channel as admin (required)

If you see **"bot is not a member of the channel chat"**, the bot is not in the channel yet:

1. Open your channel **@wing_karaoke** in Telegram.
2. Tap the channel name (top) → **Administrators** → **Add administrator**.
3. Search for your bot (e.g. **@wingsaber_bot**) and add it.
4. Turn on **Post messages** (and leave other permissions as needed).
5. Save. Then run the upload script again.

## 3. Run the script

**Windows (PowerShell):**

```powershell
cd "C:\Users\Rohan\Documents\Youtube download"
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
python upload_to_telegram.py "C:\path\to\folder\with\songs"
```

**Or pass the token on the command line:**

```powershell
python upload_to_telegram.py "C:\path\to\songs" --token "YOUR_BOT_TOKEN"
```

**Options:**

- `--channel @wing_karaoke` — default; change if you use another channel.
- `--topic-id ID` — optional. Upload to a **topic** (folder) in your channel. See [Topic ID (folders)](#topic-id-folders) below.
- `--album-size N` — group audio into albums of N files (2–10) per message. `0` = one message per file.
- `--workers N` — **parallel uploads** (default: 1). Use `--workers 10` or `--workers 16` to upload many files at once. If Telegram rate-limits you, lower to 5–8.
- `--delay 0.5` — seconds between uploads when using 1 worker (avoids rate limits).
- `--dry-run` — only list files that would be uploaded; no upload.

After it runs, all files in the folder will appear as posts in your channel; anyone with the link can join and download.

---

## Topic ID (folders)

In Telegram, **Topics** work like folders: you can enable Topics in your channel and create one topic per playlist or category. Uploads that specify a **Topic ID** go into that topic instead of the main feed.

### How to get a Topic ID

1. **Enable Topics** in your channel: Channel info → Edit → Topics → Turn on.
2. **Create a topic** (e.g. "Karaoke 2024" or "Playlist XYZ").
3. **Get the topic’s message ID** (this is the Topic ID / `message_thread_id`):
   - **Option A:** Open the topic and send any message. Use a bot or client that can read updates; the message’s `message_thread_id` is the topic ID.
   - **Option B:** In the topic’s link (e.g. `t.me/c/1234567890/54321`), the number after the last `/` is often the topic ID (e.g. `54321`). Some clients show it in the topic info.
   - **Option C:** Use the [Telegram Bot API](https://core.telegram.org/bots/api) (e.g. getUpdates or getChat) after sending a message in the topic; the reply will include `message_thread_id`.
4. Enter that number in **Topic ID (folder)** in the app, or pass `--topic-id 54321` to the script.

If you leave Topic ID empty, files are posted to the channel’s main feed.

---

## Upload from the app (v3)

In the YouTube Downloader app, enable **Upload to Telegram after download**. Set your **Bot token** and **Channel** (@channel). Optionally set **Topic ID (folder)** and **Group as albums** (5 or 10 per message). When a download finishes, the app will upload the files from the output folder to your channel in the background.
