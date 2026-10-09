<div dir="rtl">

# Frigate — ایزدشهر

هفت نمونه‌ی Frigate (`0.16.3`) با یک `docker-compose.yml`. هر نمونه کانفیگ
مستقل دارد؛ ویرایش کانفیگ → ری‌استارت همان سرویس.

## نمونه‌ها

| نمونه       | پورت UI | پورت RTSP | کانتینر            | کانفیگ                   |
|-------------|---------|-----------|--------------------|--------------------------|
| `cafe`      | 8972    | 8556      | `frigate-cafe`       | `config/cafe/config.yml` |
| `center11`  | 8973    | 8558      | `frigate-center11`   | `config/center11/config.yml` |
| `center22`  | 8974    | 8560      | `frigate-center22`   | `config/center22/config.yml` |
| `restaurant`| 8975    | 8562      | `frigate-restaurant` | `config/restaurant/config.yml` |
| `sahel`     | 8976    | 8564      | `frigate-sahel`      | `config/sahel/config.yml` |
| `villa`     | 8977    | 8566      | `frigate-villa`      | `config/villa/config.yml` |
| `mahoote`   | 8978    | 8568      | `frigate-mahoote`    | `config/mahoote/config.yml` |
| **portal**  | **8888** | —        | `cctv-portal`        | `portal/` (صفحه ورود) |

## ساختار

<div dir="ltr">

```
docker-compose.yml
docs/CAMERAS.md              # موجودی کامل دوربین‌ها (IP، رمز RTSP، وضعیت)
config/
  cafe/config.yml
  center11/config.yml
  center22/config.yml
  restaurant/config.yml
  sahel/config.yml
  villa/config.yml
  mahoote/config.yml
scripts/sync-frigate-users.sh   # همگام‌سازی کاربران UI
.cursor/rules/                  # قوانین پروژه برای AI
media/                          # ضبط‌ها (در گیت نیست)
```

</div>

## قوانین پروژه (خلاصه)

این قوانین در `.cursor/rules/frigate-project.mdc` هم هست تا هر AI که روی
پروژه کار کند آن‌ها را ببیند.

### دوربین‌ها

- **لیست کامل** همه دوربین‌ها (فعال، آفلاین، planned، تکراری): [`docs/CAMERAS.md`](docs/CAMERAS.md)
- قبل از افزودن دوربین، آن فایل و قوانین تکراری را چک کن.

### دوربین‌ها — قوانین کانفیگ

- **نام‌گذاری IP**: `cam_<آخرین اکتت IP>` — مثلاً `cam_5` برای `192.168.51.5`
- **نام‌گذاری DVR**: `dvr_<site>_ch<N>` — مثلاً `dvr_cafe_ch3`
- **بدون تکرار**: هر دوربین فقط در **یک** نمونه Frigate باشد. قبل از اضافه
  کردن، همه‌ی `config/*/config.yml` را grep کن.
- **رمز دوربین (RTSP)**: مستقیم داخل URL در همان `config.yml` بنویس
  (`rtsp://admin:admin123@192.168.51.5:554/...`). از `.env` استفاده **نکن**.
- **الگوی go2rtc**: یک استریم go2rtc + ضبط از restream داخلی:

<div dir="ltr">

```yaml
go2rtc:
  streams:
    cam_5:
      - rtsp://admin:admin123@192.168.51.5:554/Streaming/Channels/102

cameras:
  cam_5:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/cam_5
          input_args: preset-rtsp-restream
          roles: [record]
```

</div>

### لاگین پنل Frigate (جدا از رمز دوربین)

| چیز | کجاست | توضیح |
|-----|--------|--------|
| رمز RTSP دوربین | `config/<instance>/config.yml` | برای اتصال به دوربین/DVR |
| رمز لاگین پنل UI | `frigate.db` هر نمونه | کاربر `admin`، `ceo` و ... |

**رمز `.env` دیگر استفاده نمی‌شود.** فایل `.env.example` فقط برای سازگاری
قدیمی مانده؛ `docker-compose` دیگر آن را نمی‌خواند.

