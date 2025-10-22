import os
import sys
import time
import subprocess
import requests
import json
import shutil
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- (1) CONFIGURATION: EDIT THESE 4 PATHS ---
# Folder 1: Where Syncthing saves audio files (The "Landing Zone")
WATCH_FOLDER = r"D:\Projects\Idea_sync" #<-- Your Syncthing target folder

# Folder 2: Where the final .txt notes are saved (The "Google Drive Zone")
FINAL_OUTPUT_FOLDER = r"D:\Projects\Formatted-Ideas" #<-- Your Google Drive folder

# Tool Paths
WHISPER_EXE = r"D:\Projects\Local_AI\Whisper\Whisper.exe"
WHISPER_MODEL = r"D:\Projects\Local_AI\Whisper\ggml-base.en.bin"
# ----------------------------------------------------

# This is the prompt we will send to the local AI
FORMATTING_PROMPT = """
The following is a raw, transcribed voice memo. Please take these ideas
and neatly document them as a clean, concise bulleted list.
If there are no clear ideas, just summarize the text.

Here is the transcription:
---
{transcribed_text}
---
"""

# --- Helper Functions (Transcribe & Format) ---

def format_text(text_to_format):
    """
    Sends raw text to a local Ollama model for formatting.
    """
    print(f"[Processor] Sending to Ollama for formatting...")
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "mistral:7b", # Use any model available in your local Ollama
        "prompt": FORMATTING_PROMPT.format(transcribed_text=text_to_format),
        "stream": False
    }
    try:
        # Post the request to the local Ollama server
        response = requests.post(url, data=json.dumps(payload))
        response.raise_for_status() # Raise an error for bad status codes
        response_data = response.json()
        formatted_text = response_data.get("response", "Error: No response from Ollama")
        print("[Processor] Got formatted text.")
        return formatted_text
    except requests.exceptions.RequestException as e:
        print(f"[Processor] ERROR connecting to Ollama: {e}")
        print("    Is Ollama running? Did you run 'ollama pull mistral:7b'?")
        return f"Error: Could not connect to Ollama. Raw text: {text_to_format}"

