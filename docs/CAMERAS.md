<div dir="rtl">

# موجودی دوربین‌ها — cctv_izadshahr

منبع حقیقت (source of truth) برای همه‌ی دوربین‌ها، IP، یوزر/رمز RTSP، و وضعیت
استقرار. قبل از افزودن دوربین به هر `config.yml`، این فایل را بررسی کن.

**یوزر/رمز پیش‌فرض IP و DVR کافه:** `admin` / `admin123`

## راهنمای وضعیت

| وضعیت | معنی |
|--------|------|
| `active` | الان در یک نمونه Frigate فعال است |
| `planned` | در موجودی است، هنوز فعال نشده |
| `offline` | آفلاین یا موقتاً غیرفعال در کانفیگ |
| `duplicate_ip` | همان IP با نام دیگر هم وجود دارد — فقط یکی را فعال کن |

## تخصیص فعلی به نمونه‌های Frigate

هفت نمونه، گروه‌بندی‌شده بر اساس محل. یوزر همه `admin`. رمز دو نوع است:
`admin123` و `1259110@av` (در URLها `@` باید `%40` نوشته شود → `1259110%40av`).
مسیر همه‌ی دوربین‌های IP: هایک‌ویژن `/Streaming/Channels/102`.

| نمونه (service) | نقش | UI | فعال |
|-----------------|-----|----|------|
| **cafe** | کافه | 8972 | DVR ch1-8 + view_cafe_gharb(.52) + vorodi_cafe(.49) |
| **center11** | پذیرش و ورودی مجتمع | 8973 | cam_4,5,6,9,41 + paziresh_be_pol(.134) + paziresh_be_sahel(.135) + shargh_vorodi(.131) |
| **restaurant** | رستوران | 8975 | restoran_paeen(.136) + restoran_bala(.137) + restoran_sandogh(.14) + cam_13(.13) + ipcam_rest_100(.100) + ipcam_rest_101(.101) + ipcam_ashpazkhane_99(.99) |
| **sahel** | ساحل | 8976 | sahel_shargh(.54) + sahel_gharb_47(.47) + sahel_gharb_48(.48) + view_cafe_shargh(.53) |
| **villa** | ویلاها | 8977 | villa_ha(.51) + villa_ha_gharb(.12) |
| **mahoote** | محوطه | 8978 | generator(.10) + parking_villa(.132) |
| **center22** | پارکینگ | 8974 | ipcam_parking3_89(.89) + ipcam_parking3_90(.90) + dvr_parking4_ch1..5(.222) — در حال تست |

> رمز `1259110@av`: `.134,.135,.131,.136,.137,.51,.52,.53,.54,.47,.48,.49`
> رمز `admin123`: `.14,.12,.10,.132` (و همه‌ی cam_* مرکز و DVR کافه)

### در حال تست در center22 (تازه فعال‌شده — قبلاً planned)
- DVR پارکینگ۴ (`192.168.51.222`) — ۵ کانال، فرمت `.sdp` (بخش ۴) — فعال شد
- parking3 (`.89`, `.90`) — قبلاً timeout/استریم بی‌اعتبار داشت — فعال شد، نیاز به تأیید روی سرور

---

## ۱. کافه — DVR (`192.168.51.204`)

DVR داهوا/مشابه — مسیر اصلی ضبط: `subtype=0`، ساب‌استریم: `subtype=1`

| نام | کانال | وضعیت | نمونه | RTSP (ضبط — subtype=0) |
|-----|-------|--------|--------|-------------------------|
| `dvr_cafe_ch1` | 1 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=1&subtype=0` |
| `dvr_cafe_ch2` | 2 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=2&subtype=0` |
| `dvr_cafe_ch3` | 3 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=3&subtype=0` |
| `dvr_cafe_ch4` | 4 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=4&subtype=0` |
| `dvr_cafe_ch5` | 5 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=5&subtype=0` |
| `dvr_cafe_ch6` | 6 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=6&subtype=0` |
| `dvr_cafe_ch7` | 7 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=7&subtype=0` |
| `dvr_cafe_ch8` | 8 | **active** | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=8&subtype=0` |
| `dvr_cafe_ch10` | 10 | planned | cafe | `rtsp://admin:admin123@192.168.51.204:554/cam/realmonitor?channel=10&subtype=0` |

> ch10 قبلاً اشتباه فعال بود؛ با ch3 جایگزین شد. ch10 برای آینده در موجودی مانده.

---

## ۲. کافه — دوربین IP

