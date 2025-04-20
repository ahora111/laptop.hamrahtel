
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
import re
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
    # حذف کاراکترهای غیرضروری و بررسی اینکه آیا مقدار عددی است
    model_str = model_str.replace("٬", "").replace(",", "").strip()
    if is_number(model_str):
        model_value = float(model_str)
        # اعمال درصدهای مختلف بر اساس بازه عددی
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
        else:  # مقادیر بالاتر از 40000000
            model_value_with_increase = model_value * 1.015
        
        # گرد کردن مقدار به 5 رقم آخر
        model_value_with_increase = round(model_value_with_increase, -5)
        return f"{model_value_with_increase:,.0f}"  # فرمت دهی عدد نهایی
    return model_str  # اگر مقدار عددی نباشد، همان مقدار اولیه بازگردانده می‌شود




def escape_special_characters(text):
    # فرار دادن کاراکترهای خاص برای MarkdownV2
    escape_chars = ['\\', '(', ')', '[', ']', '~', '*', '_', '-', '+', '>', '#', '.', '!', '|']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text



def split_message(message, max_length=4000):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

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
    elif any(keyword in line for keyword in ["RAM", "FA", "Classic", "Otel", "DOX"]):
        return f"🟣 {line}"
    elif any(keyword in line for keyword in ["Play Station", "کنسول بازی", "پلی استیشن", "بازی"]):  # اضافه کردن کلمات کلیدی کنسول بازی
        return f"🎮 {line}"
    else:
        return line

def sort_lines_together_by_price(lines):
    def extract_price(group):
        # این تابع قیمت را از آخرین خط هر گروه استخراج می‌کند
        for line in reversed(group):
            parts = line.split()
            for part in parts:
                try:
                    return float(part.replace(',', '').replace('،', ''))  # حذف کاما و تبدیل قیمت به عدد
                except ValueError:
                    continue
        return float('inf')  # مقدار پیش‌فرض برای گروه‌های بدون قیمت

    # تبدیل خطوط به گروه‌ها (حفظ ارتباط میان اطلاعات هر محصول)
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

    # مرتب‌سازی گروه‌ها براساس قیمت
    grouped_lines.sort(key=extract_price)

    # تبدیل گروه‌های مرتب‌شده به لیستی از خطوط
    sorted_lines = [line for group in grouped_lines for line in group]
    return sorted_lines

def remove_extra_blank_lines(lines):
    cleaned_lines = []
    blank_count = 0

    for line in lines:
        if line.strip() == "":  # بررسی خطوط خالی
            blank_count += 1
            if blank_count <= 1:  # فقط یک خط خالی نگه‌دار
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)

    return cleaned_lines
    

# تابع برای دریافت ساعت دقیق ایران به شمسی
def get_current_time():
    # زمان ایران (تهران)
    iran_tz = timezone('Asia/Tehran')
    iran_time = datetime.now(iran_tz)
    
    # تبدیل به فرمت ساعت و دقیقه
    current_time = iran_time.strftime('%H:%M')  # ساعت به صورت 24 ساعته
    
    return current_time

def prepare_final_message(category_name, category_lines, update_date):
    # گرفتن عنوان دسته از روی ایموجی
    category_title = get_category_name(category_name)
    
    # دریافت تاریخ امروز به شمسی
    update_date = JalaliDate.today().strftime("%Y/%m/%d")
    # دریافت ساعت کنونی به شمسی
    current_time = get_current_time()

    # تعریف نگاشت برای روزهای هفته به فارسی
    weekday_mapping = {
            "Saturday": "شنبه💪",
            "Sunday": "یکشنبه😃",
            "Monday": "دوشنبه☺️",
            "Tuesday": "سه شنبه🥱",
            "Wednesday": "چهارشنبه😕",
            "Thursday": "پنج شنبه☺️",
            "Friday": "جمعه😎"
    }
    weekday_english = JalaliDate.today().weekday()  # گرفتن ایندکس روز هفته
    weekday_farsi = list(weekday_mapping.values())[weekday_english]  # تبدیل ایندکس به روز فارسی
    update_date_formatted = f"{weekday_farsi} {update_date.replace('-', '/')}"



    # ساخت هدر پیام
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
            # اگر محصول قبلی وجود داشت، اضافه‌اش کن
            if current_product:
                formatted_lines.append(current_product)
                if product_variants:
                    formatted_lines.extend(product_variants)
                formatted_lines.append("")  # اضافه کردن یک خط فاصله بین گوشی‌ها
                product_variants = []
            current_product = line.strip()
            i += 1
        else:
            # ترکیب رنگ و قیمت با فرض اینکه پشت سر هم هستند
            if i + 1 < len(category_lines):
                color = line.strip()
                price = category_lines[i + 1].strip()
                product_variants.append(f"{color} | {price}")
                i += 2
            else:
                # خط ناقص، فقط رنگ یا قیمت موجوده
                product_variants.append(line.strip())
                i += 1

    # افزودن آخرین محصول
    if current_product:
        formatted_lines.append(current_product)
        if product_variants:
            formatted_lines.extend(product_variants)

    # حذف | از سطرهایی که ایموجی دارند
    formatted_lines = [
        line for line in formatted_lines
        if not any(emoji in line for emoji in ["🔵", "🟡", "🍏", "🟣", "💻", "🟠", "🎮"]) or "|" not in line
    ]

    footer = "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"
    final_message = f"{header}" + "\n".join(formatted_lines) + f"{footer}"

    return final_message

    

