#!/usr/bin/env python3
import os
import time
import requests
import logging
import json
import pytz
import sys
import base64
import gspread
from pytz import timezone
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from datetime import datetime, time as dt_time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from persiantools.jdatetime import JalaliDate

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SHEET_NAME = 'Sheet1'
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

iran_tz = pytz.timezone('Asia/Tehran')
now = datetime.now(iran_tz)
current_time = now.time()
start_time = dt_time(9, 30)
end_time = dt_time(23, 30)
if not (start_time <= current_time <= end_time):
    print("🕒 خارج از بازه مجاز اجرا (۹:۳۰ تا ۲۳:۳۰). اسکریپت متوقف شد.")
    sys.exit()

def get_driver():
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        logging.error(f"خطا در ایجاد WebDriver: {e}")
        return None

def scroll_page(driver, scroll_pause_time=2):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_product_data(driver, valid_brands):
    product_elements = driver.find_elements(By.CLASS_NAME, 'mantine-Text-root')
    brands, models = [], []
    for product in product_elements:
        name = product.text.strip().replace("تومانءء", "").replace("تومان", "").replace("نامشخص", "").replace("جستجو در مدل‌ها", "").strip()
        parts = name.split()
        brand = parts[0] if len(parts) >= 2 else name
        model = " ".join(parts[1:]) if len(parts) >= 2 else ""
        if brand in valid_brands:
            brands.append(brand)
            models.append(model)
        else:
            models.append(brand + " " + model)
            brands.append("")
    return brands[25:], models[25:]

def is_number(model_str):
    try:
        float(model_str.replace(",", ""))
        return True
    except ValueError:
        return False

def process_model(model_str):
    model_str = model_str.replace("٬", "").replace(",", "").strip()
    if is_number(model_str):
        model_value = float(model_str)
        if model_value <= 1:
            model_value_with_increase = model_value * 0
        elif model_value <= 7000000:
            model_value_with_increase = model_value + 260000
        elif model_value <= 10000000:
            model_value_with_increase = model_value * 1.035
        elif model_value <= 20000000:
            model_value_with_increase = model_value * 1.025
        elif model_value <= 30000000:
            model_value_with_increase = model_value * 1.02
        elif model_value <= 40000000:
            model_value_with_increase = model_value * 1.015
        else:
            model_value_with_increase = model_value * 1.015
        model_value_with_increase = round(model_value_with_increase, -5)
        return f"{model_value_with_increase:,.0f}"
    return model_str

def escape_special_characters(text):
    escape_chars = ['\\', '(', ')', '[', ']', '~', '*', '_', '-', '+', '>', '#', '.', '!', '|']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text

def split_message_by_emoji_group(message, max_length=4000):
    lines = message.split('\n')
    parts = []
    current = ""
    group = ""
    for line in lines:
        if line.startswith(('🔵', '🟡', '🍏', '🟣', '💻', '🟠', '🎮')):
            # اگر گروه فعلی با اضافه کردن گروه جدید از حد مجاز بیشتر می‌شود، پارت جدید بساز
            if current and len(current) + len(group) > max_length:
                parts.append(current.rstrip('\n'))
                current = ""
            current += group
            group = ""
        group += line + '\n'
    # اضافه کردن آخرین گروه
    if current and len(current) + len(group) > max_length:
        parts.append(current.rstrip('\n'))
        current = ""
    current += group
    if current.strip():
        parts.append(current.rstrip('\n'))
    return parts

def decorate_line(line):
    if line.startswith(('🔵', '🟡', '🍏', '🟣', '💻', '🟠', '🎮')):
        return line  
    if any(keyword in line for keyword in ["Nartab", "Tab", "تبلت"]):
        return f"🟠 {line}"
    elif "Galaxy" in line:
        return f"🔵 {line}"
    elif "POCO" in line or "Poco" in line or "Redmi" in line:
        return f"🟡 {line}"
    elif "iPhone" in line:
        return f"🍏 {line}"
    elif any(keyword in line for keyword in ["اینچی", "لپ تاپ"]):
        return f"💻 {line}"   
    elif any(keyword in line for keyword in ["RAM", "FA", "Classic", "Otel", "DOX", "General", "Bloom", "NOKIA", "Zhivaco", "Hanofer", "TCH", "ALCATEL"]): 
        return f"🟣 {line}"
    elif any(keyword in line for keyword in ["Play Station", "کنسول بازی", "پلی استیشن", "بازی"]):
        return f"🎮 {line}"
    else:
        return line

