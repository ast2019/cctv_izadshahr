/**
 * Portal login accounts (usernames only).
 *
 * SECURITY: passwords are intentionally NOT stored here. Each user types their
 * own password in the login form, which the portal forwards to Frigate for
 * validation. The `admin.user` value is used only to decide who may see the
 * admin panel. The actual credentials live in Frigate and are unchanged.
 *
 *   viewer → user "ceoizadshahr"   (read-only)
 *   admin  → user "admin" (full access)
 */
const PORTAL_AUTH = {
  viewer: { user: "ceoizadshahr", label: "مشاهده" },
  admin: { user: "admin", label: "مدیریت" },
};
