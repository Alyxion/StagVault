/**
 * StagVault Provider Client
 *
 * Provides unified access to external image/video APIs (Pixabay, Pexels, etc.)
 * with intelligent caching and rate limit handling.
 *
 * Three access modes:
 * 1. Direct API calls (requires API key, CORS must be enabled)
 * 2. Via FastAPI backend (proxied, API keys stored server-side)
 * 3. Combined with local StagVault data
 *
 * Usage:
 *   // Via FastAPI backend (recommended)
 *   const providers = new ProviderClient({ backendUrl: '/providers' });
 *
 *   // Direct API access (requires API keys)
 *   const providers = new ProviderClient({
 *       mode: 'direct',
 *       apiKeys: { pixabay: 'YOUR_KEY', pexels: 'YOUR_KEY' }
 *   });
 */

// Cache implementation using localStorage with LRU eviction
class ProviderCache {
    constructor(options = {}) {
        this.prefix = options.prefix || 'svault_provider_';
        this.maxSize = options.maxSize || 500;
        this.defaultTTL = options.defaultTTL || 86400000; // 24 hours in ms
        this.storage = options.storage || (typeof localStorage !== 'undefined' ? localStorage : null);
    }

    _key(key) {
        return `${this.prefix}${key}`;
    }

    _getIndex() {
        if (!this.storage) return { keys: [], timestamps: {} };
        try {
            const data = this.storage.getItem(`${this.prefix}_index`);
            return data ? JSON.parse(data) : { keys: [], timestamps: {} };
        } catch {
            return { keys: [], timestamps: {} };
        }
    }

    _setIndex(index) {
        if (!this.storage) return;
        try {
            this.storage.setItem(`${this.prefix}_index`, JSON.stringify(index));
        } catch (e) {
            // Storage full, clear old entries
            this._evict(Math.floor(this.maxSize / 2));
        }
    }

    _evict(count) {
        const index = this._getIndex();
        // Sort by timestamp (oldest first)
        const sorted = index.keys.sort((a, b) =>
            (index.timestamps[a] || 0) - (index.timestamps[b] || 0)
        );

        for (let i = 0; i < count && i < sorted.length; i++) {
            const key = sorted[i];
            this.storage?.removeItem(this._key(key));
            const idx = index.keys.indexOf(key);
            if (idx > -1) index.keys.splice(idx, 1);
            delete index.timestamps[key];
        }
        this._setIndex(index);
    }

    get(key) {
        if (!this.storage) return null;

        const stored = this.storage.getItem(this._key(key));
        if (!stored) return null;

        try {
            const { value, expires } = JSON.parse(stored);
            if (Date.now() > expires) {
                this.delete(key);
                return null;
            }

            // Update access time
            const index = this._getIndex();
            index.timestamps[key] = Date.now();
            this._setIndex(index);

            return value;
        } catch {
            return null;
        }
    }

    set(key, value, ttl = this.defaultTTL) {
        if (!this.storage) return;

        const index = this._getIndex();

        // Evict if at capacity
        if (index.keys.length >= this.maxSize && !index.keys.includes(key)) {
            this._evict(Math.floor(this.maxSize / 4));
        }

        const data = {
            value,
            expires: Date.now() + ttl,
            created: Date.now()
        };

        try {
            this.storage.setItem(this._key(key), JSON.stringify(data));

            if (!index.keys.includes(key)) {
                index.keys.push(key);
            }
            index.timestamps[key] = Date.now();
            this._setIndex(index);
        } catch (e) {
            // Storage full
            this._evict(Math.floor(this.maxSize / 2));
            try {
                this.storage.setItem(this._key(key), JSON.stringify(data));
            } catch {
                // Give up
            }
        }
    }

    delete(key) {
        if (!this.storage) return;

        this.storage.removeItem(this._key(key));
        const index = this._getIndex();
        const idx = index.keys.indexOf(key);
        if (idx > -1) {
            index.keys.splice(idx, 1);
            delete index.timestamps[key];
            this._setIndex(index);
        }
    }

