import os
import discord
import asyncio
import requests
import feedparser
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# ============ CONFIG ============ #
TOKEN = os.getenv("DISCORD_TOKEN")
SUMMARY_CHANNEL_SECURITY = int(os.getenv("CHANNEL_SUMMARY_SECURITY"))
SUMMARY_CHANNEL_TECH = int(os.getenv("CHANNEL_SUMMARY_TECH"))

FEED_URLS = {
    "CHANNEL_CISA": "https://www.cisa.gov/news.xml",
    "CHANNEL_NVD": "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
    "CHANNEL_BLEEPING": "https://www.bleepingcomputer.com/feed/",
    "CHANNEL_DARKREADING": "https://www.darkreading.com/rss.xml",
    "CHANNEL_KREBS": "https://krebsonsecurity.com/feed/",
    "CHANNEL_HACKERNEWS": "https://feeds.feedburner.com/TheHackersNews",
    "CHANNEL_TALOS": "https://blog.talosintelligence.com/rss/",
    "CHANNEL_RAPID7": "https://www.rapid7.com/blog/rss/",
    "CHANNEL_SECURITYWEEK": "https://feeds.feedburner.com/securityweek",
    "CHANNEL_TECHCRUNCH": "https://techcrunch.com/feed/",
    "CHANNEL_WIRED": "https://www.wired.com/feed/rss",
    "CHANNEL_VERGE": "https://www.theverge.com/rss/index.xml",
    "CHANNEL_MIT": "http://news.mit.edu/rss/topic/technology",
    "CHANNEL_ARS": "http://feeds.arstechnica.com/arstechnica/index/",
    "CHANNEL_IEEE": "https://spectrum.ieee.org/rss/fulltext"
}
SECURITY_CHANNEL_IDS = [
    int(os.getenv("CHANNEL_CISA")),
    int(os.getenv("CHANNEL_NVD")),
    int(os.getenv("CHANNEL_BLEEPING")),
    int(os.getenv("CHANNEL_DARKREADING")),
    int(os.getenv("CHANNEL_KREBS")),
    int(os.getenv("CHANNEL_HACKERNEWS")),
    int(os.getenv("CHANNEL_TALOS")),
    int(os.getenv("CHANNEL_RAPID7")),
    int(os.getenv("CHANNEL_SECURITYWEEK")),
]

TECH_CHANNEL_IDS = [
    int(os.getenv("CHANNEL_TECHCRUNCH")),
    int(os.getenv("CHANNEL_WIRED")),
    int(os.getenv("CHANNEL_VERGE")),
    int(os.getenv("CHANNEL_MIT")),
    int(os.getenv("CHANNEL_ARS")),
    int(os.getenv("CHANNEL_IEEE")),
]

SECURITY_FEEDS = [int(os.getenv(k)) for k in FEED_URLS if "CHANNEL_" in k and "TECH" not in k]
TECH_FEEDS = [int(os.getenv(k)) for k in FEED_URLS if "TECH" in k or "MIT" in k or "ARS" in k or "IEEE" in k]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

summary_lock = asyncio.Lock()
last_seen_entries_file = "last_seen_entries.json"

# ============ PERSISTENT STORAGE ============ #
def load_last_seen():
    if os.path.exists(last_seen_entries_file):
        with open(last_seen_entries_file, "r") as f:
            return json.load(f)
    return {}

def save_last_seen():
    with open(last_seen_entries_file, "w") as f:
        json.dump(last_seen_entries, f)

last_seen_entries = load_last_seen()

# ============ RSS FETCH + POST ============ #
async def update_channel_from_feed(channel_name_env):
    url = FEED_URLS.get(channel_name_env)
    channel_id = int(os.getenv(channel_name_env))
    chan = client.get_channel(channel_id)

    if not url or not chan:
        return

    feed = feedparser.parse(url)
    new_entries = []
    last_id = last_seen_entries.get(channel_name_env)

    for entry in feed.entries[:5]:  # Check last 5 entries
        entry_id = getattr(entry, 'id', entry.link)
        if last_id == entry_id:
            break
        new_entries.append(entry)

    if new_entries:
        last_seen_entries[channel_name_env] = getattr(new_entries[0], 'id', new_entries[0].link)
        save_last_seen()

        for entry in reversed(new_entries):
            content = f"**{entry.title}**\n{entry.link}"
            await chan.send(content)
            print(f"Posted to {chan.name}: {entry.title}")

async def update_all_feeds():
    print("Fetching new articles from feeds...")
    for env_var in FEED_URLS.keys():
        try:
            await update_channel_from_feed(env_var)
        except Exception as e:
            print(f"Feed update failed for {env_var}: {e}")

