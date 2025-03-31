#!/usr/bin/env python3
import os
import time
import requests
import logging
import threading
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from persiantools.jdatetime import JalaliDate

# تنظیمات مربوط به تلگرام
BOT_TOKEN = "8187924543:AAH0jZJvZdpq_34um8R_yCyHQvkorxczXNQ"
CHAT_ID = "-1002284274669"

# تنظیمات لاگ‌گیری
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

def categorize_messages(lines):
    categories = {"🔵": [], "🟡": [], "🍏": [], "🟣": [], "💻": []}
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

        if current_category:
            categories[current_category].append(line)

    return categories

def get_header_footer(category, update_date):
    headers = {
        "🔵": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی سامسونگ ➡️\n",
        "🟡": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی شیایومی ➡️\n",
        "🍏": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی آیفون ➡️\n",
        "🟣": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی متفرقه ➡️\n",
        "💻": f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی لپ‌تاپ ➡️\n",
    }
    footer = "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"
    return headers[category], footer

def main():
    try:
        urls = {
            "mobile": "https://hamrahtel.com/quick-checkout",
            "laptop": "https://hamrahtel.com/quick-checkout?category=laptop"
        }
        
        category_message_ids = {}
        for category, url in urls.items():
            driver = get_driver()
            if not driver:
                logging.error(f"❌ نمی‌توان WebDriver را برای {category} ایجاد کرد.")
                continue
            
            driver.get(url)
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
            logging.info(f"✅ داده‌ها آماده‌ی استخراج هستند برای {category}!")
            scroll_page(driver)

            valid_brands = ["Galaxy", "POCO", "Redmi", "iPhone", "Redtone", "VOCAL", "TCL", "NOKIA", "Honor", "Huawei", "GLX", "+Otel"]
            brands, models = extract_product_data(driver, valid_brands)
            driver.quit()

            if brands:
                update_date = JalaliDate.today().strftime("%Y-%m-%d")
                categories = categorize_messages(models)

                for cat, lines in categories.items():
                    if lines:
                        header, footer = get_header_footer(cat, update_date)
                        message = header + "\n" + "\n".join(lines) + footer
                        msg_id = send_telegram_message(message, BOT_TOKEN, CHAT_ID)
                        if msg_id:
                            category_message_ids[cat] = msg_id

        final_message = "✅ لیست گوشیای بالا بروز میباشد. ... (متن ثابت)"
        button_markup = {"inline_keyboard": []}
        for cat, msg_id in category_message_ids.items():
            button_markup["inline_keyboard"].append([{"text": f"📱 لیست {cat}", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{msg_id}"}])
        
        send_telegram_message(final_message, BOT_TOKEN, CHAT_ID, reply_markup=button_markup)
    except Exception as e:
        logging.error(f"❌ خطا: {e}")

if __name__ == "__main__":
    main()
