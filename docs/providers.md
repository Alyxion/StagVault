# External API Providers

StagVault integrates with external media APIs for stock photos and videos. Each provider has specific terms of service that must be followed.

## Provider Overview

| Provider | Rate Limit | Attribution | Hotlink | Tier |
|----------|------------|-------------|---------|------|
| [Pixabay](#pixabay) | 100/min | Not required | No | standard |
| [Pexels](#pexels) | 200/hour | Appreciated | Yes | standard |
| [Unsplash](#unsplash) | 50/hour (demo) | **Required** | Yes | restricted |

## Provider Details

### Pixabay

Free images and royalty-free stock photos.

- **Terms of Service**: https://pixabay.com/service/terms/
- **License Summary**: https://pixabay.com/service/license-summary/
- **API Documentation**: https://pixabay.com/api/docs/

**Key Restrictions:**
- Hotlinking not allowed (must download images)
- Cannot compile images into database for resale
- Cannot sell unmodified copies

**Rate Limits:**
- 100 requests per minute
- 24-hour caching recommended

---

### Pexels

Free stock photos and videos shared by talented creators.

- **Terms of Service**: https://www.pexels.com/terms-of-service/
- **License**: https://www.pexels.com/license/
- **API Guidelines**: https://www.pexels.com/api/documentation/#guidelines

**Key Restrictions:**
- Attribution appreciated but not required
- Cannot sell unmodified copies
- Cannot compile into competing service

**Rate Limits:**
- 200 requests per hour
- Hotlinking allowed with attribution

---

### Unsplash

Beautiful free images from photographers worldwide.

- **API Terms**: https://unsplash.com/api-terms
- **License**: https://unsplash.com/license
- **API Documentation**: https://unsplash.com/documentation

**Key Restrictions:**
- **Attribution required** (photographer + Unsplash link)
- **No ads alongside images**
- Must trigger download endpoint for tracking
- Cannot compile into competing service

**Rate Limits:**
- Demo: 50 requests/hour (very restrictive)
- Production: 5,000 requests/hour (requires approval)

**Why Restricted Tier:**
The demo rate limit (50/hour) is extremely low. This provider is marked as `restricted` and excluded from broad searches by default to preserve rate limits for intentional use.

## Configuration

API keys are stored in environment variables (`.env` file):

```bash
PIXABAY_API_KEY=your_key_here
PEXELS_API_KEY=your_key_here
UNSPLASH_API_KEY=your_key_here
```

Provider configurations are in `configs/sources/`:
- `configs/sources/pixabay.yaml`
- `configs/sources/pexels.yaml`
- `configs/sources/unsplash.yaml`

## Usage Notes

### Broad Search
By default, only `standard` tier providers are included in multi-provider searches. This prevents rate limit exhaustion on restricted providers.

### Explicit Selection
To search restricted providers, explicitly specify them:

```python
# Python
results = await registry.search_images("sunset", providers=["unsplash"])

# API
GET /providers/unsplash/search/images?q=sunset
```

### Caching
All providers use a dual-layer cache (memory LRU + SQLite disk) with 24-hour TTL. This reduces API calls and improves response times.
