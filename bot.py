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
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Please set it in your environment.")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = Quart(__name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


SOURCE_CHANNEL_ID=-1002110764294
# Optional: second channel to cross-post budget deals (≤ ₹150)
# Set via env var BUDGET_CHANNEL_ID or replace with a hardcoded integer
BUDGET_CHANNEL_ID = -1003898460377
# Optional: second budget tier channel for ≤ ₹199
# BUDGET_CHANNEL_ID_199 = -1003872969940
# SOURCE_CHANNEL_ID2= -1002365489797
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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

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
    if client is None:
        # OpenAI client not configured; skip AI classification
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

async def expand_short_links(text: str) -> str:
    """
    Expand shortener links in text without blocking the event loop.
    """
    if not text:
        return text
    if not any(keyword in text for keyword in shortnerfound):
        return text
    urls = extract_link_from_text2(text) or []
    if not urls:
        return text
    # Run unshortening in background threads
    tasks = [asyncio.to_thread(unshorten_url2, u) for u in urls]
    expanded = await asyncio.gather(*tasks, return_exceptions=True)
    result = text
    for original_url, expanded_url in zip(urls, expanded):
        if isinstance(expanded_url, Exception):
            continue
        result = result.replace(original_url, expanded_url)
    return result

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
# 💸 Price Extraction (Regex + AI fallback)
# ===============================
PRICE_THRESHOLD_150 = 150
PRICE_THRESHOLD_199 = 199

def extract_price_regex(text: str):
    if not text:
        return None
    # Common INR price patterns: ₹149, Rs. 149, INR 149, 149/-, 149 rs
    patterns = [
        r"(?:₹|Rs\.?\s*|INR\s*)(\d{1,6}(?:\.\d{1,2})?)",
        r"(\d{1,6}(?:\.\d{1,2})?)\s*/-",
        r"(\d{1,6}(?:\.\d{1,2})?)\s*(?:rs|inr)\b",
        r"price\s*[:\-]?\s*(?:₹\s*)?(\d{1,6}(?:\.\d{1,2})?)",
    ]
    candidates = []
    for p in patterns:
        for m in re.findall(p, text, flags=re.IGNORECASE):
            try:
                candidates.append(float(m))
            except:
                continue
    if not candidates:
        return None
    # Return the minimum plausible price found
    return min(candidates)