# ============ DISCORD FETCH + SUMMARIZATION ============ #
async def fetch_messages(channel, allowed_ids, hours=1.5):
    try:
        if channel.id not in allowed_ids:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        messages = [
            (channel.name, channel.id, m.content.strip())
            async for m in channel.history(limit=200)
            if m.created_at.replace(tzinfo=timezone.utc) >= cutoff and m.content.strip()
        ]
        print(f"Fetched {len(messages)} messages from {channel.name}")
        return messages
    except Exception as e:
        print(f"Failed to fetch messages from {channel.name}: {e}")
        return []



def call_llm(prompt, timeout=30):
    try:
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }, timeout=timeout)
        return res.json()["response"].strip()
    except Exception as e:
        print(f" LLM call failed: {e}")
        return " LLM failed to generate summary."

async def post_chunks(channel_id, label, content):
    if not content.strip():
        return

    chan = client.get_channel(channel_id)
    if not chan:
        return

    overhead = len(f"**{label}**\n_YYYY-MM-DD HH:MM_\n")
    limit = 2000 - overhead

    chunks = [content[i:i+limit] for i in range(0, len(content), limit)]

    for i, chunk in enumerate(chunks):
        title = f"**{label}**" if i == 0 else "**(continued)**"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        safe_msg = f"{title}\n_{timestamp}_\n{chunk}"
        await chan.send(safe_msg)



async def generate_prompt(category, messages):
    if not messages:
        return f"No new updates in {category.lower()} feeds."

    grouped = {}
    for chan_name, chan_id, msg in messages:
        grouped.setdefault(chan_name, []).append(msg)

    prompt = f"Summarize the following **{category}** news. Provide 1–2 bullet points per channel. Be detailed but concise. Avoid links/usernames.\n\n"
    for chan, msgs in grouped.items():
        prompt += f"Channel: {chan}\n" + "\n".join(f"- {m}" for m in msgs[:5]) + "\n"
    prompt += "\nSummary:"
    return prompt



async def post_feed_summary(feeds, out_channel, label, category, hours=1.5, extended_timeout=False):
    async with summary_lock:
        msgs = []
        for cid in feeds:
            ch = client.get_channel(cid)
            if ch:
                try:
                    fetched = await fetch_messages(ch, feeds, hours)
                    msgs += fetched
                except Exception as e:
                    print(f"❌ {ch.name}: {e}")
        print(f"🧪 Generating {category} summary from {len(msgs)} messages across channels: {[name for name, _, _ in msgs]}")

        prompt = await generate_prompt(category, msgs)
        timeout = 90 if extended_timeout else 30
        summary = call_llm(prompt, timeout=timeout)
        await post_chunks(out_channel, f"{label} Summary", summary)



# ============ TASK LOOPS ============ #
async def periodic_30min_feed_check():
    await client.wait_until_ready()
    while True:
        print(" [30m] Fetching & posting new feed entries...")
        await update_all_feeds()
        await asyncio.sleep(30 * 60)

async def periodic_90min_summary_post():
    await client.wait_until_ready()
    await asyncio.sleep(90 * 60)  # 🕒 Wait for first cycle, since on_ready() already runs a summary
    while True:
        print("[90m] Posting summaries to summary channels...")
        await post_feed_summary(SECURITY_CHANNEL_IDS, SUMMARY_CHANNEL_SECURITY, "🛡️ Security", category="Security")
        await post_feed_summary(TECH_CHANNEL_IDS, SUMMARY_CHANNEL_TECH, "📡 Tech", category="Tech")
        await asyncio.sleep(90 * 60)



async def status_countdown():
    await client.wait_until_ready()
    feed_timer = 30
    summary_timer = 90
    while True:
        print(f"Waiting... Feed update in {feed_timer} min | Summary post in {summary_timer} min")
        await asyncio.sleep(300)  # 5 minutes
        feed_timer -= 5
        summary_timer -= 5
        if feed_timer <= 0:
            feed_timer = 30
        if summary_timer <= 0:
            summary_timer = 90


# ============ STARTUP ============ #
@client.event
async def on_ready():
    print(f" Logged in as {client.user}")
    print(" Startup: Fetching feeds and posting 24-hour summaries...")

    await update_all_feeds()

    await post_feed_summary(SECURITY_CHANNEL_IDS, SUMMARY_CHANNEL_SECURITY, "🛡️ Security - Last 24 Hours", category="Security", hours=24, extended_timeout=True)
    await post_feed_summary(TECH_CHANNEL_IDS, SUMMARY_CHANNEL_TECH, "📡 Tech - Last 24 Hours", category="Tech", hours=24, extended_timeout=True)

    asyncio.create_task(periodic_30min_feed_check())
    asyncio.create_task(periodic_90min_summary_post())
    asyncio.create_task(status_countdown())



# ============ LAUNCH ============ #
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(client.start(TOKEN))