| نام | IP | وضعیت | نمونه | RTSP ضبط | RTSP detect / یادداشت |
|-----|-----|--------|--------|----------|------------------------|
| `ipcam_parking3_90` | 192.168.51.90 | **active** | center22 | `rtsp://admin:admin123@192.168.51.90:554/Streaming/Channels/102` | **تکراری IP با cam_90** — cam_90 را فعال نکن — در حال تست |
| `ipcam_parking3_89` | 192.168.51.89 | **active** | center22 | `rtsp://admin:admin123@192.168.51.89:554/Streaming/Channels/102` | قبلاً timeout — در حال تست |
| `ipcam_ashpazkhane_99` | 192.168.51.99 | **active** | restaurant | `rtsp://admin:admin123@192.168.51.99:554/Streaming/Channels/102` | H.265 — ترجیحاً H.264 روی دوربین — در حال تست |
| `ipcam_rest_100` | 192.168.51.100 | **active** | restaurant | `rtsp://admin:admin123@192.168.51.100:554/Streaming/Channels/102` | قبلاً timeout — در حال تست |
| `ipcam_rest_101` | 192.168.51.101 | **active** | restaurant | `rtsp://admin:admin123@192.168.51.101:554/Streaming/Channels/102` | قبلاً timeout — در حال تست |

---

## ۳. مرکز — دوربین IP (`192.168.51.0/24`)

مسیر استاندارد: `/Streaming/Channels/102` — یوزر: `admin` — رمز: `admin123`

### فعال در center11

| نام | IP | وضعیت | RTSP |
|-----|-----|--------|------|
| `cam_4` | 192.168.51.4 | **active** | `rtsp://admin:admin123@192.168.51.4:554/Streaming/Channels/102` |
| `cam_5` | 192.168.51.5 | **active** | `rtsp://admin:admin123@192.168.51.5:554/Streaming/Channels/102` |
| `cam_6` | 192.168.51.6 | **active** | `rtsp://admin:admin123@192.168.51.6:554/Streaming/Channels/102` |
| `cam_9` | 192.168.51.9 | **active** | `rtsp://admin:admin123@192.168.51.9:554/Streaming/Channels/102` |
| `cam_13` | 192.168.51.13 | **active** (restaurant) | `rtsp://admin:admin123@192.168.51.13:554/Streaming/Channels/102` — منتقل‌شده به نمونه restaurant |
| `cam_41` | 192.168.51.41 | **active** | `rtsp://admin:admin123@192.168.51.41:554/Streaming/Channels/102` |

### آفلاین / غیرفعال موقت (center11)

| نام | IP | وضعیت | RTSP | یادداشت |
|-----|-----|--------|------|---------|
| `cam_14` | 192.168.51.14 | **duplicate_ip** | `rtsp://admin:admin123@192.168.51.14:554/Streaming/Channels/102` | همان IP الان به‌نام `restoran_sandogh` در نمونه restaurant **فعال** است — cam_14 را دوباره فعال نکن |
| `cam_16` | 192.168.51.16 | **offline** | `rtsp://admin:admin123@192.168.51.16:554/Streaming/Channels/102` | timeout |

### تست‌شده OK — هنوز فعال نشده (planned → center22 یا دسته بعدی)

> ⚠️ `cam_10` و `cam_12` و `cam_47` **دیگر planned نیستند** — با نام دیگر فعال شده‌اند (جدول IPهای تکراری، بخش ۵).

| نام | IP | RTSP |
|-----|-----|------|
| ~~`cam_10`~~ | 192.168.51.10 | فعال به‌نام `generator` در mahoote |
| ~~`cam_12`~~ | 192.168.51.12 | فعال به‌نام `villa_ha_gharb` در villa |
| `cam_30` | 192.168.51.30 | `rtsp://admin:admin123@192.168.51.30:554/Streaming/Channels/102` |
| ~~`cam_47`~~ | 192.168.51.47 | فعال به‌نام `sahel_gharb_47` در sahel |
| `cam_71` | 192.168.51.71 | `rtsp://admin:admin123@192.168.51.71:554/Streaming/Channels/102` |
| `cam_84` | 192.168.51.84 | `rtsp://admin:admin123@192.168.51.84:554/Streaming/Channels/102` |
| `cam_112` | 192.168.51.112 | `rtsp://admin:admin123@192.168.51.112:554/Streaming/Channels/102` |

### جدید — هنوز فعال نشده (planned)