def extract_price_ai(text: str):
    if not text or client is None:
        return None
    prompt = f"""
    Extract the most likely current price in Indian Rupees from the text.
    - If multiple prices are present (e.g., MRP, deal price), return the LOWEST deal/final price.
    - Return ONLY a number (no currency symbol), like 149 or 149.00.
    - If no price is present, return "None".

    Text:
    {text}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract the lowest deal price in INR as a number only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        content = (response.choices[0].message.content or "").strip()
        if content.lower() == "none":
            return None
        # keep only first number if any additional text slipped
        m = re.search(r"\d+(?:\.\d+)?", content)
        if not m:
            return None
        return float(m.group(0))
    except Exception as e:
        print(f"❌ GPT price extraction error: {e}")
        return None

def get_product_price(text: str):
    # Try regex first
    price = extract_price_regex(text)
    if price is not None:
        return price
    # Fallback to AI
    return extract_price_ai(text)

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
        final_caption = compilehyperlink(message)
        
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

async def send_budget_149(message: types.Message, final_caption: str):
    if not BUDGET_CHANNEL_ID:
        return

    try:
        extra_html = (
            "<b>🛍️ 👉 <a href='https://t.me/addlist/WhyK9RPZHdU4MGNl'>Click & Join More Deals</a></b>"
        )
        Promo = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🏠 Join Deals Group",
                    url="https://t.me/+VQo_PHfTYW02MGI1",
                    style="success"
                )]])
        if message.photo:
            await bot.send_photo(
                chat_id=BUDGET_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=f"<b>{final_caption}</b>\n\n{extra_html}",
                reply_markup=Promo,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=BUDGET_CHANNEL_ID,
                text=f"{final_caption}",
                disable_web_page_preview=True
            )
        print(f"💸 Budget post sent to {BUDGET_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Error sending to budget channel: {e}")

# async def send_budget_199(message: types.Message, final_caption: str):
#     if not BUDGET_CHANNEL_ID_199:
#         return
#     try:
#         extra_html = (
#             "<b>👉 <a href='https://t.me/addlist/3G8HfhX3WSEwNmI1'>Click & Join All Deals </a>👈</b>"
#         )
#         Promo = types.InlineKeyboardMarkup(
#         inline_keyboard=[
#             [
#                 types.InlineKeyboardButton(
#                     text="🛍️ Join Premium Offers",
#                     url="https://t.me/+vUHFBOFLHd02MTZl",
#                     style="danger"
#                 )]])
#         if message.photo:
#             await bot.send_photo(
#                 chat_id=BUDGET_CHANNEL_ID_199,
#                 photo=message.photo[-1].file_id,
#                 caption=f"<b>{final_caption}</b>\n\n{extra_html}",
#                 reply_markup=Promo,
#                 parse_mode="HTML"
#             )
#         else:
#             await bot.send_message(
#                 chat_id=BUDGET_CHANNEL_ID_199,
#                 text=f"{final_caption}",
#                 disable_web_page_preview=True
#             )
#         print(f"💸 Budget-199 post sent to {BUDGET_CHANNEL_ID_199}")
#     except Exception as e:
#         print(f"❌ Error sending to budget-199 channel: {e}")


# ===============================
# 🤖 Commands
# ===============================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Join @Dealdoom Bro")

@dp.message(F.text.startswith("silent_"))
async def set_silent_interval_cmd(message: types.Message):
    global silent_interval
    try:
        _, arg = message.text.split('_')
        silent_interval = int(arg)
        await message.reply(f"✅ Silent interval set: Every {silent_interval}th post will notify.")
    except:
        await message.reply("❌ Usage: silent_2")


# ✅ Listen to posts from the source channel
@dp.channel_post()
async def handle_channel_post(message: types.Message):
    try:
        if message.chat.id != SOURCE_CHANNEL_ID:
            return
        # 1️ Extract base text (preserve full text, not just last link)
        base_text = message.caption or message.text or ""
        # Optionally normalize hyperlinks within the text/caption
        compiled_text = compilehyperlink(message) or base_text
        # 2️⃣ Expand short links without blocking loop
        inputvalue = await expand_short_links(compiled_text)

        # 2.5️⃣ Cross-post to budget channel if price ≤ threshold
        try:
            price = await asyncio.to_thread(get_product_price, inputvalue)
            if price is not None:
                if price <= PRICE_THRESHOLD_150:
                    await send_budget_149(message, inputvalue)
        except Exception as e:
            print(f"⚠️ Budget price check failed: {e}")
        # 3️⃣ Detect category (run potentially-blocking call in a thread)
        category = await asyncio.to_thread(get_category, inputvalue)

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

# @dp.channel_post()
# async def handle_channel_post2(message: types.Message):
#     try:
#         if message.chat.id != SOURCE_CHANNEL_ID2:
#             return
#         # 1️ Extract base text (preserve full text, not just last link)
#         base_text = message.caption or message.text or ""
#         # Optionally normalize hyperlinks within the text/caption
#         compiled_text = compilehyperlink(message) or base_text
#         # 2️⃣ Expand short links without blocking loop
#         inputvalue = await expand_short_links(compiled_text)
#
#         # 2.5️⃣ Cross-post to budget channel if price ≤ threshold
#         try:
#             price = await asyncio.to_thread(get_product_price, inputvalue)
#             if price is not None:
#                 if price <= PRICE_THRESHOLD_199:
#                     await send_budget_199(message, inputvalue)
#         except Exception as e:
#             print(f"⚠️ Budget price check failed: {e}")
#         # 3️⃣ Detect category (run potentially-blocking call in a thread)
#
#     except Exception as e:
#         print(f"❌ Error in handle_channel_post2: {e}")
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
    await bot.delete_webhook(drop_pending_updates=True)

    bot_task = asyncio.create_task(dp.start_polling(bot))
    web_task = asyncio.create_task(app.run_task(host="0.0.0.0", port=8080))
    await asyncio.gather(bot_task, web_task)

if __name__ == "__main__":
    asyncio.run(main())
