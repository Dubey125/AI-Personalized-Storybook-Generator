#!/bin/sh
set -eu

BACKEND_ORIGIN="${REACT_APP_API_BASE_URL:-}"
BACKEND_ORIGIN="${BACKEND_ORIGIN%/}"

if [ -z "$BACKEND_ORIGIN" ]; then
  echo "REACT_APP_API_BASE_URL is required in container runtime env to configure nginx proxy." >&2
  exit 1
fi

cat > /usr/share/nginx/html/env-config.js <<EOF
window.__APP_CONFIG__ = {
  API_BASE_URL: "",
  API_AUTH_TOKEN: "${REACT_APP_API_AUTH_TOKEN:-}"
};
EOF

cat > /etc/nginx/conf.d/default.conf <<EOF
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location /api {
    proxy_pass ${BACKEND_ORIGIN};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }

  location /outputs {
    proxy_pass ${BACKEND_ORIGIN};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }

  location / {
    try_files \$uri /index.html;
  }
}
EOF

exec nginx -g "daemon off;"
