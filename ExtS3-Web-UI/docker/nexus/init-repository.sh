#!/bin/sh
set -eu

repo_name="${NEXUS_REPOSITORY:-extension-demo}"
base_url="${NEXUS_BASE_URL:-http://nexus:8081}"
auth="${NEXUS_USERNAME:-example_nexus_user}:${NEXUS_PASSWORD:-example_nexus_password}"

echo "Waiting for Nexus at ${base_url}"
for i in $(seq 1 60); do
  if curl -fsS -u "$auth" "${base_url}/service/rest/v1/status" >/dev/null; then
    break
  fi
  sleep 5
done

if curl -fsS -u "$auth" "${base_url}/service/rest/v1/repositories/${repo_name}" >/dev/null; then
  echo "Nexus repository already exists: ${repo_name}"
  exit 0
fi

payload=$(cat <<JSON
{
  "name": "${repo_name}",
  "online": true,
  "storage": {
    "blobStoreName": "default",
    "strictContentTypeValidation": false,
    "writePolicy": "allow"
  },
  "cleanup": {
    "policyNames": []
  },
  "component": {
    "proprietaryComponents": false
  },
  "raw": {
    "contentDisposition": "ATTACHMENT"
  }
}
JSON
)

status=$(curl -sS -o /tmp/nexus-create-response.txt -w "%{http_code}" \
  -u "$auth" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "$payload" \
  "${base_url}/service/rest/v1/repositories/raw/hosted")

if [ "$status" = "201" ] || [ "$status" = "204" ]; then
  echo "Created Nexus raw hosted repository: ${repo_name}"
  exit 0
fi

cat /tmp/nexus-create-response.txt
echo "Failed to create Nexus repository ${repo_name}; HTTP ${status}" >&2
exit 1