# این تابع کمکی برای گرفتن اسم دسته‌بندی‌ها
def get_category_name(emoji):
    mapping = {
        "🔵": "سامسونگ",
        "🟡": "شیائومی",
        "🍏": "آیفون",
        "💻": "لپ‌تاپ‌ها",
        "🟠": "تبلت‌ها",
        "🎮": "کنسول‌ بازی"
    }
    return mapping.get(emoji, "گوشیای متفرقه")

def categorize_messages(lines):
    categories = {"🔵": [], "🟡": [], "🍏": [], "🟣": [], "💻": [], "🟠": [], "🎮": []}  # اضافه کردن 🎮 برای کنسول بازی
    
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
        elif line.startswith("🟠"):  # اضافه کردن شرط برای تبلت
            current_category = "🟠"
        elif line.startswith("🎮"):  # اضافه کردن شرط برای کنسول بازی
            current_category = "🎮"
            
        if current_category:
            categories[current_category].append(line)

    # مرتب‌سازی و حذف خطوط خالی اضافی در هر دسته‌بندی
    for category in categories:
        categories[category] = sort_lines_together_by_price(categories[category])  # مرتب‌سازی
        categories[category] = remove_extra_blank_lines(categories[category])  # حذف خطوط خالی

    return categories




# بارگذاری credentials از GitHub Secrets (base64 encoded)
def get_credentials():
    encoded = os.getenv("GSHEET_CREDENTIALS_JSON")
    if not encoded:
        raise Exception("Google Sheets credentials not found in environment variable")
    decoded = base64.b64decode(encoded)
    temp_path = "/tmp/creds.json"
    with open(temp_path, "wb") as f:
        f.write(decoded)
    return temp_path

# اتصال به Google Sheet
def connect_to_sheet():
    creds_path = get_credentials()
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    return sheet

def check_and_create_headers(sheet):
    # گرفتن داده‌های سطر اول
    first_row = sheet.get_all_values()[0] if sheet.get_all_values() else []
    
    # تعریف هدرها
    headers = ["emoji", "date", "message_id", "text"]
    
    # اگر هدرها موجود نباشند، اضافه می‌شود
    if first_row != headers:
        sheet.update(values=[headers], range_name="A1:D1")
        logging.info("✅ هدرها اضافه شدند.")
    else:
        logging.info("🔄 هدرها قبلاً موجود هستند.")


# خواندن داده‌های موجود از Google Sheet (به‌صورت dict با کلید emoji)
def load_sheet_data(sheet):
    records = sheet.get_all_records()
    data = {}
    for row in records:
        emoji = row.get("emoji")
        if emoji:
            data[emoji] = {
                "date": row.get("date"),
                "message_id": row.get("message_id"),
                "text": row.get("text")
            }
    return data
    
def update_sheet_data(sheet, emoji, message_id, text):
    today = JalaliDate.today().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    found = False

    for i, row in enumerate(records, start=2):  # سطر 1 برای هدره
        if row.get("emoji") == emoji:
            sheet.update(values=[[emoji, today, message_id, text]], range_name=f"A{i}")
            found = True
            break

    if not found:
        sheet.append_row([emoji, today, message_id, text])





# ارسال یا ویرایش پیام در تلگرام بسته به تاریخ و محتوا
def send_new_message_and_update_sheet(emoji, message_text, bot_token, chat_id, sheet):
    """
    ارسال پیام جدید و ثبت اطلاعات آن در Google Sheet
    """
    escaped_text = escape_special_characters(message_text)

    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": escaped_text,
        "parse_mode": "MarkdownV2"
    }

    response = requests.post(send_url, json=params)

    if response.ok:
        message_id = response.json()["result"]["message_id"]
        logging.info(f"📤 [{emoji}] پیام جدید ارسال شد.")
        update_sheet_data(sheet, emoji, message_id, message_text)
        return message_id
    else:
        logging.error(f"❌ [{emoji}] خطا در ارسال پیام: {response.text}")
        return None