def transcribe_audio(audio_file_path):
    """
    Uses Whisper.exe to transcribe a given audio file.
    """
    print(f"[Processor] Transcribing {audio_file_path}...")
    # Whisper.exe creates a .txt file with the same name as the audio file
    output_txt_file = os.path.splitext(audio_file_path)[0] + ".txt"
    command = [WHISPER_EXE, "-m", WHISPER_MODEL, "-f", audio_file_path, "-otxt"]
    
    try:
        # Run the Whisper command-line tool.
        # CREATE_NO_WINDOW hides the annoying command prompt pop-up.
        subprocess.run(command, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # If the output file was created...
        if os.path.exists(output_txt_file):
            # Read the text from it
            with open(output_txt_file, 'r', encoding='utf-8') as f:
                transcribed_text = f.read()
            print("[Processor] Transcription complete.")
            # Clean up the .txt file that Whisper made
            os.remove(output_txt_file) 
            return transcribed_text
        else:
            print("[Processor] ERROR: Whisper ran but output .txt file was not found.")
            return None
    except subprocess.CalledProcessError as e:
        print(f"[Processor] ERROR running Whisper: {e.stderr}")
        return None

# --- Main Watcher: The "Sentry" ---
# This class watches the WATCH_FOLDER (Inbox).
# It checks for file stability and then processes the file.

class SentryHandler(FileSystemEventHandler):
    def __init__(self):
        # Avoid checking the same file multiple times from different events
        self.files_being_checked = set() 

    def on_created(self, event):
        """
        Called when a file is first created (e.g., Syncthing starts writing).
        """
        if event.is_directory:
            return
        self.start_stability_check(event.src_path)

    def on_modified(self, event):
        """
        Called as Syncthing writes data chunks to the file.
        """
        if event.is_directory:
            return
        # We start the check on 'modified' as well, in case 'created' was missed.
        self.start_stability_check(event.src_path)

    def start_stability_check(self, file_path):
        """
        Starts a stability check thread, but only if it's an audio file
        and we aren't already checking it.
        """
        # Check if it's an audio file and not already in our check-list
        if file_path not in self.files_being_checked and file_path.endswith(('.mp3', '.m4a', '.wav', '.ogg', '.aac')):
            self.files_being_checked.add(file_path)
            print(f"[Sentry] New file detected: {os.path.basename(file_path)}. Starting stability check...")
            # Run the check and processing in a separate thread
            t = threading.Thread(target=self.check_and_process_thread, args=(file_path,))
            t.start()

    def check_and_process_thread(self, file_path):
        """
        Polls the file size until it stops changing, then processes it.
        """
        last_size = -1
        stable_count = 0
        max_stable_count = 3 # ~15 seconds of stability (3 checks * 5s)
        
        print(f"[Sentry] Waiting for file transfer to complete...")
        while stable_count < max_stable_count:
            try:
                # Check if file still exists (it might have been moved/deleted)
                if not os.path.exists(file_path):
                    print(f"[Sentry] File {os.path.basename(file_path)} disappeared. Stopping check.")
                    self.files_being_checked.remove(file_path)
                    return
                    
                # Get the current file size
                current_size = os.path.getsize(file_path)
            except OSError as e:
                # File is locked by another process (like Syncthing). Wait and retry.
                print(f"    ... file is locked (Error: {e}). Retrying in 5s.")
                time.sleep(5) 
                continue

            # If size is the same as last check, and not 0 bytes...
            if current_size == last_size and current_size > 0:
                stable_count += 1
                print(f"[Sentry] ... file is stable. Check {stable_count}/{max_stable_count}.")
            else:
                # Size changed, or is 0. Reset the stability counter.
                stable_count = 0
                if current_size == 0:
                    print("    ... file is 0 bytes (placeholder). Waiting for data.")
                else:
                    print(f"    ... file is still growing (now {current_size} bytes).")
            
            last_size = current_size
            time.sleep(5) # Wait 5 seconds between checks

        # --- File is Stable: Begin Processing ---
        print(f"[Sentry] STABLE. File '{os.path.basename(file_path)}' is ready. Processing...")
        try:
            file_name = os.path.basename(file_path)
            
            # 1. Transcribe
            raw_text = transcribe_audio(file_path)
            
            if raw_text:
                # 2. Format
                formatted_note = format_text(raw_text)
                
                # 3. Save the final .txt note
                final_filename = os.path.splitext(file_name)[0] + ".txt"
                final_path = os.path.join(FINAL_OUTPUT_FOLDER, final_filename)
                with open(final_path, 'w', encoding='utf-8') as f:
                    f.write(formatted_note)
                print(f"[Processor] SUCCESS! Saved final note to {final_path}")
                
                # 4. Send ntfy notification to the phone
                try:
                    requests.post(
                        "https://ntfy.sh/amit-g-idea-pipeline-rename-this", # <-- This is your topic
                        data=f"New idea captured: {final_filename}".encode(encoding='utf-8')
                    )
                    print("[Processor] Sent notification to phone.")
                except Exception as e:
                    print(f"[Processor] Warning: Could not send ntfy notification: {e}")
            
            # 5. Clean up original audio file from WATCH_FOLDER
            try:
                os.remove(file_path)
                print(f"[Processor] Cleaned up original audio file.")
            except Exception as e:
                print(f"[Processor] Warning: Could not delete original audio file: {e}")

        except Exception as e:
            print(f"[Processor] !!! UNHANDLED ERROR processing {file_path}: {e}")
        finally:
            # Clean up: remove the file from the set of files being checked
            if file_path in self.files_being_checked:
                self.files_being_checked.remove(file_path)


# --- Main script execution ---
if __name__ == "__main__":
    # Check that the critical folders exist before starting
    if not os.path.exists(WATCH_FOLDER):
        print(f"ERROR: WATCH_FOLDER does not exist: {WATCH_FOLDER}")
        sys.exit(1)
    if not os.path.exists(FINAL_OUTPUT_FOLDER):
        print(f"ERROR: FINAL_OUTPUT_FOLDER does not exist: {FINAL_OUTPUT_FOLDER}")
        sys.exit(1)

    print("--- Single-Folder Idea Processor ---")
    
    # Setup the Sentry Watcher
    event_handler_sentry = SentryHandler()
    observer_sentry = Observer()
    observer_sentry.schedule(event_handler_sentry, WATCH_FOLDER, recursive=False)
    
    # Start the watcher
    observer_sentry.start()
    
    print(f"SENTRY watching: {WATCH_FOLDER}")
    print("Press CTRL+C to stop.")
    
    try:
        # Keep the script alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Handle graceful shutdown
        observer_sentry.stop()
    
    observer_sentry.join()