| نام | IP | RTSP |
|-----|-----|------|
| `cam_2` | 192.168.51.2 | `rtsp://admin:admin123@192.168.51.2:554/Streaming/Channels/102` |
| `cam_3` | 192.168.51.3 | `rtsp://admin:admin123@192.168.51.3:554/Streaming/Channels/102` |
| `cam_7` | 192.168.51.7 | `rtsp://admin:admin123@192.168.51.7:554/Streaming/Channels/102` |
| `cam_8` | 192.168.51.8 | `rtsp://admin:admin123@192.168.51.8:554/Streaming/Channels/102` |
| `cam_18` | 192.168.51.18 | `rtsp://admin:admin123@192.168.51.18:554/Streaming/Channels/102` |
| `cam_19` | 192.168.51.19 | `rtsp://admin:admin123@192.168.51.19:554/Streaming/Channels/102` |
| `cam_20` | 192.168.51.20 | `rtsp://admin:admin123@192.168.51.20:554/Streaming/Channels/102` |
| `cam_21` | 192.168.51.21 | `rtsp://admin:admin123@192.168.51.21:554/Streaming/Channels/102` |
| `cam_24` | 192.168.51.24 | `rtsp://admin:admin123@192.168.51.24:554/Streaming/Channels/102` |
| `cam_25` | 192.168.51.25 | `rtsp://admin:admin123@192.168.51.25:554/Streaming/Channels/102` |
| `cam_27` | 192.168.51.27 | `rtsp://admin:admin123@192.168.51.27:554/Streaming/Channels/102` |
| `cam_31` | 192.168.51.31 | `rtsp://admin:admin123@192.168.51.31:554/Streaming/Channels/102` |
| `cam_42` | 192.168.51.42 | `rtsp://admin:admin123@192.168.51.42:554/Streaming/Channels/102` |
| `cam_43` | 192.168.51.43 | `rtsp://admin:admin123@192.168.51.43:554/Streaming/Channels/102` |
| `cam_44` | 192.168.51.44 | `rtsp://admin:admin123@192.168.51.44:554/Streaming/Channels/102` |
| `cam_45` | 192.168.51.45 | `rtsp://admin:admin123@192.168.51.45:554/Streaming/Channels/102` |
| `cam_46` | 192.168.51.46 | `rtsp://admin:admin123@192.168.51.46:554/Streaming/Channels/102` |
| ~~`cam_48`~~ | 192.168.51.48 | فعال به‌نام `sahel_gharb_48` در sahel |
| ~~`cam_49`~~ | 192.168.51.49 | فعال به‌نام `vorodi_cafe` در cafe |
| `cam_50` | 192.168.51.50 | `rtsp://admin:admin123@192.168.51.50:554/Streaming/Channels/102` |
| ~~`cam_51`~~ | 192.168.51.51 | فعال به‌نام `villa_ha` در villa |
| ~~`cam_52`~~ | 192.168.51.52 | فعال به‌نام `view_cafe_gharb` در cafe |
| ~~`cam_53`~~ | 192.168.51.53 | فعال به‌نام `view_cafe_shargh` در sahel |
| ~~`cam_54`~~ | 192.168.51.54 | فعال به‌نام `sahel_shargh` در sahel |
| `cam_65` | 192.168.51.65 | `rtsp://admin:admin123@192.168.51.65:554/Streaming/Channels/102` |
| `cam_81` | 192.168.51.81 | `rtsp://admin:admin123@192.168.51.81:554/Streaming/Channels/102` |
| `cam_82` | 192.168.51.82 | `rtsp://admin:admin123@192.168.51.82:554/Streaming/Channels/102` |
| `cam_83` | 192.168.51.83 | `rtsp://admin:admin123@192.168.51.83:554/Streaming/Channels/102` |
| `cam_85` | 192.168.51.85 | `rtsp://admin:admin123@192.168.51.85:554/Streaming/Channels/102` |
| `cam_88` | 192.168.51.88 | `rtsp://admin:admin123@192.168.51.88:554/Streaming/Channels/102` |
| ~~`cam_90`~~ | 192.168.51.90 | **تکراری IP** — `ipcam_parking3_90` در center22 فعال است؛ cam_90 را فعال نکن |
| `cam_91` | 192.168.51.91 | `rtsp://admin:admin123@192.168.51.91:554/Streaming/Channels/102` |
| `cam_92` | 192.168.51.92 | `rtsp://admin:admin123@192.168.51.92:554/Streaming/Channels/102` |
| `cam_93` | 192.168.51.93 | `rtsp://admin:admin123@192.168.51.93:554/Streaming/Channels/102` |
| `cam_94` | 192.168.51.94 | `rtsp://admin:admin123@192.168.51.94:554/Streaming/Channels/102` |
| `cam_95` | 192.168.51.95 | `rtsp://admin:admin123@192.168.51.95:554/Streaming/Channels/102` |
| `cam_96` | 192.168.51.96 | `rtsp://admin:admin123@192.168.51.96:554/Streaming/Channels/102` |
| `cam_97` | 192.168.51.97 | `rtsp://admin:admin123@192.168.51.97:554/Streaming/Channels/102` |
| `cam_98` | 192.168.51.98 | `rtsp://admin:admin123@192.168.51.98:554/Streaming/Channels/102` |
| `cam_203` | 192.168.51.203 | `rtsp://admin:admin123@192.168.51.203:554/Streaming/Channels/102` |