    clear(providerPrefix = null) {
        if (!this.storage) return;

        const index = this._getIndex();
        const keysToDelete = providerPrefix
            ? index.keys.filter(k => k.startsWith(providerPrefix))
            : [...index.keys];

        for (const key of keysToDelete) {
            this.storage.removeItem(this._key(key));
            const idx = index.keys.indexOf(key);
            if (idx > -1) {
                index.keys.splice(idx, 1);
                delete index.timestamps[key];
            }
        }
        this._setIndex(index);
    }

    stats() {
        const index = this._getIndex();
        return {
            count: index.keys.length,
            maxSize: this.maxSize,
            keys: index.keys
        };
    }
}


// Rate limit tracker
class RateLimitTracker {
    constructor() {
        this.limits = {};
    }

    update(provider, info) {
        this.limits[provider] = {
            ...info,
            updatedAt: Date.now()
        };
    }

    get(provider) {
        return this.limits[provider] || null;
    }

    shouldWait(provider) {
        const info = this.limits[provider];
        if (!info) return false;
        return info.remaining <= 1;
    }

    waitTime(provider) {
        const info = this.limits[provider];
        if (!info || !this.shouldWait(provider)) return 0;

        const elapsed = (Date.now() - info.updatedAt) / 1000;
        return Math.max(0, info.reset_seconds - elapsed) * 1000;
    }
}


// Provider configurations (no API keys!)
const PROVIDER_CONFIGS = {
    pixabay: {
        id: 'pixabay',
        name: 'Pixabay',
        baseUrl: 'https://pixabay.com/api/',
        authType: 'query_param',
        authParam: 'key',
        requiresAttribution: false,
        supportsImages: true,
        supportsVideos: true,
        hotlinkAllowed: false,
        cacheDuration: 86400000, // 24 hours (required by Pixabay)
        rateLimitWindow: 60000,
        rateLimitRequests: 100
    },
    pexels: {
        id: 'pexels',
        name: 'Pexels',
        baseUrl: 'https://api.pexels.com/',
        authType: 'header',
        authParam: 'Authorization',
        requiresAttribution: true,
        attributionTemplate: 'Photo by {author} on Pexels',
        supportsImages: true,
        supportsVideos: true,
        hotlinkAllowed: true,
        cacheDuration: 86400000,
        rateLimitWindow: 3600000, // 1 hour
        rateLimitRequests: 200
    }
};


/**
 * Main provider client class
 */
export class ProviderClient {
    /**
     * @param {Object} options
     * @param {string} options.mode - 'backend' (default) or 'direct'
     * @param {string} options.backendUrl - Backend API URL (for mode='backend')
     * @param {Object} options.apiKeys - API keys by provider (for mode='direct')
     * @param {Object} options.cacheOptions - Cache configuration
     */
    constructor(options = {}) {
        this.mode = options.mode || 'backend';
        this.backendUrl = options.backendUrl || '/providers';
        this.apiKeys = options.apiKeys || {};

        this.cache = new ProviderCache(options.cacheOptions);
        this.rateLimits = new RateLimitTracker();
        this.configs = { ...PROVIDER_CONFIGS };
    }

