import asyncio
import logging
import os
import re
import json
from quart import Quart
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from unshortenit import UnshortenIt
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command


import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

# ===============================
# 🔧 Configuration
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Quart(__name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


SOURCE_CHANNEL_ID=-1002110764294
CATEGORY_TOPICS = {
    "Baby&PetProducts": {"chat_id": -1003104174203, "topic_id": 29},
    "FashionBeauty&Apparels": {"chat_id": -1003104174203, "topic_id": 5},
    "CarBike&Accessories": {"chat_id": -1003104174203, "topic_id": 26},
    "MobileLaptop&Accessories": {"chat_id": -1003104174203, "topic_id": 4},
    "KitchenFurnitures&HomeDecor": {"chat_id": -1003104174203, "topic_id": 7},
    "SportsGym&Medicine": {"chat_id": -1003104174203, "topic_id": 13},
    "Electronics&LargeAppliance": {"chat_id": -1003104174203, "topic_id": 3},
    "Grocery&DailyUse": {"chat_id": -1003104174203, "topic_id": 2}
}

shortnerfound = ['extp', 'bitli', 'bit.ly', 'bitly', 'bitili', 'biti']

# ===============================
# 🧩 Helper Functions
# ===============================

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CATEGORIES = [
    "Baby&PetProducts", "FashionBeauty&Apparels", "CarBike&Accessories", "MobileLaptop&Accessories",
    "KitchenFurnitures&HomeDecor", "SportsGym&Medicine", "Electronics&LargeAppliance", "Grocery&DailyUse"
]

def get_category_ai_gpt(text: str) -> str:
    """
    Use ChatGPT to classify text into one of the predefined categories.
    """
    if not text:
        return None

    prompt = f"""
    You are a smart text classifier for deal/product posts.
    Choose exactly ONE best-matching category from this list:
    {", ".join(CATEGORIES)}.

    If the product doesn't fit any, respond only with "None".

    Text:
    {text}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # very fast and cheaper
            messages=[
                {"role": "system", "content": "You classify e-commerce products into fixed categories."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,  # deterministic output
        )

        category = response.choices[0].message.content.strip()
        if category not in CATEGORIES:
            return None
        print(f"🧠 GPT categorized as → {category}")
        return category
    except Exception as e:
        print(f"❌ GPT categorization error: {e}")
        return None


def get_category(text):
    """
    First tries static keyword-based classification.
    If no keyword matches, calls GPT for AI-based categorization.
    """
    text_lower = text.lower()
    #
    # # 🧩 Step 1: Keyword-based check
    # for category, keywords in CATEGORY_KEYWORDS.items():
    #     for kw in keywords:
    #         if kw in text_lower:
    #             print(f"✅ Keyword match: '{kw}' found in {category}")
    #             return category

    # 🧠 Step 2: AI fallback using GPT
    # print("⚙️ No keyword match found, asking GPT...")
    try:
        category =  get_category_ai_gpt(text)
        return category
    except Exception as e:
        print(f"❌ Error while calling GPT: {e}")
        return None

def extract_link_from_text(text):
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls[0] if urls else None

def extract_link_from_text2(text):
    url_pattern = r'https?://\S+'
    return re.findall(url_pattern, text)

def unshorten_url2(short_url):
    try:
        unshortener = UnshortenIt()
        return unshortener.unshorten(short_url)
    except:
        return short_url

def removedup(text):
    urls = re.findall(r"https?://\S+", text)
    unique_urls, seen = [], set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    lines = text.split("\n")
    cleaned_lines, seen_urls = [], set()
    for line in lines:
        if any(url in line for url in unique_urls):
            url_in_line = next((url for url in unique_urls if url in line), None)
            if url_in_line and url_in_line in seen_urls:
                continue
            seen_urls.add(url_in_line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()

def findpcode(url):
    try:
        product_code_match = re.search(r"/product/([A-Za-z0-9]{10})", url)
        product_code_match2 = re.search(r'/dp/([A-Za-z0-9]{10})', url)
        product_code = product_code_match.group(1) if product_code_match else product_code_match2.group(1)
        return product_code
    except:
        return None

def compilehyperlink(message):
    text = message.caption if message.caption else message.text
    inputvalue = text
    hyperlinkurl = []
    entities = message.caption_entities if message.caption else message.entities
    for entity in entities or []:
        if entity.url:
            hyperlinkurl.append(entity.url)
    pattern = re.compile(r'Buy Now')
    inputvalue = pattern.sub(lambda x: hyperlinkurl.pop(0) if hyperlinkurl else 'Buy Now', inputvalue)
    inputvalue = inputvalue.replace('Regular Price', 'MRP')
    if "😱 Deal Time" in inputvalue:
        inputvalue = removedup(inputvalue)
        inputvalue = (inputvalue.split("😱 Deal Time")[0]).strip()
    return inputvalue

# ===============================
# 🔕 Silent Control
# ===============================
silent_interval = 5
post_counter = {}
def should_notify(chat_id: int) -> bool:
    global post_counter, silent_interval
    post_counter[chat_id] = post_counter.get(chat_id, 0) + 1
    return post_counter[chat_id] % silent_interval == 0

# ===============================

# ===============================
# 🚀 Send Function (Aiogram)
# ===============================
def should_block_message(text: str) -> bool:
    """
    Block if '@' is followed by ANY letter (a-z / A-Z) without a space.
    Allow if '@' is followed ONLY by digits (price like @141).
    """
    if not text:
        return False

    # find all occurrences of @something
    matches = re.findall(r"@([A-Za-z0-9_]+)", text)

    for m in matches:
        # if it starts with digits ONLY → allowed
        if m.isdigit():
            continue

        # if it contains any alphabet → block
        if re.search(r"[A-Za-z]", m):
            return True

    return False
async def send(category, message: types.Message):
    text2 = message.caption if message.caption else message.text
    if should_block_message(text2):
        await bot.send_message(chat_id=5886397642,text='Just Blocked a Promo')
        return
    try:
        topic = CATEGORY_TOPICS.get(category)
        if not topic:
            print(f"⚠️ Unknown category: {category}")
            return

        chat_id = topic["chat_id"]
        thread_id = topic.get("topic_id")  # 👈 yahan se thread ID lenge (agar exist karta hai)
        notify = should_notify(chat_id)
        modifiedtxt = compilehyperlink(message).replace('@under_99_loot_deals', '@shopsymeesho')
        final_caption = modifiedtxt

        # ✅ Agar photo hai
        if message.photo:
            await bot.send_photo(
                chat_id=chat_id,
                photo=message.photo[-1].file_id,
                caption=f"{final_caption}",
                message_thread_id=thread_id if thread_id else None,  # 👈 optional thread_id
                disable_notification=not notify
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=f"{final_caption}",
                message_thread_id=thread_id if thread_id else None,  # 👈 optional thread_id
                disable_web_page_preview=True,
                disable_notification=not notify
            )

        print(f"✅ Message sent to {chat_id} (thread: {thread_id})")

    except Exception as e:
        print(f"❌ Error in send function: {e}")


# ===============================
# 🤖 Commands
# ===============================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Bot is running successfully!")

@dp.message(F.text.startswith("silent_") & F.from_user.id == 5886397642)
async def set_silent_interval_cmd(message: types.Message):
    global silent_interval
    try:
        _, arg = message.text.split('_')
        silent_interval = int(arg)
        await message.reply(f"✅ Silent interval set: Every {silent_interval}th post will notify.")
    except:
        await message.reply("❌ Usage: silent_2")

# ===============================
# 🧭 Forward Toggle
# ===============================
# forward = True
#
# @dp.message(Command("forward"))
# async def forward_control(message: types.Message):
#     if message.from_user.id != 5886397642:
#         return
#     buttons = [
#         [InlineKeyboardButton("Turn ON", callback_data='forward_on')],
#         [InlineKeyboardButton("Turn OFF", callback_data='forward_off')]
#     ]
#     await message.answer("Forward Status", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
#
# @dp.callback_query(F.data.in_({'forward_on', 'forward_off'}))
# async def callback_forward_toggle(callback: types.CallbackQuery):
#     global forward
#     if callback.data == 'forward_off':
#         forward = False
#         await callback.message.edit_text("❌ Forward turned OFF")
#     else:
#         forward = True
#         await callback.message.edit_text("✅ Forward turned ON")

# ===============================
# 🧾 Message Forwarding
# ===============================
# @dp.message()
# async def forward_message(message: types.Message):
#     try:
#         global forward
#         if not forward:
#             return
#
#         text = message.caption or message.text or ""
#         if any(k in text for k in shortnerfound):
#             for url in extract_link_from_text2(text):
#                 text = text.replace(url, unshorten_url2(url))
#
#         category = get_category(text)
#         if category:
#             print(f"✅ Matched '{category}' → forwarding")
#             await send(category, message)
#         else:
#             print("⚠️ No category matched")
#
#     except Exception as e:
#         print(f"❌ Error in forward_message: {e}")

# ✅ Listen to posts from the source channel
@dp.channel_post()
async def handle_channel_post(message: types.Message):
    try:
        if message.chat.id != SOURCE_CHANNEL_ID:
            return
        # 1️Extract text or caption with links
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

        # 3️⃣ Detect category using keywords
        category = get_category(inputvalue)

        if category:
            topic = CATEGORY_TOPICS.get(category)
            if not topic:
                print(f"⚠️ No topic mapping found for category: {category}")
                return

            chat_id = topic["chat_id"]
            thread_id = topic.get("topic_id")

            print(f"✅ Matched '{category}' → sending to thread {thread_id}")

            await send(category, message)
        else:
            print("⚠️ No matching category found, skipping.")

    except Exception as e:
        print(f"❌ Error in handle_channel_post: {e}")

# ===============================
# 🌐 Quart Web Endpoint
# ===============================
@app.route("/")
async def home():
    return "Hello from Aiogram + Quart bot!"

# ===============================
# 🏁 Run Everything
# ===============================
async def main():
    print("🤖 Bot starting...")
    bot_task = asyncio.create_task(dp.start_polling(bot))
    web_task = asyncio.create_task(app.run_task(host="0.0.0.0", port=8080))
    await asyncio.gather(bot_task, web_task)

if __name__ == "__main__":
    asyncio.run(main())


