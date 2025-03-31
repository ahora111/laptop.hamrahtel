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
BOT_TOKEN = "8187924543:AAH0zJvZdpq_34um8R_yCyHQvkorxczXNQ"
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

def scroll_page(driver):
    """اسکرول صفحه برای بارگذاری کامل داده‌ها"""
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
    
def is_number(model_str):
    try:
        float(model_str.replace(",", ""))
        return True
    except ValueError:
        return False
        
def process_category(url, valid_brands):
    driver = get_driver()
    if not driver:
        logging.error("❌ نمی‌توان WebDriver را ایجاد کرد.")
        return None, None
    
    driver.get(url)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
    logging.info("✅ داده‌ها آماده‌ی استخراج هستند!")
    
    scroll_page(driver)
    brands, models = extract_product_data(driver, valid_brands)
    driver.quit()
    
    return brands, models

def main():
    try:
        valid_brands = ["Galaxy", "POCO", "Redmi", "iPhone", "Redtone", "VOCAL", "TCL", "NOKIA", "Honor", "Huawei", "GLX", "+Otel"]
        brands, models = process_category('https://hamrahtel.com/quick-checkout', valid_brands)
        
        valid_laptop_brands = ["Asus", "Dell", "Lenovo", "HP", "Acer", "MSI", "MacBook", "Razer"]
        laptop_brands, laptop_models = process_category('https://hamrahtel.com/quick-checkout?category=laptop', valid_laptop_brands)
        
        samsung_message_id = None
        xiaomi_message_id = None
        iphone_message_id = None
        laptop_message_id = None

        if brands:
            processed_data = []
            for i in range(len(brands)):
                model_str = process_model(models[i])
                processed_data.append(f"{model_str} {brands[i]}")
            
            update_date = JalaliDate.today().strftime("%Y-%m-%d")
            message_lines = [decorate_line(row) for row in processed_data]
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

        if laptop_brands:
            processed_laptops = []
            for i in range(len(laptop_brands)):
                model_str = process_model(laptop_models[i])
                processed_laptops.append(f"{model_str} {laptop_brands[i]}")
            
            update_date = JalaliDate.today().strftime("%Y-%m-%d")
            message_lines = ["💻 " + line for line in processed_laptops]
            laptop_message = f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n✅ لیست پخش موبایل اهورا\n⬅️ موجودی لپ‌تاپ ➡️\n" + "\n".join(message_lines) + "\n\n☎️ شماره های تماس :\n📞 09371111558\n📞 02833991417"
            laptop_message_id = send_telegram_message(laptop_message, BOT_TOKEN, CHAT_ID)

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

        send_telegram_message(final_message, BOT_TOKEN, CHAT_ID, reply_markup=button_markup)

    except Exception as e:
        logging.error(f"❌ خطا: {e}")

if __name__ == "__main__":
    main()