    /**
     * Generate cache key for a request
     */
    _cacheKey(provider, method, params) {
        const paramStr = Object.entries(params)
            .filter(([_, v]) => v != null)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([k, v]) => `${k}=${v}`)
            .join('&');
        return `${provider}:${method}:${paramStr}`;
    }

    /**
     * Make a request via backend
     */
    async _backendRequest(endpoint, params = {}) {
        const url = new URL(`${this.backendUrl}${endpoint}`, window.location.origin);
        Object.entries(params).forEach(([k, v]) => {
            if (v != null) url.searchParams.append(k, v);
        });

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }
        return response.json();
    }

    /**
     * Make a direct API request
     */
    async _directRequest(provider, endpoint, params = {}) {
        const config = this.configs[provider];
        if (!config) throw new Error(`Unknown provider: ${provider}`);

        const apiKey = this.apiKeys[provider];
        if (!apiKey) throw new Error(`No API key for ${provider}`);

        // Check rate limit
        if (this.rateLimits.shouldWait(provider)) {
            const wait = this.rateLimits.waitTime(provider);
            if (wait > 0) {
                await new Promise(resolve => setTimeout(resolve, wait));
            }
        }

        const url = new URL(endpoint, config.baseUrl);

        // Add auth
        const headers = {};
        if (config.authType === 'query_param') {
            url.searchParams.append(config.authParam, apiKey);
        } else if (config.authType === 'header') {
            headers[config.authParam] = apiKey;
        }

        // Add params
        Object.entries(params).forEach(([k, v]) => {
            if (v != null) url.searchParams.append(k, String(v));
        });

        const response = await fetch(url, { headers });

        // Update rate limit from headers
        this.rateLimits.update(provider, {
            limit: parseInt(response.headers.get('X-RateLimit-Limit') || '100'),
            remaining: parseInt(response.headers.get('X-RateLimit-Remaining') || '100'),
            reset_seconds: parseInt(response.headers.get('X-RateLimit-Reset') || '60')
        });

        if (response.status === 429) {
            throw new Error('Rate limit exceeded');
        }

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        return response.json();
    }

    /**
     * Search for images
     * @param {string} query - Search term
     * @param {Object} options
     * @param {string[]} options.providers - Provider IDs (default: all)
     * @param {number} options.page - Page number
     * @param {number} options.perPage - Results per page
     * @param {string} options.mediaType - photo, illustration, vector, all
     * @param {boolean} options.useCache - Use cached results (default: true)
     */
    async searchImages(query, options = {}) {
        const {
            providers = Object.keys(this.configs),
            page = 1,
            perPage = 20,
            mediaType = 'all',
            useCache = true,
            ...extra
        } = options;

        // Check cache
        const cacheKey = this._cacheKey('multi', 'searchImages', {
            q: query, providers: providers.join(','), page, perPage, mediaType
        });

        if (useCache) {
            const cached = this.cache.get(cacheKey);
            if (cached) {
                return { ...cached, cached: true };
            }
        }

        let result;

        if (this.mode === 'backend') {
            result = await this._backendRequest('/search/images', {
                q: query,
                providers: providers.join(','),
                page,
                per_page: perPage,
                media_type: mediaType,
                ...extra
            });
        } else {
            // Direct mode: query each provider
            const results = await Promise.allSettled(
                providers.map(p => this._searchProviderImages(p, query, { page, perPage, mediaType, ...extra }))
            );

            result = {
                query,
                providers,
                results: {},
                total_images: 0
            };

            providers.forEach((p, i) => {
                if (results[i].status === 'fulfilled') {
                    result.results[p] = results[i].value;
                    result.total_images += results[i].value.total || 0;
                } else {
                    result.results[p] = { error: results[i].reason.message, images: [] };
                }
            });
        }

        // Cache result
        if (useCache) {
            this.cache.set(cacheKey, result);
        }

        return result;
    }

    /**
     * Search images on a specific provider (direct mode)
     */
    async _searchProviderImages(provider, query, options = {}) {
        const { page = 1, perPage = 20, mediaType = 'all' } = options;
        const config = this.configs[provider];

        // Check provider-specific cache
        const cacheKey = this._cacheKey(provider, 'searchImages', { q: query, page, perPage });
        const cached = this.cache.get(cacheKey);
        if (cached) return { ...cached, cached: true };

        let data;
        if (provider === 'pixabay') {
            data = await this._directRequest(provider, '', {
                q: query,
                page,
                per_page: perPage,
                image_type: mediaType === 'all' ? 'all' : mediaType,
                safesearch: true
            });

            return {
                provider: 'pixabay',
                total: data.totalHits || 0,
                page,
                per_page: perPage,
                images: (data.hits || []).map(this._parsePixabayImage),
                cached: false
            };
        } else if (provider === 'pexels') {
            data = await this._directRequest(provider, 'v1/search', {
                query,
                page,
                per_page: perPage
            });

            return {
                provider: 'pexels',
                total: data.total_results || 0,
                page,
                per_page: perPage,
                images: (data.photos || []).map(this._parsePexelsImage),
                cached: false
            };
        }

        throw new Error(`Unknown provider: ${provider}`);
    }

    /**
     * Search for videos
     */
    async searchVideos(query, options = {}) {
        const {
            providers = Object.keys(this.configs).filter(p => this.configs[p].supportsVideos),
            page = 1,
            perPage = 20,
            useCache = true
        } = options;

        const cacheKey = this._cacheKey('multi', 'searchVideos', {
            q: query, providers: providers.join(','), page, perPage
        });

        if (useCache) {
            const cached = this.cache.get(cacheKey);
            if (cached) return { ...cached, cached: true };
        }

        let result;

        if (this.mode === 'backend') {
            result = await this._backendRequest('/search/videos', {
                q: query,
                providers: providers.join(','),
                page,
                per_page: perPage
            });
        } else {
            // Direct mode implementation similar to searchImages
            result = { query, providers, results: {}, total_videos: 0 };
        }

        if (useCache) {
            this.cache.set(cacheKey, result);
        }

        return result;
    }

    /**
     * Get a specific image
     */
    async getImage(provider, imageId) {
        const cacheKey = this._cacheKey(provider, 'getImage', { id: imageId });
        const cached = this.cache.get(cacheKey);
        if (cached) return cached;

        let result;
        if (this.mode === 'backend') {
            result = await this._backendRequest(`/${provider}/images/${imageId}`);
        } else {
            // Direct API call
            if (provider === 'pixabay') {
                const data = await this._directRequest(provider, '', { id: imageId });
                result = data.hits?.[0] ? this._parsePixabayImage(data.hits[0]) : null;
            } else if (provider === 'pexels') {
                const data = await this._directRequest(provider, `v1/photos/${imageId}`);
                result = this._parsePexelsImage(data);
            }
        }

        if (result) {
            this.cache.set(cacheKey, result);
        }
        return result;
    }

    /**
     * Get provider configurations (no API keys)
     */
    getProviderConfigs() {
        return Object.values(this.configs);
    }

    /**
     * Get rate limit status for a provider
     */
    getRateLimit(provider) {
        return this.rateLimits.get(provider);
    }

    /**
     * Get cache statistics
     */
    getCacheStats() {
        return this.cache.stats();
    }

    /**
     * Clear cache
     */
    clearCache(provider = null) {
        this.cache.clear(provider);
    }

    // Response parsers
    _parsePixabayImage(hit) {
        return {
            id: String(hit.id),
            provider: 'pixabay',
            source_url: hit.pageURL,
            preview_url: hit.previewURL,
            web_url: hit.webformatURL,
            full_url: hit.largeImageURL,
            width: hit.imageWidth,
            height: hit.imageHeight,
            tags: hit.tags?.split(',').map(t => t.trim()) || [],
            author: hit.user,
            author_url: `https://pixabay.com/users/${hit.user}-${hit.user_id}/`,
            license: 'Pixabay License',
            downloads: hit.downloads,
            likes: hit.likes
        };
    }

    _parsePexelsImage(photo) {
        return {
            id: String(photo.id),
            provider: 'pexels',
            source_url: photo.url,
            preview_url: photo.src?.tiny || photo.src?.small,
            web_url: photo.src?.medium || photo.src?.large,
            full_url: photo.src?.original,
            width: photo.width,
            height: photo.height,
            tags: [],
            description: photo.alt,
            author: photo.photographer,
            author_url: photo.photographer_url,
            license: 'Pexels License',
            avg_color: photo.avg_color
        };
    }
}


// Export for both ES modules and global use
export { ProviderCache, RateLimitTracker, PROVIDER_CONFIGS };
export default ProviderClient;