def sort_lines_together_by_price(lines):
    def extract_price(group):
        for line in reversed(group):
            parts = line.split()
            for part in parts:
                try:
                    return float(part.replace(',', '').replace('،', ''))
                except ValueError:
                    continue
        return float('inf')
    grouped_lines = []
    current_group = []
    for line in lines:
        if line.startswith(("🔵", "🟡", "🍏", "🟣", "💻", "🟠", "🎮")):
            if current_group:
                grouped_lines.append(current_group)
            current_group = [line]
        else:
            current_group.append(line)
    if current_group:
        grouped_lines.append(current_group)
    grouped_lines.sort(key=extract_price)
    sorted_lines = [line for group in grouped_lines for line in group]
    return sorted_lines

def remove_extra_blank_lines(lines):
    cleaned_lines = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)
    return cleaned_lines

def get_current_time():
    iran_tz = timezone('Asia/Tehran')
    iran_time = datetime.now(iran_tz)
    current_time = iran_time.strftime('%H:%M')
    return current_time

def prepare_final_message(category_name, category_lines, update_date):
    category_title = get_category_name(category_name)
    update_date = JalaliDate.today().strftime("%Y/%m/%d")
    current_time = get_current_time()
    weekday_mapping = {
            "Saturday": "شنبه💪",
            "Sunday": "یکشنبه😃",
            "Monday": "دوشنبه☺️",
            "Tuesday": "سه شنبه🥱",
            "Wednesday": "چهارشنبه😕",
            "Thursday": "پنج شنبه☺️",
            "Friday": "جمعه😎"
    }
    weekday_english = JalaliDate.today().weekday()
    weekday_farsi = list(weekday_mapping.values())[weekday_english]
    update_date_formatted = f"{weekday_farsi} {update_date.replace('-', '/')}"
    header = (
        f"🗓 بروزرسانی {update_date_formatted} 🕓 ساعت: {current_time}\n"
        f"✅ لیست پخش موبایل اهورا\n\n"
        f"⬅️ موجودی {category_title} ➡️\n\n"
    )
    formatted_lines = []
    current_product = None
    product_variants = []
    i = 0
    while i < len(category_lines):
        line = category_lines[i]
        if line.startswith(("🔵", "🟡", "🍏", "🟣", "💻", "🟠", "🎮")):
            if current_product:
                formatted_lines.append(current_product)
                if product_variants:
                    formatted_lines.extend(product_variants)
                formatted_lines.append("")
                product_variants = []
            current_product = line.strip()
            i += 1
        else:
            if i + 1 < len(category_lines):
                color = line.strip()
                price = category_lines[i + 1].strip()
                product_variants.append(f"{color} | {price}")
                i += 2
            else:
                product_variants.append(line.strip())
                i += 1
    if current_product:
        formatted_lines.append(current_product)
        if product_variants:
            formatted_lines.extend(product_variants)
    formatted_lines = [
        line for line in formatted_lines
        if not any(emoji in line for emoji in ["🔵", "🟡", "🍏", "🟣", "💻", "🟠", "🎮"]) or "|" not in line
    ]
    footer = "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"
    final_message = f"{header}" + "\n".join(formatted_lines) + f"{footer}"
    return final_message

def get_category_name(emoji):
    mapping = {
        "🔵": "سامسونگ",
        "🟡": "شیائومی",
        "🍏": "آیفون",
        "💻": "لپ‌تاپ‌ها",
        "🟠": "تبلت‌ها",
        "🎮": "کنسول‌ بازی",
        "🟣": "گوشیای متفرقه"
    }
    return mapping.get(emoji, "گوشیای متفرقه")

def categorize_messages(lines):
    categories = {"🔵": [], "🟡": [], "🍏": [], "🟣": [], "💻": [], "🟠": [], "🎮": []}
    current_category = None
    for line in lines:
        if line.startswith("🔵"):
            current_category = "🔵"
        elif line.startswith("🟡"):
            current_category = "🟡"
        elif line.startswith("🍏"):
            current_category = "🍏"
        elif line.startswith("🟣"):
            current_category = "🟣"
        elif line.startswith("💻"):
            current_category = "💻"
        elif line.startswith("🟠"):
            current_category = "🟠"
        elif line.startswith("🎮"):
            current_category = "🎮"
        if current_category:
            categories[current_category].append(line)
    for category in categories:
        categories[category] = sort_lines_together_by_price(categories[category])
        categories[category] = remove_extra_blank_lines(categories[category])
    return categories

def get_credentials():
    encoded = os.getenv("GSHEET_CREDENTIALS_JSON")
    if not encoded:
        raise Exception("Google Sheets credentials not found in environment variable")
    decoded = base64.b64decode(encoded)
    temp_path = "/tmp/creds.json"
    with open(temp_path, "wb") as f:
        f.write(decoded)
    return temp_path

