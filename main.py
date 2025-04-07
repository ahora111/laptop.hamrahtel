#!/usr/bin/env python3
import os
import time
import requests
import logging
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from persiantools.jdatetime import JalaliDate

BOT_TOKEN = "8187924543:AAH0jZJvZdpq_34um8R_yCyHQvkorxczXNQ"
CHAT_ID = "-1002284274669"

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
        name = product.text.strip().replace("تومانءء", "").replace("تومان", "").replace("نامشخص", "").strip()
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
        model_value_with_increase = model_value * 1.015
        return f"{model_value_with_increase:,.0f}"
    return model_str

def escape_markdown(text):
    escape_chars = ['\\', '(', ')', '[', ']', '~', '*', '_', '-', '+', '>', '#', '.', '!', '|']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text

def split_message(message, max_length=4000):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

def decorate_line(line):
    if line.startswith(('🔵', '🟡', '🍏', '🟣', '💻', '🟠')):
        return line
    if any(keyword in line for keyword in ["Nartab", "Tab"]):
        return f"🟠 {line}"
    elif "Galaxy" in line:
        return f"🔵 {line}"
    elif "POCO" in line or "Poco" in line or "Redmi" in line:
        return f"🟡 {line}"
    elif "iPhone" in line:
        return f"🍏 {line}"
    elif any(keyword in line for keyword in ["اینچی"]):
        return f"💻 {line}"
    elif any(keyword in line for keyword in ["RAM", "FA", "Classic"]):
        return f"🟣 {line}"
    else:
        return line

def categorize_messages(lines):
    categories = {"🔵": [], "🟡": [], "🍏": [], "🟣": [], "💻": [], "🟠": []}  # اضافه کردن 🟠 برای تبلت
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

        if current_category:
            categories[current_category].append(f"{line}")

    return categories

def get_header_footer(category, update_date):
    headers = {
        "🔵": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی سامسونگ ➡️\n",
        "🟡": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی شیایومی ➡️\n",
        "🍏": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی آیفون ➡️\n",
        "🟣": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی متفرقه ➡️\n",
        "💻": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی لپ‌تاپ ➡️\n",
        "🟠": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی تبلت ➡️\n",  # اضافه کردن هدر برای تبلت
    }
    footer = "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"
    return headers[category], footer

def send_telegram_message(message, bot_token, chat_id, reply_markup=None):
    message_parts = split_message(message)
    last_message_id = None
    for part in message_parts:
        part = escape_markdown(part)
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": part,
            "parse_mode": "MarkdownV2"
        }
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)  # ✅ تبدیل `reply_markup` به JSON

        headers = {"Content-Type": "application/json"}  # ✅ اضافه کردن `headers` برای `POST`
        response = requests.post(url, json=params, headers=headers)  
        response_data = response.json()
        if response_data.get('ok'):
            last_message_id = response_data["result"]["message_id"]
        else:
            logging.error(f"❌ خطا در ارسال پیام: {response_data}")
            return None

    logging.info("✅ پیام ارسال شد!")
    return last_message_id  # برگشت message_id آخرین پیام


def get_last_messages(bot_token, chat_id, limit=5):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    response = requests.get(url)
    if response.json().get("ok"):
        messages = response.json().get("result", [])
        return [msg for msg in messages if "message" in msg][-limit:]
    return []

