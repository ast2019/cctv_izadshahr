<div dir="rtl">

# Frigate — ایزدشهر

سه نمونه‌ی Frigate (نسخه‌ی `0.16.3`) که با یک `docker-compose.yml` ساده بالا
می‌آیند. کانفیگ هر داکر یک فایل مستقل و مستقیم است؛ آن را ویرایش می‌کنی و داکر
را بالا می‌آوری. خبری از قالب/رندر/پیچیدگی اضافه نیست.

## نمونه‌ها

| نمونه       | پورت UI | پورت RTSP | پورت WebRTC | کانتینر            | کانفیگ                   |
|-------------|---------|-----------|-------------|--------------------|--------------------------|
| `cafe`      | 8972    | 8556      | 8557        | `frigate-cafe`     | `config/cafe/config.yml` |
| `center11`  | 8973    | 8558      | 8559        | `frigate-center11` | `config/center11/config.yml` |
| `center22`  | 8974    | 8560      | 8561        | `frigate-center22` | `config/center22/config.yml` |

## ساختار

<div dir="ltr">

```
docker-compose.yml        # سه سرویس frigate
config/
  cafe/config.yml         # کانفیگ واقعی کافه (۱۳ دوربین)
  center11/config.yml     # اسکلت — آماده‌ی پر کردن
  center22/config.yml     # اسکلت — آماده‌ی پر کردن
.env                      # فقط رمزها (در گیت نیست)
.env.example
media/                    # ضبط‌ها (در گیت نیست، خودکار ساخته می‌شود)
```

</div>

## راه‌اندازی

<div dir="ltr">

```bash
# ۱) رمز مشترک را بگذار (یک رمز برای همه‌ی دوربین‌های همه‌ی نمونه‌ها)
cp .env.example .env
nano .env            # FRIGATE_RTSP_PASSWORD=<رمز دوربین>

# ۲) فعلاً فقط کافه را بالا بیاور (center11/center22 هنوز دوربین ندارند)
docker compose up -d frigate-cafe

# لاگ:
docker compose logs -f frigate-cafe
```

</div>

UI کافه: `http://SERVER_IP:8972`

## افزودن / تغییر دوربین

فقط فایل `config/<instance>/config.yml` را ویرایش کن. الگوی بهینه (فقط ضبط،
یک اتصال به هر دوربین، کیفیت کامل، CPU حداقلی):

<div dir="ltr">

```yaml
go2rtc:
  streams:
    my_cam:
      - rtsp://admin:{FRIGATE_RTSP_PASSWORD}@192.168.51.204:554/cam/realmonitor?channel=1&subtype=0

cameras:
  my_cam:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/my_cam   # از restream داخلی، نه مستقیم دوربین
          input_args: preset-rtsp-restream
          roles: [record]
```

</div>

قواعد:
- **IP و یوزرنیم** مستقیم داخل کانفیگ نوشته می‌شوند.
- **رمز** فقط با `{FRIGATE_RTSP_PASSWORD}` نوشته می‌شود (یک رمز مشترک برای همه) و
  مقدار واقعی‌اش در `.env` است تا در گیت درز نکند.
- go2rtc هر دوربین را **یک‌بار** می‌گیرد؛ ضبط از restream می‌خواند → فشار کم روی
  دوربین/DVR، بدون re-encode، کیفیت بومی.
- بعد از ویرایش:

<div dir="ltr">

```bash
docker compose restart frigate-cafe
```

</div>

## افزودن یک نمونه‌ی جدید

۱. یک سرویس جدید مثل بقیه در `docker-compose.yml` اضافه کن (با پورت‌های یکتا).
۲. یک `config/<name>/config.yml` بساز.
۳. رمز مشترک `FRIGATE_RTSP_PASSWORD` از قبل هست؛ اگر این نمونه رمز جداگانه دارد،
   یک خط جدید به `.env` اضافه کن و در کانفیگش از همان نام استفاده کن.
۴. `docker compose up -d frigate-<name>`.

## اعتبارسنجی

<div dir="ltr">

```bash
docker compose config -q          # صحت docker-compose
```

</div>

## نکته‌ها

- کانفیگ کافه **ضبط (record) روشن** با نگه‌داری ۲ روز است. برای خاموش‌کردن،
  در `config/cafe/config.yml` مقدار `record.enabled` را `false` کن.
- هر نمونه پوشه‌ی `config` و `media` جداگانه، `tmpfs` روی `/tmp/cache` و لاگ
  JSON چرخشی دارد.
- فایل `frigate.db` هر نمونه داخل پوشه‌ی `config/<instance>/` ساخته می‌شود و در
  گیت نادیده گرفته می‌شود؛ آن را پاک نکن (تاریخچه و تنظیمات داخلش است).
- بدون GPU/NVIDIA/Coral — همه‌چیز روی CPU است.

</div>
