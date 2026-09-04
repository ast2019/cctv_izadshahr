# Shared portal locations (HTTP + SSL). Root/index stay in the server block.

# auth_request subrequest — Cookie is forwarded, body is not.
location = /internal/session {
    internal;
    proxy_pass http://portal-metrics:9090/api/session;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Host $http_host;
}

location @portal_login {
    # Path only ($uri) so a nested query string cannot break ?next=
    return 302 /?next=$uri;
}

# Health — unauthenticated, internal Frigate port 5000 (any response = up)
location = /health/cafe/ {
    proxy_pass http://frigate-cafe:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/center11/ {
    proxy_pass http://frigate-center11:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/center22/ {
    proxy_pass http://frigate-center22:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/restaurant/ {
    proxy_pass http://frigate-restaurant:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/sahel/ {
    proxy_pass http://frigate-sahel:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/villa/ {
    proxy_pass http://frigate-villa:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/mahoote/ {
    proxy_pass http://frigate-mahoote:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/tasisat/ {
    proxy_pass http://frigate-tasisat:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/entezamat/ {
    proxy_pass http://frigate-entezamat:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/anbar/ {
    proxy_pass http://frigate-anbar:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/khanedari/ {
    proxy_pass http://frigate-khanedari:5000/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location = /health/temp/ {
    set $temp_upstream frigate-temp:5000;
    proxy_pass http://$temp_upstream/api/version;
    proxy_intercept_errors on;
    error_page 401 403 = @health_ok;
}
location @health_ok {
    return 204;
}

location /api/ {
    proxy_pass http://portal-metrics:9090/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /cafe/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-cafe:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /cafe;
    proxy_redirect / /cafe/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /center11/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-center11:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /center11;
    proxy_redirect / /center11/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /center22/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-center22:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /center22;
    proxy_redirect / /center22/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /restaurant/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-restaurant:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /restaurant;
    proxy_redirect / /restaurant/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /sahel/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-sahel:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /sahel;
    proxy_redirect / /sahel/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /villa/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-villa:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /villa;
    proxy_redirect / /villa/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /mahoote/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-mahoote:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /mahoote;
    proxy_redirect / /mahoote/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /tasisat/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-tasisat:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /tasisat;
    proxy_redirect / /tasisat/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /entezamat/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-entezamat:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /entezamat;
    proxy_redirect / /entezamat/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /anbar/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-anbar:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /anbar;
    proxy_redirect / /anbar/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /khanedari/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    proxy_pass http://frigate-khanedari:5000/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /khanedari;
    proxy_redirect / /khanedari/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /temp/ {
    include /usr/share/nginx/html/nginx-frigate-auth.inc;
    set $temp_upstream frigate-temp:5000;
    rewrite ^/temp/(.*)$ /$1 break;
    proxy_pass http://$temp_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Ingress-Path /temp;
    proxy_redirect / /temp/;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