def connect_to_sheet():
    creds_path = get_credentials()
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    return sheet

def check_and_create_headers(sheet):
    first_row = sheet.get_all_values()[0] if sheet.get_all_values() else []
    headers = ["emoji", "date", "part", "message_id", "text"]
    if first_row != headers:
        sheet.update(values=[headers], range_name="A1:E1")
        logging.info("✅ هدرها اضافه شدند.")
    else:
        logging.info("🔄 هدرها قبلاً موجود هستند.")

def load_sheet_data(sheet):
    records = sheet.get_all_records()
    data = {}
    for row in records:
        emoji = row.get("emoji")
        date = row.get("date")
        part = row.get("part")
        if emoji and date:
            data.setdefault((emoji, date), []).append({
                "part": int(part),
                "message_id": row.get("message_id"),
                "text": row.get("text")
            })
    return data

def update_sheet_data(sheet, emoji, messages):
    today = JalaliDate.today().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    rows_to_delete = [i+2 for i, row in enumerate(records) if row.get("emoji") == emoji and row.get("date") == today]
    for row_num in reversed(rows_to_delete):
        sheet.delete_rows(row_num)
    for part, (message_id, text) in enumerate(messages, 1):
        sheet.append_row([emoji, today, part, message_id, text])

def send_telegram_message(message, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": escape_special_characters(message),
        "parse_mode": "MarkdownV2"
    }
    response = requests.post(url, json=params)
    if response.ok:
        return response.json()["result"]["message_id"]
    else:
        logging.error("خطا در ارسال پیام: %s", response.text)
        return None

def edit_telegram_message(message_id, message, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    params = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": escape_special_characters(message),
        "parse_mode": "MarkdownV2"
    }
    response = requests.post(url, json=params)
    return response.ok

def delete_telegram_message(message_id, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    params = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    response = requests.post(url, json=params)
    return response.ok

def process_category_messages(emoji, messages, bot_token, chat_id, sheet, today):
    sheet_data = load_sheet_data(sheet)
    prev_msgs = sorted([row for row in sheet_data.get((emoji, today), [])], key=lambda x: x["part"])
    new_msgs = []
    should_send_final_message = False
    for i, msg in enumerate(messages):
        if i < len(prev_msgs):
            if prev_msgs[i]["text"] != msg:
                ok = edit_telegram_message(prev_msgs[i]["message_id"], msg, bot_token, chat_id)
                if not ok:
                    message_id = send_telegram_message(msg, bot_token, chat_id)
                    should_send_final_message = True
                else:
                    message_id = prev_msgs[i]["message_id"]
                    should_send_final_message = True
            else:
                message_id = prev_msgs[i]["message_id"]
        else:
            message_id = send_telegram_message(msg, bot_token, chat_id)
            should_send_final_message = True
        new_msgs.append((message_id, msg))
    for j in range(len(messages), len(prev_msgs)):
        delete_telegram_message(prev_msgs[j]["message_id"], bot_token, chat_id)
        should_send_final_message = True
    update_sheet_data(sheet, emoji, new_msgs)
    return [msg_id for msg_id, _ in new_msgs], should_send_final_message

def update_final_message_in_sheet(sheet, message_id, text):
    today = JalaliDate.today().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    found = False
    for i, row in enumerate(records, start=2):
        if row.get("emoji") == "FINAL" and row.get("date") == today:
            sheet.update(values=[["FINAL", today, 1, message_id, text]], range_name=f"A{i}:E{i}")
            found = True
            break
    if not found:
        sheet.append_row(["FINAL", today, 1, message_id, text])

def get_final_message_from_sheet(sheet):
    today = JalaliDate.today().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    for row in records:
        if row.get("emoji") == "FINAL" and row.get("date") == today:
            return row.get("message_id"), row.get("text")
    return None, None

def send_or_edit_final_message(sheet, final_message, bot_token, chat_id, button_markup, should_send):
    message_id, prev_text = get_final_message_from_sheet(sheet)
    escaped_text = escape_special_characters(final_message)
    if message_id and prev_text == final_message and not should_send:
        logging.info("🔁 پیام نهایی تغییری نکرده است.")
        return message_id
    if message_id and (prev_text != final_message or should_send):
        url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": escaped_text,
            "parse_mode": "MarkdownV2",
            "reply_markup": json.dumps(button_markup)
        }
        response = requests.post(url, json=params)
        if response.ok:
            update_final_message_in_sheet(sheet, message_id, final_message)
            logging.info("✅ پیام نهایی ویرایش شد.")
            return message_id
        else:
            logging.warning("❌ خطا در ویرایش پیام نهایی، حذف پیام قبلی و ارسال پیام جدید.")
            # حذف پیام قبلی
            del_url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
            del_params = {
                "chat_id": chat_id,
                "message_id": message_id
            }
            del_response = requests.post(del_url, json=del_params)
            if del_response.ok:
                logging.info("✅ پیام نهایی قبلی حذف شد.")
            else:
                logging.warning("❌ حذف پیام نهایی قبلی موفق نبود: %s", del_response.text)
    # ارسال پیام جدید
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": escaped_text,
        "parse_mode": "MarkdownV2",
        "reply_markup": json.dumps(button_markup)
    }
    response = requests.post(url, json=params)
    if response.ok:
        message_id = response.json()["result"]["message_id"]
        update_final_message_in_sheet(sheet, message_id, final_message)
        logging.info("✅ پیام نهایی ارسال شد.")
        return message_id
    else:
        logging.error("❌ خطا در ارسال پیام نهایی: %s", response.text)
        return None

