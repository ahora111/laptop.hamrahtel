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

# تنظیمات تلگرام
BOT_TOKEN = "8187924543:AAH0jZJvZdpq_34um8R_yCyHQvkorxczXNQ"
CHAT_ID = "-1002284274669"

# تنظیمات لاگ‌گیری
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service()
    return webdriver.Chrome(service=service, options=options)

def scroll_page(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
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
def escape_markdown_v2(text):
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in text)

def send_telegram_message(message, bot_token, chat_id):
    escaped_message = escape_markdown_v2(message)  # ✅ اصلاح متن قبل از ارسال
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": escaped_message, "parse_mode": "MarkdownV2"})
    response_data = response.json()
    if response_data.get('ok'):
        return response_data["result"]["message_id"]
    else:
        logging.error(f"❌ خطا در ارسال پیام: {response_data}")
        return None


def process_category(driver, url, category_name, icon, valid_brands):
    driver.get(url)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
    scroll_page(driver)

    brands, models = extract_product_data(driver, valid_brands)
    if not brands:
        logging.warning(f"❌ هیچ داده‌ای برای {category_name} یافت نشد!")
        return None

    update_date = JalaliDate.today().strftime("%Y-%m-%d")
    header = f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ {category_name} ➡️\n"
    footer = "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"

    message = header + "\n".join([f"{icon} {models[i]} {brands[i]}" for i in range(len(brands))]) + footer
    return send_telegram_message(message, BOT_TOKEN, CHAT_ID)

def main():
    driver = get_driver()
    
    phone_brands = ["Galaxy", "POCO", "Redmi", "iPhone"]
    laptop_brands = ["Asus", "Lenovo", "MSI", "MacBook", "Acer", "HP", "Dell"]

    samsung_message_id = process_category(driver, "https://hamrahtel.com/quick-checkout", "موجودی سامسونگ", "🔵", phone_brands)
    xiaomi_message_id = process_category(driver, "https://hamrahtel.com/quick-checkout", "موجودی شیایومی", "🟡", phone_brands)
    iphone_message_id = process_category(driver, "https://hamrahtel.com/quick-checkout", "موجودی آیفون", "🍏", phone_brands)
    laptop_message_id = process_category(driver, "https://hamrahtel.com/quick-checkout?category=laptop", "موجودی لپ‌تاپ", "💻", laptop_brands)

    driver.quit()

    # ارسال پیام نهایی
    final_message = (
        "✅ لیست بالا بروز می‌باشد. تحویل کالا بعد از ثبت خرید، ساعت 11:30 صبح روز بعد می‌باشد.\n\n"
        "✅ شماره کارت جهت واریز\n"
        "🔷 شماره شبا : IR970560611828006154229701\n"
        "🔷 شماره کارت : 6219861812467917\n"
        "🔷 بلو بانک   حسین گرئی\n\n"
        "⭕️ حتما رسید واریز به ایدی تلگرام زیر ارسال شود:\n"
        "🆔 @lhossein1\n\n"
        "✅ شماره تماس ثبت سفارش:\n"
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

    send_telegram_message(final_message, BOT_TOKEN, CHAT_ID)

if __name__ == "__main__":
    main()
