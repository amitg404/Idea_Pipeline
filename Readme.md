# 🤖 Personal AI Idea Pipeline

This project is a 24/7 automation script that transforms your voice memos into neatly formatted, bullet-point notes.

You tap a widget on your phone, record an idea, and this script (running on an always-on PC) automatically transcribes it, formats it using a local AI, and saves it to your Google Drive.

## Features

* **One-Tap Idea Capture:** Record a voice memo on your phone, and it's automatically processed.
* **Local-First AI:** Uses your PC's GPU to run local AI models (Whisper and Mistral) for 100% privacy and no API costs.
* **Intelligent Formatting:** Doesn't just transcribe; it uses an LLM to intelligently summarize and format your ideas into clean bullet points.
* **Robust & Stable:** Built with a two-folder "Sentry/Processor" model to handle slow file transfers and sync issues.
* **Instant Notifications:** Get a push notification on your phone the moment your note is ready.
* **Cloud Sync:** Saves the final note to a Google Drive folder, making it accessible from anywhere.

## How It Works

This script uses a robust dual-watcher design to ensure file stability, which is crucial when syncing from a phone with a slow connection.

1.  **Folder 1: The "Sentry" (`Idea_syncing`)**
    * **Syncthing** (or a similar app) saves new audio recordings from your phone into this folder.
    * The **Sentry Watcher** detects the new file. It *does not* process it immediately.
    * It patiently checks the file size every 5 seconds. Once the size has been stable for 15 seconds, it knows the transfer is 100% complete.
    * It then **moves** the stable file to Folder 2.

2.  **Folder 2: The "Processor" (`Idea-Processing`)**
    * The **Processor Watcher** detects the stable file arriving.
    * It immediately sends the audio file to **Whisper** for transcription.
    * The raw text is then sent to **Ollama (Mistral 7B)** with a prompt to format it into bullet points.
    * The final, clean `.txt` note is saved to your **Google Drive** folder.
    * A push notification is sent via **ntfy** to your phone.

![A simple diagram showing the flow: Phone -> Syncthing -> Sentry Folder -> Processor Folder -> AI Models -> Google Drive & ntfy](https://i.imgur.com/83ZkFvT.png)

## Tech Stack

* **Automation:** Python 3
* **File Sync:** [Syncthing](https://syncthing.net/) (or any file sync tool)
* **File Watching:** `watchdog` Python library
* **Transcription:** [Whisper (Const-me build)](https://github.com/Const-me/Whisper) - A C++ port optimized for NVIDIA GPUs.
* **AI Formatting:** [Ollama](https://ollama.com/) running the `mistral:7b` model (or any other model).
* **Cloud Storage:** [Google Drive for Desktop](https://www.google.com/drive/download/)
* **Notifications:** [ntfy](https://ntfy.sh/) (free, open-source push notifications)

## Setup & Installation

**1. Install Dependencies:**

* **Python 3:** [Download from python.org](https://www.python.org/downloads/).
* **Python Libraries:**
    ```bash
    pip install watchdog requests
    ```
* **Ollama:** [Download from ollama.com](https://ollama.com/) and run it. Then, pull your model:
    ```bash
    ollama pull mistral:7b
    ```
* **Whisper:** [Download the `Whisper.Release.zip`](https://github.com/Const-me/Whisper/releases) (or `cli.zip`) and unzip it to a permanent folder.
* **Whisper Model:** [Download a GGML model](https://huggingface.co/ggerganov/whisper.cpp/tree/main) (e.g., `ggml-base.en.bin`) and place it in the same folder as `Whisper.exe`.
* **Google Drive:** Install and set up the Google Drive for Desktop client.
* **Syncthing:** Install it on your PC and phone.
* **ntfy:** Install the app on your phone and subscribe to a secret topic (e.g., `my-secret-pipeline-123`).

**2. Create Your Folders:**

You need to create three separate folders on your PC:

1.  `Idea_syncing`: This is your "landing zone." Set Syncthing to save audio files here.
2.  `Idea-Processing`: An *empty* folder that acts as the "ready zone."
3.  `Formatted-Ideas`: Your "output" folder. Set your Google Drive client to sync this folder.

**3. Configure the Script:**

Open the `idea_processor.py` script and **edit the 5 paths** at the top to match your setup. You also *must* change the `ntfy` topic URL.

```python
# --- (1) EDIT THESE 5 PATHS ---
# Folder 1: Where Syncthing saves audio files (The "Landing Zone")
WATCH_FOLDER = r"D:\Your\Path\To\Idea_syncing" #<-- Your Syncthing target folder

# Folder 2: Where stable files are MOVED to (The "Ready Zone")
PROCESSING_FOLDER = r"D:\Your\Path\To\Idea-Processing" #<-- The NEW folder you just created

# Folder 3: Where the final .txt notes are saved (The "Google Drive Zone")
FINAL_OUTPUT_FOLDER = r"D:\Your\Path\To\Formatted-Ideas" #<-- Your Google Drive folder

# Tool Paths
WHISPER_EXE = r"D:\Your\Tools\Whisper\Whisper.exe"
WHISPER_MODEL = r"D:\Your\Tools\Whisper\ggml-base.en.bin"
# -----------------------------

...

# Find this line in the process_file_thread function and change the URL
requests.post(
    "[https://ntfy.sh/your-secret-topic-here](https://ntfy.sh/your-secret-topic-here)", # <-- CHANGE THIS
    data=f"New idea captured: {final_filename}".encode(encoding='utf-8')
)