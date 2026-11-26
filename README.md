# Mostafa MultiWidget for Windows

[فارسی](#فارسی) · [English](#english)

---

<a name="فارسی"></a>
## فارسی

برنامه‌ی همه‌کاره برای **ویندوز**: آی‌پی و کشور، سرعت لحظه‌ای اینترنت، دمای هوا و نرخ دلار، همه در یک‌جا.

نسخه‌ی اندروید در ریپازیتوری جدا: https://github.com/coxvpn/Mostafa-MultiWidget

ساخته‌شده توسط مصطفی ماندگاری.


### ویندوز

**ویژگی‌ها**
- پرچم، آی‌پی و (اختیاری) شهر و ارائه‌دهنده‌ی اینترنت.
- در سینی سیستم می‌نشیند: با زدن روی آیکون، یک پنجره‌ی کوچک کنار نوار وظیفه باز می‌شود و با کلیک بیرون از آن بسته می‌شود.
- سرعت دانلود و آپلود لحظه‌ای (با فیلترشکن، ترافیک یک بار شمرده می‌شود).
- دمای هوا (داده از Open-Meteo)، و حجم دانلود و آپلود امروز. تا وقتی شهری انتخاب نکرده باشید، شهر خودکار از روی آی‌پی تشخیص داده می‌شود؛ با فیلترشکن روشن، مکان فیلترشکن نشان داده می‌شود و از منو می‌توانید «تشخیص شهر» را بدون فیلترشکن دوباره بزنید.
- نرخ دلار (تومان) کنار سرعت، حجم و دما.
- آخرین نرخ دلار ذخیره می‌شود تا بعد از باز کردن دوباره‌ی برنامه نوار خالی نماند (تا دو روز). اگر منبع اصلی باز نشد، می‌توان یک سرویس دوم را با گذاشتن کلید آن در `rate_api_key` داخل فایل `%APPDATA%\\MyIPWidget\\settings.json` به‌عنوان پشتیبان فعال کرد (سرویس دوم رایگان نیست).
- نوار کوچک کنار ساعت (داخل نوار وظیفه) با سرعت دانلود و آپلود، حجم امروز، دما و دلار. بعد از نصب خودکار اجرا می‌شود و گزینه‌ی «اجرا با ویندوز» به‌صورت پیش‌فرض تیک‌دار است.
- سرعت، حجم، هوا و دلار هرکدام از منوی راست‌کلیک قابل خاموش شدن هستند.
- بدون اینترنت، کره‌ی زمین با خط قرمز نشان داده می‌شود.
- منوی راست‌کلیک: کپی آی‌پی، به‌روزرسانی، شفافیت، ماندن روی دسکتاپ، اجرا با ویندوز، خروج.
- با دو بار کلیک روی ویجت، آی‌پی کپی می‌شود.
- موقعیت و تنظیمات را به یاد می‌سپارد و با تم تیره و روشن ویندوز هماهنگ است.
- فقط یک نسخه همزمان اجرا می‌شود.
<img width="2322" height="1317" alt="guide" src="https://github.com/user-attachments/assets/0c9e5891-9235-45cb-85a1-6dc8756fdf3b" />
<img width="1560" height="906" alt="themess" src="https://github.com/user-attachments/assets/02c9b57b-3bb3-41d7-8c58-17c2a25102cc" />

<img width="659" height="260" alt="image" src="https://github.com/user-attachments/assets/1441be84-2023-464d-91a1-6b8d800172f5" />


**راهنما**
1. `Mostafa-MultiWidget-Setup.exe` را اجرا کنید و نصب را تمام کنید.
2. آیکون برنامه در سینی سیستم (کنار ساعت) ظاهر می‌شود؛ روی آن کلیک کنید.
3. برای دمای هوا: راست‌کلیک ← انتخاب شهر ← نام شهر را جستجو کنید.
4. برای اجرا با روشن شدن ویندوز: راست‌کلیک ← اجرا با ویندوز.
5. برای ماندن ویجت روی دسکتاپ: راست‌کلیک ← ماندن روی دسکتاپ.

تنظیمات و یک فایل گزارش کوچک در پوشه‌ی `%APPDATA%\MyIPWidget` هستند. اگر آنتی‌ویروس هشدار داد، به‌خاطر ساخته شدن فایل با PyInstaller است و برنامه‌ی دیگری با آن مشکل ندارد.

**ساخت از کد:** با هر push به شاخه‌ی main (یا اجرای دستی گردش‌کار **Build Windows installer** در تب Actions) نصب‌کننده ساخته و یک Release منتشر می‌شود. شماره‌ی نسخه از `__version__` در `ipcore.py` خوانده می‌شود. یا از کد: `pip install -r requirements.txt` و `python main.py`.

---

<a name="english"></a>
## English

An all-in-one app for **Windows**: IP address and country, live internet speed, weather and the dollar rate, all in one place.

The Android version has its own repository: https://github.com/coxvpn/Mostafa-MultiWidget

Made by Mostafa Mandegari.


### Windows

**Features**
- Flag, IP address and (optionally) city and provider.
- Lives in the system tray: click the tray icon and a small pop-up opens beside the taskbar; it closes when you click elsewhere.
- Live download and upload speed (with a VPN the traffic is counted once).
- Weather (data from Open-Meteo) and today's downloaded and uploaded volume. While no city is chosen, the city is found automatically from the IP; with a VPN on it shows the VPN's place, so use the "detect city" menu item again with the VPN off.
- The dollar rate (Toman) beside speed, volume and temperature.
- The last dollar rate is saved, so the bar is not empty after a restart (up to two days). If the main source cannot be read, a second service can be used as a backup by putting its key in `rate_api_key` in `%APPDATA%\\MyIPWidget\\settings.json` (that service is not free).
- A small bar beside the clock (built into the taskbar) with download/upload speed, today's volume, temperature and dollar. It starts by itself at the end of the setup, and "start with Windows" is ticked by default.
- Speed, volume, weather and dollar can each be switched off from the right-click menu.
- A globe with a red slash shows when there is no internet.
- Right-click menu: copy IP, refresh, opacity, keep on desktop, start with Windows, quit.
- Double-click the widget to copy the IP.
- Remembers position and settings, and follows the Windows dark/light theme.
- Only one copy runs at a time.

**Guide**
1. Run `Mostafa-MultiWidget-Setup.exe` and finish the setup.
2. The icon appears in the system tray (near the clock); click it.
3. For weather: right-click → choose city → search the city name.
4. To start with Windows: right-click → start with Windows.
5. To keep the widget on the desktop: right-click → keep on desktop.

Settings and a small log file live in `%APPDATA%\MyIPWidget`. If an antivirus warns, it is because the file is built with PyInstaller, not because of anything harmful.

**Build from source:** every push to `main` (or running the **Build Windows installer** workflow by hand in the Actions tab) builds the installer and publishes a Release `vX.Y.Z`. The version is read from `__version__` in `ipcore.py`. Or from code: `pip install -r requirements.txt` then `python main.py`.

---

## License and thanks

The code is open source. Thanks to B3H1Z for the original project.