def send_or_edit_message(emoji, message_text, bot_token, chat_id, sheet_data, sheet, should_send_final_message):
    """
    ارسال یا ویرایش پیام بر اساس اطلاعات روز و ذخیره در Google Sheet
    """
    today = JalaliDate.today().strftime("%Y-%m-%d")
    data = sheet_data.get(emoji)

    escaped_text = escape_special_characters(message_text)

    if data and data.get("date") == today:
        if data.get("text") == message_text:
            logging.info(f"🔁 [{emoji}] محتوای پیام تغییری نکرده است.")
            return data.get("message_id"), should_send_final_message  # در صورت ویرایش، پیام جدید ارسال نشود

        # تلاش برای ویرایش پیام
        edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
        params = {
            "chat_id": chat_id,
            "message_id": data.get("message_id"),
            "text": escaped_text,
            "parse_mode": "MarkdownV2"
        }

        response = requests.post(edit_url, json=params)
        if response.ok:
            logging.info(f"✅ [{emoji}] پیام ویرایش شد.")
            update_sheet_data(sheet, emoji, data.get("message_id"), message_text)
            return data.get("message_id"), should_send_final_message  # پیام ویرایش شده، پیام نهایی ارسال نشود
        else:
            logging.error(f"❌ [{emoji}] خطا در ویرایش: {response.json()}")
            logging.warning(f"📛 [{emoji}] پیام نامعتبر است، ارسال پیام جدید به‌جای ویرایش")
            # ارسال پیام جدید در هر صورت
            should_send_final_message = True
            return send_new_message_and_update_sheet(emoji, message_text, bot_token, chat_id, sheet), should_send_final_message

    # اگر پیامی برای امروز وجود ندارد یا پیام جدید ارسال می‌شود
    should_send_final_message = True
    return send_new_message_and_update_sheet(emoji, message_text, bot_token, chat_id, sheet), should_send_final_message



def send_telegram_message(message, bot_token, chat_id, reply_markup=None):
    message_parts = split_message(message)
    last_message_id = None
    for part in message_parts:
        # فرار دادن کاراکترهای خاص
        part = escape_special_characters(part)
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "MarkdownV2"
        }
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)

        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=params, headers=headers)
        response_data = response.json()
        if response_data.get('ok'):
            last_message_id = response_data["result"]["message_id"]
        else:
            logging.error(f"❌ خطا در ارسال پیام: {response_data}")
            return None

    logging.info("✅ پیام ارسال شد!")
    return last_message_id


def get_last_messages(bot_token, chat_id, limit=5):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    response = requests.get(url)
    if response.json().get("ok"):
        messages = response.json().get("result", [])
        return [msg for msg in messages if "message" in msg][-limit:]
    return []


# تکمیل شده: main با منطق ارسال/ویرایش + ذخیره در Google Sheet

def main():
    try:
        # اتصال به Google Sheet
        sheet = connect_to_sheet()

        # بررسی و اضافه کردن هدرها در صورت نیاز
        check_and_create_headers(sheet)

        driver = get_driver()
        if not driver:
            logging.error("❌ نمی‌توان WebDriver را ایجاد کرد.")
            return

        # باز کردن دسته‌بندی‌ها
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

        sheet = connect_to_sheet()
        sheet_data = load_sheet_data(sheet)

        
        should_send_final_message = False
        message_ids = {}

        for emoji, lines in categorized.items():
            if not lines:
                continue
            message = prepare_final_message(emoji, lines, JalaliDate.today().strftime("%Y-%m-%d"))
            result, should_send_final_message = send_or_edit_message(emoji, message, BOT_TOKEN, CHAT_ID, sheet_data, sheet, should_send_final_message)

            if isinstance(result, int):  # یعنی پیام جدید ارسال شده
                message_ids[emoji] = result
            elif result == "edited":
                message_ids[emoji] = sheet_data.get(emoji, {}).get("message_id")  # حفظ شناسه قدیمی
            else:
                # unchanged یا خطا
                message_ids[emoji] = sheet_data.get(emoji, {}).get("message_id")

        
        if should_send_final_message:
            # ساخت پیام نهایی + دکمه‌ها + ارسال
            final_message = (
                "✅ لیست گوشی و سایر کالاهای بالا بروز میباشد. ثبت خرید تا ساعت 10:30 شب انجام میشود و تحویل کالا ساعت 11:30 صبح روز بعد می باشد..\n\n"
                "✅اطلاعات واریز\n"
                "🔷 شماره شبا : IR970560611828006154229701\n"
                "🔷 شماره کارت : 6219861812467917\n"
                "🔷 بلو بانک   حسین گرئی\n\n"
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
                "🎮": "🎮 کنسول بازی"
            }

            for emoji, label in emoji_labels.items():
                msg_id = message_ids.get(emoji)
                if msg_id:
                    button_markup["inline_keyboard"].append([ 
                        {"text": label, "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{msg_id}"}
                    ])

            send_telegram_message(final_message, BOT_TOKEN, CHAT_ID, reply_markup=button_markup)

        else:
            logging.info("ℹ️ هیچ پیام جدیدی ارسال نشد، پیام نهایی فرستاده نشد.")

    except Exception as e:
        logging.error(f"❌ خطا: {e}")

if __name__ == "__main__":
    main()
