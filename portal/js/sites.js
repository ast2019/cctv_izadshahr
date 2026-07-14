/** Site definitions — keep in sync with docs/CAMERAS.md */
const SITES = [
  {
    id: "cafe",
    slug: "cafe",
    title: "کافه",
    titleEn: "Cafe",
    description: "دوربین‌های بخش کافه و محوطه",
    icon: "☕",
    port: 8972,
    cameraCount: 8,
    enabled: true,
    healthPath: "/health/cafe/",
    apiPath: "/cafe/api/",
    cssClass: "card--active",
  },
  {
    id: "center11",
    slug: "center11",
    title: "پذیرش و مدیریت هتل و رستوران",
    titleEn: "Reception & Hotel / Restaurant",
    description: "دوربین‌های IP بخش پذیرش، هتل و رستوران",
    icon: "🏨",
    port: 8973,
    cameraCount: 6,
    enabled: true,
    healthPath: "/health/center11/",
    apiPath: "/center11/api/",
    cssClass: "card--active",
  },
  {
    id: "center22",
    slug: "center22",
    title: "پارکینگ ۴ و سایر بخش‌ها",
    titleEn: "Parking 4 & More",
    description: "DVR پارکینگ ۴ و دسته‌های بعدی — به‌زودی",
    icon: "🅿️",
    port: 8974,
    cameraCount: 0,
    enabled: false,
    healthPath: "/health/center22/",
    apiPath: "/center22/api/",
    cssClass: "card--center22",
  },
];

/**
 * Inventory overview (docs/CAMERAS.md).
 * total = همه دوربین‌های شناخته‌شده
 * inactive = هنوز فعال نشده / planned
 * broken = قبلاً فعال بوده یا باید فعال باشد ولی الان قطع است (مثل cam_14, cam_16)
 */
const CAMERA_INVENTORY = {
  total: 71,
  inactive: 55,
  broken: 2,
};
