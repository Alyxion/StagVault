/**
 * StagVault JavaScript Client
 *
 * Works with the static JSON index exported by `stagvault export`.
 * Provides client-side search for media items with style variant grouping.
 *
 * Usage:
 *   const vault = new StagVault('/static/index.json');
 *   await vault.load();
 *
 *   // Grouped search (default)
 *   const groups = vault.searchGrouped('arrow', { limit: 20 });
 *
 *   // Individual item search
 *   const items = vault.search('arrow', { styles: ['regular'] });
 */

export class StagVault {
    /**
     * @param {string} indexUrl - URL to the exported index.json
     * @param {Object} options - Configuration options
     * @param {string[]} options.preferredStyles - Default style preferences
     */
    constructor(indexUrl, options = {}) {
        this.indexUrl = indexUrl;
        this.preferredStyles = options.preferredStyles || ['regular', 'outline'];
        this.data = null;
        this.isGrouped = null;
        this._searchIndex = null;
    }

    /**
     * Load the index from the server
     * @returns {Promise<void>}
     */
    async load() {
        const response = await fetch(this.indexUrl);
        if (!response.ok) {
            throw new Error(`Failed to load index: ${response.status}`);
        }
        this.data = await response.json();
        this.isGrouped = 'groups' in this.data;
        this._buildSearchIndex();
    }

    /**
     * Build internal search index for fast lookups
     * @private
     */
    _buildSearchIndex() {
        this._searchIndex = new Map();

        if (this.isGrouped) {
            for (const group of this.data.groups) {
                const terms = this._extractTerms(group);
                for (const term of terms) {
                    if (!this._searchIndex.has(term)) {
                        this._searchIndex.set(term, []);
                    }
                    this._searchIndex.get(term).push({ type: 'group', data: group });
                }
            }
        } else {
            for (const item of this.data.items) {
                const terms = this._extractTerms(item);
                for (const term of terms) {
                    if (!this._searchIndex.has(term)) {
                        this._searchIndex.set(term, []);
                    }
                    this._searchIndex.get(term).push({ type: 'item', data: item });
                }
            }
        }
    }

    /**
     * Extract searchable terms from an item or group
     * @private
     */
    _extractTerms(obj) {
        const terms = new Set();
        const name = obj.canonical_name || obj.name || '';

        // Add full name and parts
        terms.add(name.toLowerCase());
        for (const part of name.toLowerCase().split(/[-_]/)) {
            if (part.length > 1) terms.add(part);
        }

        // Add tags
        if (obj.tags) {
            for (const tag of obj.tags) {
                terms.add(tag.toLowerCase());
            }
        }

        // Add source
        if (obj.source_id) {
            terms.add(obj.source_id.toLowerCase());
        }

        return terms;
    }

    /**
     * Search for grouped results (icons with all their style variants)
     * @param {string} query - Search query
     * @param {Object} options - Search options
     * @param {string} options.sourceId - Filter by source
     * @param {string[]} options.tags - Filter by tags
     * @param {string[]} options.preferredStyles - Style preferences for default selection
     * @param {number} options.limit - Max results (default 50)
     * @returns {Array} Array of group objects
     */
    searchGrouped(query, options = {}) {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        const {
            sourceId = null,
            tags = null,
            preferredStyles = this.preferredStyles,
            limit = 50,
        } = options;

        const queryTerms = query.toLowerCase().split(/\s+/).filter(t => t.length > 0);
        const results = new Map();

        // Search through index
        for (const term of queryTerms) {
            for (const [indexTerm, entries] of this._searchIndex) {
                if (indexTerm.includes(term) || term.includes(indexTerm)) {
                    for (const entry of entries) {
                        const data = entry.type === 'group' ? entry.data : this._itemToGroup(entry.data);
                        const key = `${data.source_id}:${data.canonical_name}`;

                        if (!results.has(key)) {
                            results.set(key, { group: data, score: 0 });
                        }

                        // Score based on match quality
                        const exactMatch = indexTerm === term;
                        results.get(key).score += exactMatch ? 10 : 5;
                    }
                }
            }
        }

        // Filter and sort
        let filtered = Array.from(results.values());

        if (sourceId) {
            filtered = filtered.filter(r => r.group.source_id === sourceId);
        }

        if (tags && tags.length > 0) {
            filtered = filtered.filter(r =>
                tags.some(tag => r.group.tags?.includes(tag))
            );
        }

        filtered.sort((a, b) => b.score - a.score);

        // Add default style selection
        return filtered.slice(0, limit).map(r => ({
            ...r.group,
            defaultStyle: this._selectDefaultStyle(r.group.variants || r.group.styles, preferredStyles),
        }));
    }

