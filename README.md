<div dir="rtl">

# مخزن GitOps برای Frigate (ایزدشهر)

این مخزن، پیکربندی چند نمونه‌ی مستقل **Frigate 0.17.2** را به‌صورت
**GitOps** و **داده‌محور** مدیریت می‌کند. شما هرگز فایل‌های پیکربندی Frigate یا
Docker Compose را دستی ویرایش نمی‌کنید؛ فقط «اینونتوری» (inventory) را ویرایش
می‌کنید و اسکریپت رندر، همه‌چیز را تولید می‌کند.

## نمونه‌های فعلی

| نمونه       | پورت UI | پورت RTSP | پورت WebRTC (TCP/UDP) | کانتینر            |
|-------------|---------|-----------|------------------------|--------------------|
| `cafe`      | 8972    | 8556      | 8557                   | `frigate-cafe`     |
| `center11`  | 8973    | 8558      | 8559                   | `frigate-center11` |
| `center22`  | 8974    | 8560      | 8561                   | `frigate-center22` |

ایمیج به‌صورت ثابت روی `ghcr.io/blakeblackshear/frigate:0.17.2` پین شده است.

## اصول طراحی

- **منبع حقیقت واحد:** پوشه‌ی `inventory/`.
- **افزودن نمونه‌ی جدید** فقط نیازمند یک ورودی در `inventory/instances.yml` و یک
  فایل دوربین در `inventory/cameras/` است. هیچ تغییری در قالب‌ها یا اسکریپت‌ها لازم نیست.
- هر نمونه: پوشه‌ی config مستقل، پوشه‌ی media مستقل، `tmpfs` روی `/tmp/cache`،
  لاگ JSON با چرخش، و `topic_prefix` و `client_id` یکتا برای MQTT دارد.
- به‌صورت پیش‌فرض: **بدون تشخیص (detection)، بدون ضبط (recording)، بدون
  Birdseye**، و **بدون GPU/NVIDIA/Coral یا هر شتاب‌دهنده‌ی سخت‌افزاری**.
- **هیچ رمز، نام‌کاربری، IP یا فایل `.env` در گیت ذخیره نمی‌شود.**

## ساختار مخزن

<div dir="ltr">

```
inventory/
  instances.yml            # تنظیمات سراسری + فهرست نمونه‌ها
  cameras/
    cafe.yml               # دوربین‌ها و منابع (source) هر نمونه
    center11.yml
    center22.yml
templates/
  frigate-config.yml.j2    # قالب پیکربندی Frigate
  compose.instance.yml.j2  # قالب سرویس Compose برای هر نمونه
scripts/
  render.py                # رندر اینونتوری → generated/
  validate.sh              # رندر + اعتبارسنجی
  deploy.sh                # استقرار سمت سرور (بکاپ، رندر، health-check)
  backup-config.sh         # بکاپ config.yml و frigate.db
docs/                      # مستندات تفصیلی (انگلیسی)
.github/workflows/         # validate.yml و deploy.yml
.env.example               # فهرست متغیرها (بدون مقدار)
```

</div>

## مسیرهای زمان اجرا روی سرور اوبونتو

<div dir="ltr">

```
/home/rootuser/frigate_new/repo                     # همین مخزن گیت
/home/rootuser/frigate_new/secrets/.env             # رمزها (هرگز در گیت نیست)
/home/rootuser/frigate_new/media/<instance>         # مدیای هر نمونه (هرگز در گیت نیست)
/home/rootuser/frigate_new/runtime-config/<instance># config.yml + frigate.db هر نمونه
/home/rootuser/frigate_new/backups                  # بکاپ‌های زمان‌دار
```

</div>

---

## ۱) توسعه‌ی محلی (Local development)

بدون نیاز به سرور یا رمز واقعی:

<div dir="ltr">

```bash
pip install jinja2 pyyaml
bash scripts/validate.sh
```

</div>

خروجی رندرشده در `generated/` قرار می‌گیرد (این پوشه در گیت نادیده گرفته می‌شود).

## ۲) راه‌اندازی اولیه‌ی سرور (Server bootstrap)

<div dir="ltr">

```bash
sudo mkdir -p /home/rootuser/frigate_new/{secrets,media,runtime-config,backups}
sudo git clone https://github.com/ast2019/cctv_izadshahr.git /home/rootuser/frigate_new/repo
```

</div>

پیش‌نیازها: Docker Engine + پلاگین Docker Compose، و Python 3 به‌همراه
`jinja2` و `pyyaml`. کاربر اجراکننده باید عضو گروه `docker` باشد.

## ۳) ساخت اولیه‌ی رمزها (Initial secret creation)

<div dir="ltr">

```bash
sudo cp /home/rootuser/frigate_new/repo/.env.example /home/rootuser/frigate_new/secrets/.env
sudo chmod 600 /home/rootuser/frigate_new/secrets/.env
sudo nano /home/rootuser/frigate_new/secrets/.env
```

</div>

فهرست دقیق متغیرهای موردنیاز را این‌گونه بگیرید:

<div dir="ltr">

```bash
cd /home/rootuser/frigate_new/repo
python3 scripts/render.py
cat generated/required-env.txt
```

</div>

