import tempfile
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont

# from playwright.async_api import async_playwright
from pyrogram import Client, filters, enums
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
import asyncio
from quart import Quart
from unshortenit import UnshortenIt
# from playwright.sync_api import sync_playwright
import os
from dotenv import load_dotenv
import json
load_dotenv()
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Define a handler for the /start command
bot = Quart(__name__)
# bot.config['PROVIDE_AUTOMATIC_OPTIONS'] = True
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

source_channel_id = [-1002110764294]  # Replace with the source channel ID

# TOPIC_CHAT_IDS = {
#     "BabyPet": "https://t.me/LootwaliGroup/29",
#     "FashionBeauty": "https://t.me/LootwaliGroup/5",
#     "CarBike": "https://t.me/LootwaliGroup/26",
#     "MobileLaptop": "https://t.me/LootwaliGroup/4",
#     "KitchenHome": "https://t.me/LootwaliGroup/7",
#     "SportsGymMed": "https://t.me/LootwaliGroup/13",
#     "Electronics": "https://t.me/LootwaliGroup/3",
#     "Grocery": "https://t.me/LootwaliGroup/2"
# }
CATEGORY_TOPICS = {
    "BabyPet": {"chat_id": -1003104174203, "topic_id": 29},
    "FashionBeauty": {"chat_id": -1003104174203, "topic_id": 5},
    "CarBike": {"chat_id": -1003104174203, "topic_id": 26},
    "MobileLaptop": {"chat_id": -1003104174203, "topic_id": 4},
    "KitchenHome": {"chat_id": -1003104174203, "topic_id": 7},
    "SportsGymMed": {"chat_id": -1003104174203, "topic_id": 13},
    "Electronics": {"chat_id": -1003104174203, "topic_id": 3},
    "Grocery": {"chat_id": -1003104174203, "topic_id": 2}
}

shortnerfound = ['extp', 'bitli', 'bit.ly', 'bitly', 'bitili', 'biti']

with open("category_keywords.json", "r") as f:
    CATEGORY_KEYWORDS = json.load(f)

def get_category(text):
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return category
    return None


def extract_link_from_text(text):
    # Regular expression pattern to match a URL
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls[0] if urls else None


def tinycovert(text):
    unshortened_urls = {}
    urls = extract_link_from_text2(text)
    for url in urls:
        unshortened_urls[url] = tiny(url)
    for original_url, unshortened_url in unshortened_urls.items():
        text = text.replace(original_url, unshortened_url)
    return text


def tiny(long_url):
    url = 'http://tinyurl.com/api-create.php?url='

    response = requests.get(url + long_url)
    short_url = response.text
    return short_url


def extract_link_from_text2(text):
    # Regular expression pattern to match a URL
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls


def unshorten_url2(short_url):
    unshortener = UnshortenIt()
    shorturi = unshortener.unshorten(short_url)
    # print(shorturi)
    return shorturi


# async def unshorten_url(url):
#     try:
#         async with async_playwright() as p:
#             browser = await p.chromium.launch(headless=True)
#             page = await browser.new_page()
#             await page.goto(url)
#             final_url = page.url
#             await browser.close()
#             return final_url
#     except Exception as e:
#         print(f"Error: {e}")
#         return None


def removedup(text):
    urls = re.findall(r"https?://\S+", text)
    unique_urls = []
    seen = set()

    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    # Remove duplicate URL lines
    lines = text.split("\n")
    cleaned_lines = []
    seen_urls = set()

    for line in lines:
        if any(url in line for url in unique_urls):
            # If the URL in the line is already seen, skip it
            url_in_line = next((url for url in unique_urls if url in line), None)
            if url_in_line and url_in_line in seen_urls:
                continue
            seen_urls.add(url_in_line)

        cleaned_lines.append(line)

    # Join cleaned lines back
    cleaned_text = "\n".join(cleaned_lines).strip()

    return cleaned_text


def findpcode(url):
    try:
        product_code_match = re.search(r"/product/([A-Za-z0-9]{10})", url)
        product_code_match2 = re.search(r'/dp/([A-Za-z0-9]{10})', url)
        product_code = product_code_match.group(1) if product_code_match else product_code_match2.group(1)
        return product_code
    except Exception as e:
        return


def compilehyperlink(message):
    text = message.caption if message.caption else message.text
    inputvalue = text
    hyperlinkurl = []
    entities = message.caption_entities if message.caption else message.entities
    for entity in entities:
        # new_entities.append(entity)
        if entity.url is not None:
            hyperlinkurl.append(entity.url)
    pattern = re.compile(r'Buy Now')

    inputvalue = pattern.sub(lambda x: hyperlinkurl.pop(0), inputvalue).replace('Regular Price', 'MRP')
    if "😱 Deal Time" in inputvalue:
        # Remove the part
        inputvalue = removedup(inputvalue)
        inputvalue = (inputvalue.split("😱 Deal Time")[0]).strip()
    return inputvalue

# =========================
# 📌 Silent Control
# =========================
silent_interval = 3   # Default: notify every 2nd post
post_counter = {}     # Track posts per target channel
def should_notify(chat_id: int) -> bool:
    """Return True if this post should notify, False if silent."""
    global post_counter, silent_interval
    if chat_id not in post_counter:
        post_counter[chat_id] = 0
    post_counter[chat_id] += 1
    return post_counter[chat_id] % silent_interval == 0