    /**
     * Search for individual items (not grouped)
     * @param {string} query - Search query
     * @param {Object} options - Search options
     * @param {string} options.sourceId - Filter by source
     * @param {string[]} options.styles - Filter by styles
     * @param {string[]} options.tags - Filter by tags
     * @param {number} options.limit - Max results (default 50)
     * @returns {Array} Array of item objects
     */
    search(query, options = {}) {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        const {
            sourceId = null,
            styles = null,
            tags = null,
            limit = 50,
        } = options;

        // If data is grouped, flatten it first
        const items = this.isGrouped ? this._flattenGroups() : this.data.items;

        const queryTerms = query.toLowerCase().split(/\s+/).filter(t => t.length > 0);
        const results = [];

        for (const item of items) {
            const searchText = [
                item.name || item.canonical_name,
                ...(item.tags || []),
                item.source_id,
            ].join(' ').toLowerCase();

            const matches = queryTerms.every(term => searchText.includes(term));
            if (!matches) continue;

            // Apply filters
            if (sourceId && item.source_id !== sourceId) continue;
            if (styles && styles.length > 0 && !styles.includes(item.style)) continue;
            if (tags && tags.length > 0 && !tags.some(t => item.tags?.includes(t))) continue;

            results.push(item);
        }

        return results.slice(0, limit);
    }

    /**
     * Get all variants for a specific icon
     * @param {string} sourceId - Source identifier
     * @param {string} canonicalName - Base name of the icon
     * @returns {Object|null} Group object with all variants
     */
    getVariants(sourceId, canonicalName) {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        if (this.isGrouped) {
            return this.data.groups.find(
                g => g.source_id === sourceId && g.canonical_name === canonicalName
            ) || null;
        } else {
            const items = this.data.items.filter(
                i => i.source_id === sourceId && i.canonical_name === canonicalName
            );
            if (items.length === 0) return null;
            return this._itemsToGroup(items);
        }
    }

    /**
     * Get a specific item by ID
     * @param {string} itemId - Item ID
     * @returns {Object|null}
     */
    getItem(itemId) {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        if (this.isGrouped) {
            for (const group of this.data.groups) {
                const variant = group.variants?.find(v => v.id === itemId);
                if (variant) {
                    return {
                        ...variant,
                        source_id: group.source_id,
                        canonical_name: group.canonical_name,
                        tags: group.tags,
                        description: group.description,
                    };
                }
            }
            return null;
        } else {
            return this.data.items.find(i => i.id === itemId) || null;
        }
    }

    /**
     * List all sources in the index
     * @returns {string[]}
     */
    listSources() {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        const sources = new Set();
        const items = this.isGrouped ? this.data.groups : this.data.items;
        for (const item of items) {
            sources.add(item.source_id);
        }
        return Array.from(sources).sort();
    }

    /**
     * List all available styles
     * @param {string} sourceId - Optional source filter
     * @returns {string[]}
     */
    listStyles(sourceId = null) {
        if (!this.data) {
            throw new Error('Index not loaded. Call load() first.');
        }

        const styles = new Set();

        if (this.isGrouped) {
            for (const group of this.data.groups) {
                if (sourceId && group.source_id !== sourceId) continue;
                for (const style of (group.styles || [])) {
                    styles.add(style);
                }
            }
        } else {
            for (const item of this.data.items) {
                if (sourceId && item.source_id !== sourceId) continue;
                if (item.style) styles.add(item.style);
            }
        }

        return Array.from(styles).sort();
    }

    /**
     * Get total count of items or groups
     * @returns {number}
     */
    get count() {
        return this.data?.count || 0;
    }

    // Private helpers

    _flattenGroups() {
        const items = [];
        for (const group of this.data.groups) {
            for (const variant of (group.variants || [])) {
                items.push({
                    id: variant.id,
                    source_id: group.source_id,
                    name: group.canonical_name,
                    canonical_name: group.canonical_name,
                    path: variant.path,
                    format: variant.format,
                    style: variant.style,
                    tags: group.tags,
                    description: group.description,
                });
            }
        }
        return items;
    }

    _itemToGroup(item) {
        return {
            canonical_name: item.canonical_name || item.name,
            source_id: item.source_id,
            tags: item.tags || [],
            description: item.description,
            variants: [{
                id: item.id,
                style: item.style,
                path: item.path,
                format: item.format,
            }],
            styles: item.style ? [item.style] : [],
        };
    }

    _itemsToGroup(items) {
        if (items.length === 0) return null;
        const first = items[0];
        return {
            canonical_name: first.canonical_name || first.name,
            source_id: first.source_id,
            tags: first.tags || [],
            description: first.description,
            variants: items.map(i => ({
                id: i.id,
                style: i.style,
                path: i.path,
                format: i.format,
            })),
            styles: [...new Set(items.map(i => i.style).filter(Boolean))],
        };
    }

    _selectDefaultStyle(variants, preferredStyles) {
        if (!variants || variants.length === 0) return null;

        // If variants is array of strings (styles)
        if (typeof variants[0] === 'string') {
            for (const pref of preferredStyles) {
                if (variants.includes(pref)) return pref;
            }
            return variants[0];
        }

        // If variants is array of objects
        for (const pref of preferredStyles) {
            const match = variants.find(v => v.style === pref);
            if (match) return match.style;
        }
        return variants[0]?.style || null;
    }
}

// Also export as default for CommonJS compatibility
export default StagVault;