نام متغیرها از الگوی `FRIGATE_<INSTANCE>_<SOURCE>_{USER,PASSWORD,HOST}` پیروی
می‌کند. مقدار `HOST` همان IP یا نام دستگاه/DVR است و **فقط** در این فایل نگهداری
می‌شود.

## ۴) افزودن دوربین (Adding a camera)

فایل `inventory/cameras/<instance>.yml` را ویرایش کنید. اگر دستگاه (source) از
قبل تعریف شده، فقط دوربین را اضافه کنید:

<div dir="ltr">

```yaml
cameras:
  dvr_cafe_ch11:
    enabled: true
    source: dvr
    path: "/cam/realmonitor?channel=11&subtype=0"
```

</div>

اگر دستگاه جدید است، ابتدا یک `source` بسازید و سپس سه متغیر جدید را به
`.env.example` و به `.env` سرور اضافه کنید. جزئیات کامل در
[docs/add-camera.md](docs/add-camera.md).

## ۵) افزودن نمونه (Adding an instance)

۱. پورت‌های یکتا انتخاب کنید و به `inventory/instances.yml` اضافه کنید.
۲. فایل `inventory/cameras/<name>.yml` را بسازید.
۳. متغیرهای جدید را به `.env.example` و `.env` سرور اضافه کنید.
۴. اعتبارسنجی و push به `main`.

راهنمای گام‌به‌گام: [docs/add-instance.md](docs/add-instance.md).

## ۶) اعتبارسنجی (Validation)

<div dir="ltr">

```bash
bash scripts/validate.sh
```

</div>

این دستور اینونتوری را رندر کرده و اجرا می‌کند:
`docker compose -f generated/compose.generated.yaml config -q`.
همین کار به‌صورت خودکار در GitHub Actions (`.github/workflows/validate.yml`)
روی هر push و PR انجام می‌شود.

## ۷) استقرار (Deploying)

**خودکار:** هر push به شاخه‌ی `main` ابتدا اعتبارسنجی و سپس از طریق SSH استقرار
می‌شود. رازهای موردنیاز در GitHub: `SSH_HOST`، `SSH_USER`، `SSH_PORT` (اختیاری)،
`SSH_PRIVATE_KEY`، `SSH_KNOWN_HOSTS`.

**دستی روی سرور:**

<div dir="ltr">

```bash
cd /home/rootuser/frigate_new/repo
git pull origin main
bash scripts/deploy.sh
```

</div>

`deploy.sh` به‌ترتیب: رندر می‌کند، از تمام `config.yml` و `frigate.db`ها بکاپ
زمان‌دار می‌گیرد، Compose را اعتبارسنجی می‌کند، و نمونه‌ها را **یکی‌یکی** به‌روزرسانی
و پس از هر کدام health-check می‌کند. این اسکریپت **هرگز** `frigate.db` را حذف یا
بازنویسی نمی‌کند و فقط `config.yml` را تغییر می‌دهد.

## ۸) بازگردانی (Rollback)

- **بازگردانی وضعیت مطلوب** با گیت (`git revert` یا reset روی `main`).
- **بازگردانی config روی سرور** از پوشه‌ی `‏/home/rootuser/frigate_new/backups/<timestamp>/`.

جزئیات کامل: [docs/rollback.md](docs/rollback.md).

## ۹) بازیابی فاجعه (Disaster recovery)

برای بازسازی سرور از صفر فقط به «مخزن» و «فایل رازها» نیاز دارید؛ مدیا و پایگاه‌داده
داده‌های زمان اجرا هستند و در صورت نبود، توسط Frigate بازساخته می‌شوند:

<div dir="ltr">

```bash
sudo mkdir -p /home/rootuser/frigate_new/{secrets,media,runtime-config,backups}
sudo git clone https://github.com/ast2019/cctv_izadshahr.git /home/rootuser/frigate_new/repo
sudo cp /path/to/backup/.env /home/rootuser/frigate_new/secrets/.env
sudo chmod 600 /home/rootuser/frigate_new/secrets/.env
cd /home/rootuser/frigate_new/repo && bash scripts/deploy.sh
```

</div>

مراحل کامل و بازگردانی `config.yml`/`frigate.db` در
[docs/rollback.md](docs/rollback.md).

---

## معماری آینده (خارج از محدوده‌ی این تغییر)

موارد زیر عمداً در این مخزن پیاده‌سازی **نشده‌اند** و فقط به‌عنوان مسیر آینده ثبت
می‌شوند: داشبورد React، یکپارچه‌سازی Home Assistant، Authentik/Authelia،
reverse proxy و SSO. این‌ها باید به‌صورت لایه‌های جداگانه و بدون تغییر مدل
داده‌محور فعلی اضافه شوند.

## نکات امنیتی

- فایل `.env` واقعی هرگز commit نمی‌شود (توسط `.gitignore` مسدود است).
- رمز/نام‌کاربری/IP دوربین‌ها فقط از طریق جایگزینی متغیر Frigate با نحو
  `{FRIGATE_VARIABLE_NAME}` ارجاع داده می‌شوند.
- مدیا، رکوردینگ، اسنپ‌شات، کش و فایل‌های `frigate.db` هرگز در گیت قرار نمی‌گیرند.

</div>