def main():
    try:
        sheet = connect_to_sheet()
        check_and_create_headers(sheet)
        driver = get_driver()
        if not driver:
            logging.error("❌ نمی‌توان WebDriver را ایجاد کرد.")
            return
        categories_urls = {
            "mobile": "https://hamrahtel.com/quick-checkout?category=mobile",
            "laptop": "https://hamrahtel.com/quick-checkout?category=laptop",
            "tablet": "https://hamrahtel.com/quick-checkout?category=tablet",
            "console": "https://hamrahtel.com/quick-checkout?category=game-console"
        }
        valid_brands = ["Galaxy", "POCO", "Redmi", "iPhone", "Redtone", "VOCAL", "TCL", "NOKIA", "Honor", "Huawei", "GLX", "+Otel", "اینچی"]
        brands, models = [], []
        for name, url in categories_urls.items():
            driver.get(url)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
            scroll_page(driver)
            b, m = extract_product_data(driver, valid_brands)
            brands.extend(b)
            models.extend(m)
        driver.quit()
        if not brands:
            logging.warning("❌ داده‌ای برای ارسال وجود ندارد!")
            return
        processed_data = []
        for i in range(len(brands)):
            model_str = process_model(models[i])
            processed_data.append(f"{model_str} {brands[i]}")
        message_lines = [decorate_line(row) for row in processed_data]
        categorized = categorize_messages(message_lines)
        today = JalaliDate.today().strftime("%Y-%m-%d")
        all_message_ids = {}
        should_send_final_message = False
        for emoji, lines in categorized.items():
            if not lines:
                continue
            message = prepare_final_message(emoji, lines, today)
            message_parts = split_message_by_emoji_group(message)
            current_time = get_current_time()
            for idx in range(1, len(message_parts)):
                message_parts[idx] = f"⏰ {current_time}\n" + message_parts[idx]
            message_ids, changed = process_category_messages(emoji, message_parts, BOT_TOKEN, CHAT_ID, sheet, today)
            all_message_ids[emoji] = message_ids
            if changed:
                should_send_final_message = True
        final_message = (
            "✅ لیست گوشی و سایر کالاهای بالا بروز میباشد. ثبت خرید تا ساعت 10:30 شب انجام میشود و تحویل کالا ساعت 11:30 صبح روز بعد می باشد..\n\n"
            "⭕️ حتما رسید واریز به ایدی تلگرام زیر ارسال شود .\n"
            "🆔 @lhossein1\n\n"
            "✅شماره تماس ثبت سفارش :\n"
            "📞 09371111558\n"
            "📞 09386373926\n"
            "📞 09308529712\n"
            "📞 028-3399-1417"
        )
        button_markup = {"inline_keyboard": []}
        emoji_labels = {
            "🔵": "📱 لیست سامسونگ",
            "🟡": "📱 لیست شیائومی",
            "🍏": "📱 لیست آیفون",
            "💻": "💻 لیست لپ‌تاپ",
            "🟠": "📱 لیست تبلت",
            "🎮": "🎮 کنسول بازی",
            "🟣": "📱 لیست گوشیای متفرقه"
        }
        for emoji, msg_ids in all_message_ids.items():
            for msg_id in msg_ids:
                if msg_id:
                    button_markup["inline_keyboard"].append([
                        {"text": emoji_labels.get(emoji, emoji), "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{msg_id}"}
                    ])
        send_or_edit_final_message(sheet, final_message, BOT_TOKEN, CHAT_ID, button_markup, should_send_final_message)
    except Exception as e:
        logging.error(f"❌ خطا: {e}")

if __name__ == "__main__":
    main()
