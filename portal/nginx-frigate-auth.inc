# Shared by every Frigate UI location. Included from nginx.conf / ssl template.
auth_request /internal/session;
error_page 401 403 = @portal_login;
