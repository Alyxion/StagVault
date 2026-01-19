# StagVault Providers

External API providers for images and videos (Pixabay, Pexels, etc.).

## Architecture

```
providers/
├── base.py          # Base classes and unified models
├── cache.py         # Intelligent caching (memory + disk)
├── pixabay.py       # Pixabay API adapter
├── pexels.py        # Pexels API adapter
├── registry.py      # Multi-provider registry and unified search
└── routes.py        # FastAPI router factory
```

## Access Modes

All providers support three access patterns:

| Mode | Use Case | API Keys |
|------|----------|----------|
| **Python Direct** | Server-side scripts, CLI | Environment variables |
| **FastAPI Routes** | Web applications | Server-side (secure) |
| **JavaScript Direct** | Local/trusted apps only | Client-side (insecure) |

## Rate Limits

**CRITICAL**: Minimize API calls. Some providers have very low limits.

| Provider | Limit | Window | Cache Duration |
|----------|-------|--------|----------------|
| Pixabay | 100 requests | 60 seconds | **24 hours (required)** |
| Pexels | 200 requests | 1 hour | 24 hours (recommended) |
| Unsplash | **50 requests** | 1 hour | 24 hours (critical!) |

> **Note**: Unsplash has very low limits in demo mode (50/hour). Production mode
> requires approval and provides 5,000 requests/hour.

### Rate Limit Strategy

1. **Aggressive Caching**: All responses cached for 24 hours minimum
2. **Request Coalescing**: Duplicate requests return cached results
3. **Dynamic Buffer**: Reserve scales with provider limit:
   - Low-limit (< 100): Keep 10% in reserve
   - Medium-limit (100-500): Keep 5% in reserve
   - High-limit (> 500): Keep 3% in reserve
4. **Proactive Waiting**: When `remaining <= buffer`, wait before requesting
5. **Header Tracking**: Rate limits updated from every response
6. **Critical Detection**: Alert when < 10% requests remaining

## Caching

### Cache Layers

1. **Memory Cache** (ProviderCache.memory)
   - LRU eviction, configurable max size
   - Fast access, lost on restart

2. **Disk Cache** (ProviderCache.disk)
   - SQLite-based, persistent across restarts
   - Survives application restarts

### Cache Keys

Format: `{provider}:{method}:{sorted_params_hash}`

Example: `pixabay:search_images:a1b2c3d4...`

### Clearing Cache

```python
# Python
from stagvault.providers import get_registry

registry = get_registry()

# Clear all caches
registry.clear_cache()

# Clear specific provider
registry.clear_cache("pixabay")

# Get cache statistics
stats = registry.cache_stats()
```

```bash
# Via API
curl -X POST /providers/cache/clear
curl -X POST /providers/cache/clear?provider_id=pixabay
```

```javascript
// JavaScript
const providers = new ProviderClient({ backendUrl: '/providers' });
providers.clearCache();           // Clear all
providers.clearCache('pixabay');  // Clear specific
```

## Adding New Providers

1. **Create provider file** (`stagvault/providers/newprovider.py`):

```python
from stagvault.providers.base import (
    APIProvider, ProviderConfig, ProviderAuthType,
    ProviderImage, ProviderResult, MediaType
)

NEWPROVIDER_CONFIG = ProviderConfig(
    id="newprovider",
    name="New Provider",
    base_url="https://api.newprovider.com/",
    auth_type=ProviderAuthType.HEADER,  # or QUERY_PARAM
    auth_param="Authorization",          # header/param name
    api_key_env="NEWPROVIDER_API_KEY",  # env var name
    rate_limit_window=3600,              # seconds
    rate_limit_requests=50,              # conservative!
    cache_duration=86400,                # 24 hours
    requires_attribution=True,
    supports_images=True,
    supports_videos=False,
    hotlink_allowed=False,
)

class NewProvider(APIProvider):
    def __init__(self, cache=None):
        super().__init__(NEWPROVIDER_CONFIG, cache)

    async def search_images(self, query, *, page=1, per_page=20, **kwargs):
        # Check cache first!
        cache_key = {"q": query, "page": page, "per_page": per_page}
        if self.cache:
            cached = self.cache.get("newprovider", "search_images", cache_key)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Make API request
        data = await self._request("search", {"query": query, ...})

        # Parse to unified format
        images = [self._parse_image(hit) for hit in data["results"]]

        result = ProviderResult(
            provider="newprovider",
            total=data["total"],
            page=page,
            per_page=per_page,
            images=images,
        )

        # Cache result
        if self.cache:
            self.cache.set("newprovider", "search_images", cache_key,
                          result.model_dump(), ttl=self.config.cache_duration)

        return result
```

2. **Register in registry.py**:

```python
from stagvault.providers.newprovider import NewProvider

PROVIDER_CLASSES["newprovider"] = NewProvider
```

3. **Add JS config** (`static/js/providers.js`):

```javascript
PROVIDER_CONFIGS.newprovider = {
    id: 'newprovider',
    name: 'New Provider',
    baseUrl: 'https://api.newprovider.com/',
    authType: 'header',
    authParam: 'Authorization',
    rateLimitWindow: 3600000,
    rateLimitRequests: 50,
    cacheDuration: 86400000,
    // ...
};
```

4. **Add environment variable**:

```bash
# .env
NEWPROVIDER_API_KEY=your_key_here
```

## Environment Variables

| Variable | Provider | Required |
|----------|----------|----------|
| `PIXABAY_API_KEY` | Pixabay | Yes |
| `PEXELS_API_KEY` | Pexels | Yes |
| `UNSPLASH_API_KEY` | Unsplash | Yes |

**NEVER commit API keys to source control!**

## Testing

```bash
# Run provider tests (uses mocked responses)
poetry run pytest tests/test_providers.py -v

# Test with real APIs (requires keys in .env)
source .env && poetry run pytest tests/test_providers.py -v -m integration
```