async def send(category, message):
    try:
        # Get topic info
        topic = CATEGORY_TOPICS.get(category)
        if not topic:
            print(f"⚠️ Unknown category: {category}")
            return

        chat_id = topic["chat_id"]
        topic_id = topic["topic_id"]

        notify = should_notify(chat_id)

        # Prepare text
        modifiedtxt = compilehyperlink(message).replace('@under_99_loot_deals', '@shopsymeesho')

        # --- Handle Photo Messages ---
        if message.photo:
            final_caption = await build_caption_with_links(modifiedtxt)
            await app.send_photo(
                chat_id=-1003104174203,
                # message_thread_id=topic_id,
                photo=message.photo.file_id,
                caption=f"<b>{final_caption}</b>",
                disable_notification=not notify
            )

        # --- Handle Text Messages ---
        elif message.text:
            final_caption = await build_caption_with_links(modifiedtxt)
            await app.send_message(
                chat_id=chat_id,
                # message_thread_id=topic_id,
                text=f"<b>{final_caption}</b>",
                disable_web_page_preview=True,
                disable_notification=not notify
            )

    except Exception as e:
        print(f"❌ Error in send function: {e}")


async def build_caption_with_links(text):
    """Utility to modify text and add Buy Now / PriceHistory links"""
    try:
        if any(k in text for k in ['tinyurl', 'amazon', 'amzn']):
            urls = extract_link_from_text2(text)
            for url in urls:
                pid = findpcode(unshorten_url2(url))
                if pid:
                    if 'amzn' in url:
                        text = text.replace(
                            url,
                            f"{url}\n\n<a href='t.me/Amazon_Pricehistory_bot?start={pid}'>📊 PriceHistory</a>"
                        )
                    else:
                        text = text.replace(
                            url,
                            f"<b><a href={url}>Buy Now</a> | <a href='t.me/Amazon_Pricehistory_bot?start={pid}'>📊 PriceHistory</a></b>"
                        )
                else:
                    if 'amzn' not in url:
                        text = text.replace(url, f'<b><a href={url}>Buy Now</a></b>')
        return text
    except Exception as e:
        print(f"⚠️ Error in build_caption_with_links: {e}")
        return text


@bot.route('/')
async def hello():
    return 'Hello, world!'


@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await app.send_message(message.chat.id, "ahaann")

@app.on_message(filters.regex("silent_") & filters.user(5886397642))
async def set_silent_interval(client, message):
    global silent_interval
    try:
        __, arg = message.text.split('_')
        silent_interval = int(arg)
        await message.reply_text(f"✅ Silent interval set: Every {silent_interval} post will notify.")
    except:
        await message.reply_text("❌ Usage: /silent_2")
################forward on off#################################################################
global forward
forward = True


@app.on_message(filters.command('forward') & filters.user(5886397642))
async def forwardtochannel(app, message):
    await message.reply(text='Forward Status', reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("Turn ON", callback_data='forward on')],
         [InlineKeyboardButton("Turn Off", callback_data='forward off')]])
                        )


forward_off = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Turn Off", callback_data='forward off')]])
forward_on = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Turn ON", callback_data='forward on')]])


@app.on_callback_query()
async def callback_query(app, CallbackQuery):
    global forward
    if CallbackQuery.data == 'forward off':
        await CallbackQuery.edit_message_text('Forward to Channel Status turned Off', reply_markup=forward_on)
        forward = False
    elif CallbackQuery.data == 'forward on':
        await CallbackQuery.edit_message_text('Forward to Channel Status turned On', reply_markup=forward_off)
        forward = True


########################################################################################

@app.on_message(filters.chat(source_channel_id))
async def forward_message(client, message):
    try:
        if not forward:
            return

        # 1️⃣ Extract text or caption with links
        inputvalue = ""
        if message.caption_entities:
            for entity in message.caption_entities:
                if entity.url:
                    inputvalue = entity.url
        if not inputvalue and message.caption:
            inputvalue = message.caption

        if message.entities:
            for entity in message.entities:
                if entity.url:
                    inputvalue = entity.url
        if not inputvalue and message.text:
            inputvalue = message.text

        # 2️⃣ Expand short links
        if any(keyword in inputvalue for keyword in shortnerfound):
            unshortened_urls = {}
            urls = extract_link_from_text2(inputvalue)
            for url in urls:
                unshortened_urls[url] = unshorten_url2(url)
            for original_url, unshortened_url in unshortened_urls.items():
                inputvalue = inputvalue.replace(original_url, unshortened_url)

        # 3️⃣ Detect category using keywords JSON
        category = get_category(inputvalue)

        if category:
            topic = CATEGORY_TOPICS.get(category)
            if not topic:
                print(f"⚠️ No topic mapping found for category: {category}")
                return

            chat_id = topic["chat_id"]
            print(f"✅ Matched '{category}' → sending to topic ID {topic['topic_id']}")
            await send(category, message)
        else:
            print("⚠️ No matching category found, skipping.")

    except Exception as e:
        print(f"❌ Error in forward_message: {e}")



@bot.before_serving
async def before_serving():
    await app.start()


@bot.after_serving
async def after_serving():
    await app.stop()


# if __name__ == '__main__':

# bot.run(port=8000)
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(bot.run_task(host='0.0.0.0', port=8080))
    loop.run_forever()