def main():
    try:
        driver = get_driver()
        if not driver:
            logging.error("❌ نمی‌توان WebDriver را ایجاد کرد.")
            return
        
        # استخراج موبایل
        driver.get('https://hamrahtel.com/quick-checkout?category=mobile')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)

        valid_brands = ["Galaxy", "POCO", "Redmi", "iPhone", "Redtone", "VOCAL", "TCL", "NOKIA", "Honor", "Huawei", "GLX", "+Otel", "اینچی" ]
        brands, models = extract_product_data(driver, valid_brands)

        # استخراج لپ‌تاپ
        driver.get('https://hamrahtel.com/quick-checkout?category=laptop')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)

        laptop_brands, laptop_models = extract_product_data(driver, valid_brands)
        brands.extend(laptop_brands)
        models.extend(laptop_models)

        # استخراج تبلت
        driver.get('https://hamrahtel.com/quick-checkout?category=tablet')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)

        tablet_brands, tablet_models = extract_product_data(driver, valid_brands)
        brands.extend(tablet_brands)
        models.extend(tablet_models)

        driver.quit()

        samsung_message_id = None
        xiaomi_message_id = None
        iphone_message_id = None
        laptop_message_id = None
        tablet_message_id = None

        if brands:  # 👈 اینجا باید تو رفتگی داشته باشه
            processed_data = []
            for i in range(len(brands)):
                model_str = process_model(models[i])
                try:
                    price = float(model_str.replace(",", ""))
                except ValueError:
                    price = float("inf")
                full_text = f"{model_str} {brands[i]}"
                decorated = decorate_line(full_text)
                processed_data.append((price, decorated))

            processed_data.sort(key=lambda x: x[0])
            message_lines = [item[1] for item in processed_data]

            update_date = JalaliDate.today().strftime("%Y-%m-%d")
            categories = categorize_messages(message_lines)

            for category, lines in categories.items():
                if lines:
                    header, footer = get_header_footer(category, update_date)
                    message = header + "\n" + "\n".join(lines) + footer
                    msg_id = send_telegram_message(message, BOT_TOKEN, CHAT_ID)

                    if category == "🔵":
                        samsung_message_id = msg_id
                    elif category == "🟡":
                        xiaomi_message_id = msg_id
                    elif category == "🍏":
                        iphone_message_id = msg_id
                    elif category == "💻":
                        laptop_message_id = msg_id
                    elif category == "🟠":
                        tablet_message_id = msg_id
        else:
            logging.warning("❌ داده‌ای برای ارسال وجود ندارد!")

        if not samsung_message_id:
            logging.error("❌ پیام سامسونگ ارسال نشد، دکمه اضافه نخواهد شد!")
            return

        final_message = (
            "✅ لیست گوشیای بالا بروز میباشد. تحویل کالا بعد از ثبت خرید، ساعت 11:30 صبح روز بعد می باشد.\n\n"
            "✅ شماره کارت جهت واریز\n"
            "🔷 شماره شبا : IR970560611828006154229701\n"
            "🔷 شماره کارت : 6219861812467917\n"
            "🔷 بلو بانک   حسین گرئی\n\n"
            "⭕️ حتما رسید واریز به ایدی تلگرام زیر ارسال شود .\n"
            "🆔 @lhossein1\n\n"
            "✅شماره تماس ثبت سفارش :\n"
            "📞 09371111558\n"
            "📞 02833991417"
        )

        button_markup = {"inline_keyboard": []}
        if samsung_message_id:
            button_markup["inline_keyboard"].append([{"text": "📱 لیست سامسونگ", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{samsung_message_id}"}])
        if xiaomi_message_id:
            button_markup["inline_keyboard"].append([{"text": "📱 لیست شیایومی", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{xiaomi_message_id}"}])
        if iphone_message_id:
            button_markup["inline_keyboard"].append([{"text": "📱 لیست آیفون", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{iphone_message_id}"}])
        if laptop_message_id:
            button_markup["inline_keyboard"].append([{"text": "💻 لیست لپ‌تاپ", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{laptop_message_id}"}])
        if tablet_message_id:
            button_markup["inline_keyboard"].append([{"text": "📱 لیست تبلت", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{tablet_message_id}"}])
    
        send_telegram_message(final_message, BOT_TOKEN, CHAT_ID, reply_markup=button_markup)

    except Exception as e:
        logging.error(f"❌ خطا: {e}")


if __name__ == "__main__":
    main()