#### پیدا کردن رمز admin موقت (اولین بالا آمدن)

<div dir="ltr">

```bash
docker compose logs frigate-cafe 2>&1 | grep -i password
# خروجی نمونه:
# ***    User: admin                                   ***
# ***    Password: 1fb5b5c51ac5fb31fa5762024be1a0a7   ***
```

</div>

#### ریست رمز admin

در `config.yml` موقت اضافه کن، ری‌استارت، رمز را از لاگ بخوان، بعد خط را حذف کن:

<div dir="ltr">

```yaml
auth:
  reset_admin_password: true
```

</div>

#### یکسان‌سازی رمز admin و کاربر viewer (`ceo`)

<div dir="ltr">

```bash
# لاگین با رمز موقت
TOKEN=$(curl -sk -X POST https://localhost:8972/api/login \
  -H "Content-Type: application/json" \
  -d '{"user":"admin","password":"<temp_from_log>"}' \
  -c - | awk '/frigate_token/ {print $7}')

# ست کردن رمز admin دلخواه
curl -sk -X PUT https://localhost:8972/api/users/admin/password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password":"YOUR_DESIRED_PASSWORD"}'

# ساخت کاربر viewer
curl -sk -X POST https://localhost:8972/api/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"ceo","password":"Ceo@1405!","role":"viewer"}'
```

</div>

یا برای همه‌ی نمونه‌های در حال اجرا:

<div dir="ltr">

```bash
ADMIN_PASSWORD='YourAdminPass!' ./scripts/sync-frigate-users.sh
```

</div>

> **توجه**: هر نمونه Frigate دیتابیس کاربر جدا دارد. لاگین واحد واقعی بین
> همه‌ی نمونه‌ها نیاز به reverse proxy (Authelia/nginx) دارد — بعداً.

## صفحه ورود (Portal)

آدرس: **http://SERVER_IP:8888**

کارت هر بخش → کلیک → پنل Frigate همان بخش (پورت 8972/8973/8974).
وضعیت آنلاین از API داخلی؛ آمار دوربین در صورت دسترسی به API.

<div dir="ltr">

```bash
docker compose up -d portal
```

</div>

## راه‌اندازی

<div dir="ltr">

```bash
docker compose up -d frigate-cafe
docker compose up -d frigate-center11
docker compose logs -f frigate-center11
```

</div>

## تخصیص دوربین‌ها (فعلی)

جزئیات کامل IP و RTSP: [`docs/CAMERAS.md`](docs/CAMERAS.md)

| نمونه | دوربین‌ها |
|-------|-----------|
| cafe | DVR ch1–8 + سه دوربین IP کافه |
| center11 | cam_4,5,6,9,41 + پذیرش (۳ دوربین) |
| center22 | parking_villa |
| restaurant | restoran_bala/paeen/sandogh + cam_13 |
| sahel | ۳ دوربین |
| villa | ۲ دوربین |
| mahoote | generator |

## بازیابی خودکار (watchdog)

`restart: unless-stopped` فقط وقتی کمک می‌کند که پروسه **خارج** شود.
اگر Frigate هنگ کند، کانتینر «Up» می‌ماند ولی `/api/stats` جواب نمی‌دهد و
`latest.jpg` لود نمی‌شود.

سرویس `frigate-watchdog` هر ~۴۵ ثانیه هر نمونه را از API داخلی پورت `5000`
چک می‌کند:

- API تایم‌اوت / بی‌پاسخ → هنگ
- API بالا است ولی هیچ دوربینی `camera_fps > 0` ندارد **و** JPEG هم لود
  نمی‌شود (بعد از ~۹۰ ثانیه بالا آمدن) → تصویر مرده
- یک دوربین خراب به‌تنهایی ری‌استارت کل نمونه را تریگر نمی‌کند
- نمونهٔ `temp` (دوربین‌های در حال بررسی) اگر همه خراب باشند **هنگ نیست** و ری‌استارت نمی‌شود
- بعد از ۳ چک ناموفق پشت‌سرهم همان کانتینر ری‌استارت می‌شود
- کول‌داون ۵ دقیقه و سقف ۳ ری‌استارت در ساعت برای هر نمونه
- اگر بیش از نیمی از نمونه‌ها هم‌زمان مرده باشند (قطع شبکه/هاست)، ری‌استارت
  دسته‌جمعی انجام نمی‌شود
