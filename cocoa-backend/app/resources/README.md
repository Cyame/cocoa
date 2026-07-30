# Bundled models.dev snapshot

Offline fallback for \`ModelCatalog\` when https://models.dev/api.json is unreachable.
Refresh (with proxy if needed):

```bash
enable-proxy
curl -fsSL https://models.dev/api.json -o cocoa-backend/app/resources/models_dev_api.json
date -u +%Y-%m-%dT%H:%M:%SZ > cocoa-backend/app/resources/models_dev_api.fetched_at.txt
```