> `cam_201` (`.201`) همان دوربین فیزیکی `cam_41` (`.41`) است — **تکراری**؛ فقط `cam_41` فعال است.

---

## ۴. پارکینگ ۴ — DVR (`192.168.51.222`)

۵ کانال — انبار مرکزی + انبار خانه‌داری — هنوز فعال نشده (planned → center22)

یوزر: `admin` — رمز: `admin123` — فرمت URL متفاوت از DVR کافه:

| نام پیشنهادی | کانال | محل | وضعیت | RTSP |
|--------------|-------|-----|--------|------|
| `dvr_parking4_ch1` | 1 | پارکینگ۴ | planned | `rtsp://192.168.51.222:554/user=admin_password=admin123_channel=1_stream=0.sdp?real_stream` |
| `dvr_parking4_ch2` | 2 | پارکینگ۴ | planned | `rtsp://192.168.51.222:554/user=admin_password=admin123_channel=2_stream=0.sdp?real_stream` |
| `dvr_parking4_ch3` | 3 | پارکینگ۴ | planned | `rtsp://192.168.51.222:554/user=admin_password=admin123_channel=3_stream=0.sdp?real_stream` |
| `dvr_parking4_ch4` | 4 | انبار مرکزی | planned | `rtsp://192.168.51.222:554/user=admin_password=admin123_channel=4_stream=0.sdp?real_stream` |
| `dvr_parking4_ch5` | 5 | انبار خانه‌داری | planned | `rtsp://192.168.51.222:554/user=admin_password=admin123_channel=5_stream=0.sdp?real_stream` |

---

## ۵. IPهای تکراری (هشدار)

| IP | نام ۱ | نام ۲ | تصمیم |
|----|--------|--------|--------|
| `192.168.51.41` / `.201` | `cam_41` | `cam_201` | **همان دوربین** — فقط `cam_41` فعال |
| `192.168.51.90` | `ipcam_parking3_90` (center22) | `cam_90` (مرکز) | **ipcam_parking3_90 فعال است** — cam_90 را فعال نکن |
| `192.168.51.10` | `cam_10` (planned) | `generator` (mahoote) | **generator فعال است** — cam_10 را اضافه نکن |
| `192.168.51.12` | `cam_12` (planned) | `villa_ha_gharb` (villa) | **villa_ha_gharb فعال است** |
| `192.168.51.14` | `cam_14` (قبلاً offline در center11) | `restoran_sandogh` (restaurant) | **restoran_sandogh فعال است** — cam_14 را دوباره فعال نکن |
| `192.168.51.47` | `cam_47` (planned) | `sahel_gharb_47` (sahel) | **sahel_gharb_47 فعال است** |
| `192.168.51.48` | `cam_48` (planned) | `sahel_gharb_48` (sahel) | **sahel_gharb_48 فعال است** |
| `192.168.51.49` | `cam_49` (planned) | `vorodi_cafe` (cafe) | **vorodi_cafe فعال است** |
| `192.168.51.51` | `cam_51` (planned) | `villa_ha` (villa) | **villa_ha فعال است** |
| `192.168.51.52` | `cam_52` (planned) | `view_cafe_gharb` (cafe) | **view_cafe_gharb فعال است** |
| `192.168.51.53` | `cam_53` (planned) | `view_cafe_shargh` (sahel) | **view_cafe_shargh فعال است** |
| `192.168.51.54` | `cam_54` (planned) | `sahel_shargh` (sahel) | **sahel_shargh فعال است** |

---

## ۶. آمار

| دسته | تعداد |
|------|--------|
| DVR کافه (کل کانال‌ها) | 9 (۸ فعال + ch10 planned) |
| IP کافه | 5 (۰ planned — ۳ به restaurant، ۲ به center22 منتقل و فعال شد) |
| IP مرکز (کل pool) | 52 |
| IP مرکز فعال | 6 |
| IP مرکز offline | 1 (`cam_16` — `.14` الان به‌نام `restoran_sandogh` فعال است) |
| IP جدید (پذیرش/رستوران/پارکینگ: `.131,.132,.134,.135,.136,.137`) | 6 (همه فعال) |
| DVR پارکینگ۴ | 5 (همه فعال در center22 — در حال تست) |
| **جمع کل ورودی‌ها** | **77** |

> دوربین‌های فعال در همه‌ی نمونه‌ها: **۴۰** (۳۰ قبلی + ۳ رستوران + ۷ پارکینگ — در حال تست) (این عدد و جمع کل با `portal/js/sites.js` → `CAMERA_INVENTORY` هماهنگ نگه داشته شود.)

</div>
