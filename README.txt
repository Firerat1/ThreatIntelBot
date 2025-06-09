CYBERBOT STARTUP GUIDE  
=======================

This file explains how the launch_bot.bat script works and what CyberBot does.

1. What It Does  
---------------
This script launches your local CyberBot, which powers a Discord automation stack for real-time security and tech news:

- Starts Ollama (Mistral LLM) on localhost
- Waits briefly to ensure the model is ready
- Starts the CyberBot (main_bot.py)
    - Pulls RSS feeds from configured sources
    - Posts new articles in Discord channels
    - Summarizes posts every 90 minutes using Mistral
    - Tracks seen items via last_seen_entries.json

2. File Descriptions  
---------------------
- main_bot.py: The main bot script (fetches, posts, and summarizes content)
- launch_bot.bat: Launches the bot and Ollama (optional)
- launch_bot_hidden.vbs: Used to hide the window when launching via the batch file
- .env: Stores your Discord token and channel IDs (keep private)
- last_seen_entries.json: Remembers which articles have already been posted
- README.txt: This help file

3. How to Use It  
----------------
- Double-click launch_bot.bat
- Or run main_bot.py manually with:  
  `python main_bot.py`

4. Auto-Run at Startup (Optional)  
---------------------------------
To run CyberBot every time your PC starts:

- Open Task Scheduler
- Create Basic Task → "Launch CyberBot"
- Trigger: At logon
- Action: Start a program
- Program/script: `launch_bot.bat`
- Optional: Use `launch_bot_hidden.vbs` if you want it to run silently

5. Troubleshooting  
------------------
- If nothing posts in Discord:
    - Make sure Ollama is running and Mistral is loaded (port 11434)
    - Check `.env` for valid Discord token and channel IDs
    - Ensure Python and required libraries are installed
- If you get "content must be under 2000 characters":
    - The bot auto-splits messages, but check for embedded content issues
- To reset RSS memory:
    - Delete `last_seen_entries.json` to force reposting all feeds

🛡️ Powered by Mistral via Ollama  