- اگر Frigateها سالم باشند و خود پورتال جواب ندهد، `cctv-portal` ری‌استارت
  می‌شود

وضعیت در پنل ادمین و فایل `data/watchdog/status.json` است.

<div dir="ltr">

```bash
sudo docker compose up -d frigate-watchdog
sudo docker compose logs -f frigate-watchdog
```

</div>

## اعلام قطعی دوربین به سامانه IT

سرویس `camera-ticket-notifier` هر دقیقه `camera_fps` نمونه‌های Frigate را چک
می‌کند. اگر دوربینی چند بار پشت‌سرهم قطع بماند، یک تسک یک‌طرفه به API سامانه
IT می‌زند (`POST /api/v1/tasks`) با:

- `assignee_username`: **فرجی** (`faraji`)
- `collaborator_usernames`: **بهرامی**، **صحراگرد** (`bahrami`, `sahragard`)

### رفتار مهم

- `external_id` ثابت: `camera-{site}-{name}-offline` — اسپم تسک تکراری نمی‌سازد
- نمونهٔ `temp` هرگز تیکت نمی‌گیرد
- اولین روشن شدن هر نمونه: دوربین‌های ازقبل‌قطع فقط ثبت می‌شوند، تسک نمی‌سازند
  (مگر `IT_TASKS_BOOTSTRAP_TICKET=1`)
- بازیابی دوربین تسک IT را نمی‌بندد

### پارامترها (به زبان ساده)

| متغیر | پیش‌فرض | معنی |
|-------|---------|------|
| `IT_TASKS_ENABLED` | `0` | روشن/خاموش اعلام واقعی به IT |
| `IT_TASKS_DRY_RUN` | `0` | `1` = فقط لاگ؛ به IT نمی‌زند |
| `IT_TASKS_API_KEY` | خالی | کلید Bearer از ادمین IT |
| `IT_TASKS_CYCLE_SEC` | `60` | هر چند ثانیه یک‌بار چک کند |
| `IT_TASKS_FAIL_THRESHOLD` | `3` | چند بار پشت‌سرهم قطع ببیند بعد تسک (~۳ دقیقه) |
| `IT_TASKS_BOOTSTRAP_TICKET` | `0` | روز اول برای قطع‌های قبلی هم تسک بسازد؟ معمولاً نه |
| `IT_TASKS_ASSIGNEE` | `faraji` | یوزرنیم مسئول در IT |
| `IT_TASKS_COLLABORATORS` | `bahrami,sahragard` | یوزرنیم همکاران |
| `IT_TASKS_ALLOWLIST` | خالی | اگر پر باشد فقط همان‌ها (`site:camera,...`) |

کلید را در `.env` سرور بگذار (نمونه در [`.env.example`](.env.example)). در گیت commit نکن.

### تست امن

<div dir="ltr">

```bash
# فقط لاگ — بدون تسک واقعی
IT_TASKS_ENABLED=1 IT_TASKS_DRY_RUN=1 IT_TASKS_API_KEY=sk_xxx \
  sudo docker compose up -d camera-ticket-notifier
sudo docker compose logs -f camera-ticket-notifier

# یا فقط یک دوربین
IT_TASKS_ENABLED=1 IT_TASKS_DRY_RUN=0 IT_TASKS_API_KEY=sk_xxx \
  IT_TASKS_ALLOWLIST=center11:cam_5 \
  sudo docker compose up -d camera-ticket-notifier
```

</div>

وضعیت محلی: `data/camera-tickets/state.json`

## نکته‌ها

- فقط از پورت UI امن (`8972`/`8973`/`8974`) استفاده کن، نه `5000`.
- `frigate.db` را پاک نکن (تاریخچه و کاربران UI).
- بدون GPU — همه‌چیز CPU.

</div>
