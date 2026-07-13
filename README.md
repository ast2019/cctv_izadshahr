<div dir="rtl">

# Frigate — ایزدشهر

سه نمونه‌ی Frigate (`0.16.3`) با یک `docker-compose.yml`. هر نمونه کانفیگ
مستقل دارد؛ ویرایش کانفیگ → ری‌استارت همان سرویس.

## نمونه‌ها

| نمونه       | پورت UI | پورت RTSP | کانتینر            | کانفیگ                   |
|-------------|---------|-----------|--------------------|--------------------------|
| `cafe`      | 8972    | 8556      | `frigate-cafe`     | `config/cafe/config.yml` |
| `center11`  | 8973    | 8558      | `frigate-center11` | `config/center11/config.yml` |
| `center22`  | 8974    | 8560      | `frigate-center22` | `config/center22/config.yml` |
| **portal**  | **8888** | —        | `cctv-portal`      | `portal/` (صفحه ورود) |

## ساختار

<div dir="ltr">

```
docker-compose.yml
docs/CAMERAS.md              # موجودی کامل دوربین‌ها (IP، رمز RTSP، وضعیت)
config/
  cafe/config.yml
  center11/config.yml
  center22/config.yml
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
| cafe | DVR ch 1–8 (فعال)؛ ch10 + ۵ IP کافه (planned) |
| center11 | cam_4,5,6,9,13,41 (فعال)؛ cam_14,16 (offline) |
| center22 | DVR parking4 (۵ کانال) + بقیه IP مرکز (planned) |

## نکته‌ها

- فقط از پورت UI امن (`8972`/`8973`/`8974`) استفاده کن، نه `5000`.
- `frigate.db` را پاک نکن (تاریخچه و کاربران UI).
- بدون GPU — همه‌چیز CPU.

</div>
