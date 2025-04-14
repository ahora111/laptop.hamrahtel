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
CHAT_ID = "-1002505490886"

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
        if model_value <= 7000000:
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

def escape_markdown(text):
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


# این تابع برای ساخت پیام نهایی به کار میره
def prepare_final_message(category_name, category_lines, update_date):
    # گرفتن عنوان دسته از روی ایموجی
    category_title = get_category_name(category_name)

    # ساخت هدر پیام
    header = (
        f"📅 بروزرسانی قیمت در تاریخ {update_date} می باشد\n"
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
    formatted_lines = [line for line in formatted_lines if not any(emoji in line for emoji in ["🔵", "🟡", "🍏", "🟣", "💻", "🟠", "🎮"]) or "|" not in line]

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
        
        driver.get('https://hamrahtel.com/quick-checkout?category=mobile')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))

        logging.info("✅ داده‌ها آماده‌ی استخراج هستند!")
        scroll_page(driver)

        valid_brands = ["Galaxy", "POCO", "Redmi", "iPhone", "Redtone", "VOCAL", "TCL", "NOKIA", "Honor", "Huawei", "GLX", "+Otel", "اینچی"]
        brands, models = extract_product_data(driver, valid_brands)
        
        # استخراج داده‌ها برای لپ‌تاپ، تبلت و کنسول
        driver.get('https://hamrahtel.com/quick-checkout?category=laptop')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)
        laptop_brands, laptop_models = extract_product_data(driver, valid_brands)
        brands.extend(laptop_brands)
        models.extend(laptop_models)

        driver.get('https://hamrahtel.com/quick-checkout?category=tablet')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)
        tablet_brands, tablet_models = extract_product_data(driver, valid_brands)
        brands.extend(tablet_brands)
        models.extend(tablet_models)

        driver.get('https://hamrahtel.com/quick-checkout?category=game-console')
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'mantine-Text-root')))
        scroll_page(driver)
        console_brands, console_models = extract_product_data(driver, valid_brands)
        brands.extend(console_brands)
        models.extend(console_models)

        driver.quit()

        # ذخیره message_id هر دسته‌بندی
        samsung_message_id = None
        xiaomi_message_id = None
        iphone_message_id = None
        laptop_message_id = None
        tablet_message_id = None
        console_message_id = None

        if brands:
            processed_data = []
            for i in range(len(brands)):
                model_str = process_model(models[i])
                processed_data.append(f"{model_str} {brands[i]}")

            update_date = JalaliDate.today().strftime("%Y-%m-%d")
            message_lines = []
            for row in processed_data:
                decorated = decorate_line(row)
                message_lines.append(decorated)

            categories = categorize_messages(message_lines)

            for category, lines in categories.items():
                if lines:
                    # استفاده از تابع جدید برای آماده‌سازی پیام
                    message = prepare_final_message(category, lines, update_date)
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
                    elif category == "🎮":
                        console_message_id = msg_id
        else:
            logging.warning("❌ داده‌ای برای ارسال وجود ندارد!")

        if not samsung_message_id:
            logging.error("❌ پیام سامسونگ ارسال نشد، دکمه اضافه نخواهد شد!")
            return

        # ✅ ارسال پیام نهایی + دکمه‌های لینک به پیام‌های مربوطه
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
        if console_message_id:
            button_markup["inline_keyboard"].append([{"text": "🎮 کنسول بازی", "url": f"https://t.me/c/{CHAT_ID.replace('-100', '')}/{console_message_id}"}])

        send_telegram_message(final_message, BOT_TOKEN, CHAT_ID, reply_markup=button_markup)

    except Exception as e:
        logging.error(f"❌ خطا: {e}")

if __name__ == "__main__":
    main()
