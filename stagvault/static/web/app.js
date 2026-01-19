/**
 * StagVault Static Search Application
 *
 * Implements efficient client-side search using 2-character prefix index files.
 * Features sidebar filters with exclusion mode (all checked = show all, uncheck to exclude).
 */

class StagVault {
    constructor() {
        this.indexBase = './index';
        this.sources = [];
        this.licenses = [];
        this.tags = [];
        this.prefixCache = new Map();
        this.prefixManifest = [];
        this.currentResults = [];
        this.allLoadedItems = [];
        this.searchDebounceTimer = null;

        // Filter state - these track EXCLUDED items (unchecked = excluded)
        this.excludedSources = new Set();
        this.excludedLicenses = new Set();
        this.excludedCategories = new Set();

        // Expanded tree nodes
        this.expandedNodes = new Set(['Vector', 'Icons', 'Emoji']);

        // Modal state
        this.currentItem = null;
        this.zoomLevel = 3;
        this.colorizeEnabled = false;
        this.primaryColor = '#e94560';
        this.secondaryColor = '#ffffff';
        this.colorMode = 'monochrome';

        // Canvas for color manipulation
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });

        // Sources that should not have colorization option
        this.nonColorableSources = new Set(['noto-emoji']);

        // Source color modes
        this.sourceColorModes = {
            'phosphor-icons': 'monochrome',
            'heroicons': 'monochrome',
            'feather': 'monochrome',
            'lucide': 'monochrome',
            'tabler-icons': 'monochrome',
        };

        // Top categories to show in sidebar
        this.topCategories = [
            'icon', 'ui', 'emoji', 'arrow', 'user', 'file', 'media',
            'communication', 'weather', 'animal', 'food', 'travel',
            'flags', 'symbols', 'objects', 'activities'
        ];

        // Source hierarchy tree
        this.sourceTree = {
            'Vector': {
                'Icons': ['feather', 'heroicons', 'lucide', 'tabler-icons', 'phosphor-icons',
                         'bootstrap-icons', 'ionicons', 'octicons', 'boxicons', 'eva-icons',
                         'iconoir', 'remix-icon', 'simple-icons', 'material-design'],
                'Emoji': ['noto-emoji', 'twemoji', 'openmoji', 'fluent-emoji'],
            },
            'Photos': {
                '_sources': ['unsplash', 'pexels', 'pixabay'],
            },
        };

        this.init();
    }

    async init() {
        try {
            const [sources, licenses, tags, manifest] = await Promise.all([
                this.fetchJSON(`${this.indexBase}/sources.json`),
                this.fetchJSON(`${this.indexBase}/licenses.json`).catch(() => []),
                this.fetchJSON(`${this.indexBase}/tags.json`),
                this.fetchJSON(`${this.indexBase}/search/_manifest.json`),
            ]);

            this.sources = sources;
            this.licenses = licenses;
            this.tags = tags;
            this.prefixManifest = manifest;

            this.populateSidebar();
            this.setupEventListeners();
            this.showInitialState();

        } catch (error) {
            console.error('Failed to initialize:', error);
            this.showError('Failed to load index. Make sure static files are built.');
        }
    }

    async fetchJSON(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
        return response.json();
    }

    populateSidebar() {
        this.renderSourcesTree();
        this.renderLicenses();
        this.renderCategories();
    }

    renderSourcesTree() {
        const container = document.getElementById('sourcesList');
        const html = this.buildTreeHtml(this.sourceTree, 0);
        container.innerHTML = html;
        this.attachTreeHandlers();
    }

    buildTreeHtml(tree, depth) {
        let html = '';

        for (const [key, value] of Object.entries(tree)) {
            if (key === '_sources') {
                // Leaf sources
                for (const sourceId of value) {
                    const source = this.sources.find(s => s.id === sourceId);
                    if (source) {
                        html += this.renderSourceItem(source, depth);
                    }
                }
            } else if (typeof value === 'object' && !Array.isArray(value)) {
                // Branch node with nested children
                const isExpanded = this.expandedNodes.has(key);
                const childSourceIds = this.getSourceIdsInBranch(value);
                const childCount = this.countSourcesInBranch(value);
                const allChecked = !childSourceIds.some(id => this.excludedSources.has(id));
                const someChecked = childSourceIds.some(id => !this.excludedSources.has(id));
                const indeterminate = someChecked && !allChecked;

                html += `
                    <div class="tree-branch" data-branch="${key}">
                        <div class="tree-branch-header" style="padding-left: ${depth * 16}px">
                            <input type="checkbox" class="branch-checkbox" data-branch="${key}"
                                   ${allChecked ? 'checked' : ''} ${indeterminate ? 'data-indeterminate="true"' : ''}>
                            <span class="tree-toggle">${isExpanded ? '▼' : '▶'}</span>
                            <span class="tree-label">${key}</span>
                            <span class="filter-count" data-branch-count="${key}">${childCount.toLocaleString()}</span>
                        </div>
                        <div class="tree-children${isExpanded ? '' : ' collapsed'}">
                            ${this.buildTreeHtml(value, depth + 1)}
                        </div>
                    </div>
                `;
            } else if (Array.isArray(value)) {
                // Array of source IDs (leaf group with checkbox)
                const isExpanded = this.expandedNodes.has(key);
                const matchingSources = value.map(id => this.sources.find(s => s.id === id)).filter(Boolean);
                const totalCount = matchingSources.reduce((sum, s) => sum + s.count, 0);
                const allChecked = !value.some(id => this.excludedSources.has(id));
                const someChecked = value.some(id => !this.excludedSources.has(id));
                const indeterminate = someChecked && !allChecked;

                html += `
                    <div class="tree-branch" data-branch="${key}">
                        <div class="tree-branch-header" style="padding-left: ${depth * 16}px">
                            <input type="checkbox" class="branch-checkbox" data-branch="${key}" data-sources="${value.join(',')}"
                                   ${allChecked ? 'checked' : ''} ${indeterminate ? 'data-indeterminate="true"' : ''}>
                            <span class="tree-toggle">${isExpanded ? '▼' : '▶'}</span>
                            <span class="tree-label">${key}</span>
                            <span class="filter-count" data-branch-count="${key}">${totalCount.toLocaleString()}</span>
                        </div>
                        <div class="tree-children${isExpanded ? '' : ' collapsed'}">
                            ${matchingSources.sort((a, b) => b.count - a.count)
                                .map(s => this.renderSourceItem(s, depth + 1)).join('')}
                        </div>
                    </div>
                `;
            }
        }

        // Add ungrouped sources at root level
        if (depth === 0) {
            const groupedIds = this.getAllSourceIds(this.sourceTree);
            const ungrouped = this.sources.filter(s => !groupedIds.includes(s.id));
            if (ungrouped.length > 0) {
                const allChecked = !ungrouped.some(s => this.excludedSources.has(s.id));
                html += `<div class="tree-branch" data-branch="Other">
                    <div class="tree-branch-header">
                        <input type="checkbox" class="branch-checkbox" data-branch="Other"
                               data-sources="${ungrouped.map(s => s.id).join(',')}" ${allChecked ? 'checked' : ''}>
                        <span class="tree-toggle">▼</span>
                        <span class="tree-label">Other</span>
                        <span class="filter-count">${ungrouped.reduce((s,x) => s+x.count, 0).toLocaleString()}</span>
                    </div>
                    <div class="tree-children">
                        ${ungrouped.map(s => this.renderSourceItem(s, 1)).join('')}
                    </div>
                </div>`;
            }
        }

        return html;
    }

    getSourceIdsInBranch(branch) {
        const ids = [];
        for (const [key, value] of Object.entries(branch)) {
            if (key === '_sources' && Array.isArray(value)) {
                ids.push(...value);
            } else if (Array.isArray(value)) {
                ids.push(...value);
            } else if (typeof value === 'object') {
                ids.push(...this.getSourceIdsInBranch(value));
            }
        }
        return ids;
    }

    countSourcesInBranch(branch) {
        let count = 0;
        for (const [key, value] of Object.entries(branch)) {
            if (key === '_sources' && Array.isArray(value)) {
                for (const id of value) {
                    const source = this.sources.find(s => s.id === id);
                    if (source) count += source.count;
                }
            } else if (Array.isArray(value)) {
                for (const id of value) {
                    const source = this.sources.find(s => s.id === id);
                    if (source) count += source.count;
                }
            } else if (typeof value === 'object') {
                count += this.countSourcesInBranch(value);
            }
        }
        return count;
    }

    getAllSourceIds(tree) {
        const ids = [];
        for (const [key, value] of Object.entries(tree)) {
            if (key === '_sources' && Array.isArray(value)) {
                ids.push(...value);
            } else if (Array.isArray(value)) {
                ids.push(...value);
            } else if (typeof value === 'object') {
                ids.push(...this.getAllSourceIds(value));
            }
        }
        return ids;
    }

    renderSourceItem(source, depth) {
        const isChecked = !this.excludedSources.has(source.id);
        const paddingLeft = depth * 16 + 24;
        return `
            <div class="filter-item${isChecked ? '' : ' excluded'}" data-id="${source.id}" data-type="source" style="padding-left: ${paddingLeft}px">
                <input type="checkbox" id="source-${source.id}" ${isChecked ? 'checked' : ''}>
                <label for="source-${source.id}">${this.escapeHtml(source.name)}</label>
                <span class="filter-count" data-source="${source.id}">${source.count.toLocaleString()}</span>
            </div>
        `;
    }

    attachTreeHandlers() {
        // Set indeterminate state
        document.querySelectorAll('.branch-checkbox[data-indeterminate="true"]').forEach(cb => {
            cb.indeterminate = true;
        });

        // Tree branch toggle (click on toggle or label)
        document.querySelectorAll('.tree-branch-header').forEach(header => {
            const toggle = header.querySelector('.tree-toggle');
            const label = header.querySelector('.tree-label');

            [toggle, label].forEach(el => {
                if (el) {
                    el.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const branch = header.closest('.tree-branch');
                        const branchName = branch.dataset.branch;
                        const children = branch.querySelector('.tree-children');
                        const toggleEl = header.querySelector('.tree-toggle');

                        if (this.expandedNodes.has(branchName)) {
                            this.expandedNodes.delete(branchName);
                            children.classList.add('collapsed');
                            toggleEl.textContent = '▶';
                        } else {
                            this.expandedNodes.add(branchName);
                            children.classList.remove('collapsed');
                            toggleEl.textContent = '▼';
                        }
                    });
                }
            });
        });

        // Branch checkbox handlers
        document.querySelectorAll('.branch-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                e.stopPropagation();
                const branchName = checkbox.dataset.branch;
                const checked = checkbox.checked;

                // Get all source IDs under this branch
                let sourceIds = [];
                if (checkbox.dataset.sources) {
                    sourceIds = checkbox.dataset.sources.split(',');
                } else {
                    // Find in tree structure
                    sourceIds = this.findSourcesInTree(branchName);
                }

                // Update exclusion set
                sourceIds.forEach(id => {
                    if (checked) {
                        this.excludedSources.delete(id);
                    } else {
                        this.excludedSources.add(id);
                    }
                });

                // Update child checkboxes
                const branch = checkbox.closest('.tree-branch');
                branch.querySelectorAll('.filter-item input[type="checkbox"]').forEach(cb => {
                    cb.checked = checked;
                    cb.closest('.filter-item').classList.toggle('excluded', !checked);
                });

                // Update nested branch checkboxes
                branch.querySelectorAll('.branch-checkbox').forEach(cb => {
                    if (cb !== checkbox) {
                        cb.checked = checked;
                        cb.indeterminate = false;
                    }
                });

                this.updateParentCheckboxes();
                this.updateActiveFilters();
                this.performSearch();
            });
        });

        // Source checkbox handlers
        document.querySelectorAll('#sourcesList .filter-item').forEach(item => {
            const checkbox = item.querySelector('input[type="checkbox"]');
            const id = item.dataset.id;

            item.addEventListener('click', (e) => {
                if (e.target === checkbox) return;
                e.stopPropagation();
                checkbox.checked = !checkbox.checked;
                this.handleSourceChange(id, checkbox.checked);
            });

            checkbox.addEventListener('change', () => {
                this.handleSourceChange(id, checkbox.checked);
            });
        });
    }

    findSourcesInTree(branchName) {
        const findInBranch = (tree) => {
            for (const [key, value] of Object.entries(tree)) {
                if (key === branchName) {
                    if (Array.isArray(value)) return value;
                    return this.getSourceIdsInBranch(value);
                }
                if (typeof value === 'object' && !Array.isArray(value)) {
                    const result = findInBranch(value);
                    if (result.length > 0) return result;
                }
            }
            return [];
        };
        return findInBranch(this.sourceTree);
    }

    handleSourceChange(id, checked) {
        if (checked) {
            this.excludedSources.delete(id);
        } else {
            this.excludedSources.add(id);
        }

        const item = document.querySelector(`.filter-item[data-id="${id}"]`);
        if (item) {
            item.classList.toggle('excluded', !checked);
        }

        this.updateParentCheckboxes();
        this.updateActiveFilters();
        this.performSearch();
    }

    updateParentCheckboxes() {
        // Update all branch checkboxes based on their children
        document.querySelectorAll('.tree-branch').forEach(branch => {
            const branchCheckbox = branch.querySelector(':scope > .tree-branch-header > .branch-checkbox');
            if (!branchCheckbox) return;

            const childCheckboxes = branch.querySelectorAll('.filter-item input[type="checkbox"]');
            if (childCheckboxes.length === 0) return;

            const checkedCount = Array.from(childCheckboxes).filter(cb => cb.checked).length;
            const allChecked = checkedCount === childCheckboxes.length;
            const noneChecked = checkedCount === 0;

            branchCheckbox.checked = allChecked;
            branchCheckbox.indeterminate = !allChecked && !noneChecked;
        });
    }

    renderLicenses() {
        const licenseCounts = new Map();

        this.sources.forEach(source => {
            const lic = source.license || 'Unknown';
            licenseCounts.set(lic, (licenseCounts.get(lic) || 0) + source.count);
        });

        this.licenses.forEach(l => {
            if (!licenseCounts.has(l.type)) {
                licenseCounts.set(l.type, l.count);
            }
        });

        const container = document.getElementById('licensesList');
        container.innerHTML = Array.from(licenseCounts.entries())
            .sort((a, b) => b[1] - a[1])
            .map(([license, count]) => {
                const isChecked = !this.excludedLicenses.has(license);
                const safeId = license.replace(/[^a-zA-Z0-9-_]/g, '_');
                return `
                    <div class="filter-item${isChecked ? '' : ' excluded'}" data-id="${license}" data-type="license">
                        <input type="checkbox" id="license-${safeId}" ${isChecked ? 'checked' : ''}>
                        <label for="license-${safeId}">${this.escapeHtml(license)}</label>
                        <span class="filter-count" data-license="${license}">${count.toLocaleString()}</span>
                    </div>
                `;
            }).join('');

        this.attachFilterHandlers('licensesList', 'license', this.excludedLicenses);
    }

    renderCategories() {
        const tagMap = new Map(this.tags.map(t => [t.tag, t.count]));
        const container = document.getElementById('categoriesList');
        const availableCategories = this.topCategories.filter(c => tagMap.has(c));

        container.innerHTML = availableCategories
            .map(cat => {
                const count = tagMap.get(cat) || 0;
                const isChecked = !this.excludedCategories.has(cat);
                return `
                    <div class="filter-item${isChecked ? '' : ' excluded'}" data-id="${cat}" data-type="category">
                        <input type="checkbox" id="category-${cat}" ${isChecked ? 'checked' : ''}>
                        <label for="category-${cat}">${cat}</label>
                        <span class="filter-count" data-category="${cat}">${count.toLocaleString()}</span>
                    </div>
                `;
            }).join('');

        this.attachFilterHandlers('categoriesList', 'category', this.excludedCategories);
    }

    attachFilterHandlers(containerId, type, excludedSet) {
        document.querySelectorAll(`#${containerId} .filter-item`).forEach(item => {
            const checkbox = item.querySelector('input[type="checkbox"]');
            const id = item.dataset.id;

            item.addEventListener('click', (e) => {
                if (e.target === checkbox) return;
                checkbox.checked = !checkbox.checked;
                this.handleFilterChange(type, id, checkbox.checked, excludedSet);
            });

            checkbox.addEventListener('change', () => {
                this.handleFilterChange(type, id, checkbox.checked, excludedSet);
            });
        });
    }

    handleFilterChange(type, id, checked, excludedSet) {
        if (checked) {
            excludedSet.delete(id);
        } else {
            excludedSet.add(id);
        }

        const item = document.querySelector(`.filter-item[data-id="${CSS.escape(id)}"][data-type="${type}"]`);
        if (item) {
            item.classList.toggle('excluded', !checked);
        }

        this.updateActiveFilters();
        this.performSearch();
    }

    updateActiveFilters() {
        const container = document.getElementById('activeFilters');
        const filters = [];

        // Show excluded items as "negative" filters
        this.excludedSources.forEach(id => {
            const source = this.sources.find(s => s.id === id);
            filters.push({ type: 'source', id, label: `−${source?.name || id}` });
        });
        this.excludedLicenses.forEach(id => {
            filters.push({ type: 'license', id, label: `−${id}` });
        });
        this.excludedCategories.forEach(id => {
            filters.push({ type: 'category', id, label: `−${id}` });
        });

        container.innerHTML = filters.map(f => `
            <span class="active-filter-tag excluded">
                ${this.escapeHtml(f.label)}
                <span class="remove" onclick="stagvault.removeExclusion('${f.type}', '${f.id.replace(/'/g, "\\'")}')">&times;</span>
            </span>
        `).join('');
    }

    removeExclusion(type, id) {
        let set;
        if (type === 'source') set = this.excludedSources;
        else if (type === 'license') set = this.excludedLicenses;
        else set = this.excludedCategories;

        set.delete(id);

        const item = document.querySelector(`.filter-item[data-id="${CSS.escape(id)}"][data-type="${type}"]`);
        if (item) {
            item.classList.remove('excluded');
            const checkbox = item.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.checked = true;
        }

        if (type === 'source') {
            this.updateParentCheckboxes();
        }

        this.updateActiveFilters();
        this.performSearch();
    }

    clearAllFilters() {
        this.excludedSources.clear();
        this.excludedLicenses.clear();
        this.excludedCategories.clear();

        document.querySelectorAll('.filter-item').forEach(item => {
            item.classList.remove('excluded');
            const cb = item.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = true;
        });

        document.querySelectorAll('.branch-checkbox').forEach(cb => {
            cb.checked = true;
            cb.indeterminate = false;
        });

        this.updateActiveFilters();
        this.performSearch();
    }

    toggleSection(section) {
        const list = document.getElementById(section + 'List');
        const toggle = document.getElementById(section + 'Toggle');
        list.classList.toggle('collapsed');
        toggle.textContent = list.classList.contains('collapsed') ? '+' : '-';
    }

    setupEventListeners() {
        const searchInput = document.getElementById('searchInput');
        const modalOverlay = document.getElementById('modalOverlay');
        const modalClose = document.getElementById('modalClose');

        searchInput.addEventListener('input', () => {
            clearTimeout(this.searchDebounceTimer);
            this.searchDebounceTimer = setTimeout(() => this.performSearch(), 150);
        });

        modalClose.addEventListener('click', () => this.closeModal());
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) this.closeModal();
        });

        document.getElementById('zoomIn').addEventListener('click', () => this.setZoom(this.zoomLevel + 1));
        document.getElementById('zoomOut').addEventListener('click', () => this.setZoom(this.zoomLevel - 1));

        document.getElementById('colorizeToggle').addEventListener('change', (e) => {
            this.colorizeEnabled = e.target.checked;
            this.toggleColorControls(this.colorizeEnabled);
            this.applyColorization();
        });

        document.getElementById('primaryColor').addEventListener('input', (e) => {
            this.primaryColor = e.target.value;
            this.applyColorization();
        });

        document.getElementById('secondaryColor').addEventListener('input', (e) => {
            this.secondaryColor = e.target.value;
            this.applyColorization();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeModal();
            if (e.key === '/' && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
            }
            if (this.currentItem) {
                if (e.key === '+' || e.key === '=') this.setZoom(this.zoomLevel + 1);
                if (e.key === '-') this.setZoom(this.zoomLevel - 1);
            }
        });
    }

    async showInitialState() {
        const totalItems = this.sources.reduce((sum, s) => sum + s.count, 0);
        document.getElementById('statsText').textContent =
            `${totalItems.toLocaleString()} icons from ${this.sources.length} sources`;

        await this.loadAndDisplaySamples();
    }

    async loadAndDisplaySamples() {
        try {
            const samples = [];
            // Load more prefixes to get better variety
            const prefixesToTry = this.prefixManifest.slice(0, 100);

            for (const prefixEntry of prefixesToTry) {
                let items = this.prefixCache.get(prefixEntry.prefix);
                if (!items) {
                    items = await this.fetchJSON(`${this.indexBase}/search/${prefixEntry.prefix}.json`);
                    this.prefixCache.set(prefixEntry.prefix, items);
                }

                items.forEach(item => {
                    if (!this.allLoadedItems.find(i => i.id === item.id)) {
                        this.allLoadedItems.push(item);
                    }
                });

                const filtered = this.applyFilters(items);
                samples.push(...filtered.slice(0, 10));

                if (samples.length >= 400) break;
            }

            // Deduplicate
            const seen = new Set();
            const unique = samples.filter(item => {
                if (seen.has(item.id)) return false;
                seen.add(item.id);
                return true;
            });

            // Shuffle and limit
            const displayItems = unique.sort(() => 0.5 - Math.random()).slice(0, 120);

            if (displayItems.length > 0) {
                this.displayResults(displayItems, null);
            } else {
                this.showEmptyState();
            }

        } catch (error) {
            console.error('Failed to load samples:', error);
            this.showEmptyState();
        }
    }

    applyFilters(items) {
        return items.filter(item => {
            // Source filter - exclude if in excludedSources
            if (this.excludedSources.has(item.s)) {
                return false;
            }

            // License filter - exclude if license is in excludedLicenses
            if (this.excludedLicenses.size > 0) {
                const itemLicense = item.l || this.sources.find(s => s.id === item.s)?.license;
                if (this.excludedLicenses.has(itemLicense)) return false;
            }

            // Category filter - exclude if ALL categories are excluded that the item has
            if (this.excludedCategories.size > 0) {
                const itemTags = item.t || [];
                const relevantTags = itemTags.filter(t => this.topCategories.includes(t));
                if (relevantTags.length > 0 && relevantTags.every(t => this.excludedCategories.has(t))) {
                    return false;
                }
            }

            return true;
        });
    }

    showEmptyState() {
        document.getElementById('resultsContainer').innerHTML = `
            <div class="empty-state">
                <h3>No icons found</h3>
                <p>Try adjusting your filters or search terms</p>
            </div>
        `;
    }

    async performSearch() {
        const query = document.getElementById('searchInput').value.trim().toLowerCase();

        if (query.length < 2) {
            await this.loadAndDisplaySamples();
            return;
        }

        document.getElementById('resultsContainer').innerHTML = `
            <div class="loading">
                <div class="loading-spinner"></div>
                <p>Searching...</p>
            </div>
        `;

        try {
            const prefix = query.substring(0, 2);
            const prefixEntry = this.prefixManifest.find(p => p.prefix === prefix);

            if (!prefixEntry) {
                this.showNoResults(query);
                return;
            }

            let items = this.prefixCache.get(prefix);
            if (!items) {
                items = await this.fetchJSON(`${this.indexBase}/search/${prefix}.json`);
                this.prefixCache.set(prefix, items);

                items.forEach(item => {
                    if (!this.allLoadedItems.find(i => i.id === item.id)) {
                        this.allLoadedItems.push(item);
                    }
                });
            }

            // Filter by query
            let results = items.filter(item => {
                const name = item.n.toLowerCase();
                const tags = (item.t || []).map(t => t.toLowerCase());
                const matchesName = name.includes(query);
                const matchesTag = tags.some(t => t.includes(query) || t === query);
                return matchesName || matchesTag;
            });

            // Apply sidebar filters
            results = this.applyFilters(results);

            // Rank results
            results = this.rankResults(results, query);

            this.currentResults = results;
            this.displayResults(results, query);

        } catch (error) {
            console.error('Search failed:', error);
            this.showError('Search failed. Please try again.');
        }
    }

    rankResults(results, query) {
        return results.sort((a, b) => {
            const scoreA = this.getMatchScore(a, query);
            const scoreB = this.getMatchScore(b, query);
            return scoreB - scoreA;
        });
    }

    getMatchScore(item, query) {
        const name = item.n.toLowerCase();
        const tags = (item.t || []).map(t => t.toLowerCase());

        let score = 0;

        if (name === query) {
            score += 1000;
        } else if (name.startsWith(query)) {
            score += 500;
        } else if (name.includes(': ' + query) || name.endsWith(' ' + query) || name.includes(' ' + query + ' ')) {
            score += 350;
        } else if (name.includes(query)) {
            score += 100;
        }

        if (tags.includes(query)) {
            score += 600;
        } else if (tags.some(t => t.startsWith(query))) {
            score += 250;
        } else if (tags.some(t => t.includes(query))) {
            score += 50;
        }

        score += Math.max(0, 30 - name.length);

        return score;
    }

    displayResults(results, query) {
        const container = document.getElementById('resultsContainer');

        if (query) {
            document.getElementById('statsText').innerHTML =
                `Found <strong>${results.length.toLocaleString()}</strong> icons for "${this.escapeHtml(query)}"`;
        } else {
            const hasExclusions = this.excludedSources.size + this.excludedLicenses.size + this.excludedCategories.size > 0;
            if (hasExclusions) {
                document.getElementById('statsText').innerHTML =
                    `Showing <strong>${results.length.toLocaleString()}</strong> filtered icons`;
            } else {
                const total = this.sources.reduce((sum, s) => sum + s.count, 0);
                document.getElementById('statsText').textContent =
                    `${total.toLocaleString()} icons from ${this.sources.length} sources`;
            }
        }

        if (results.length === 0) {
            this.showEmptyState();
            return;
        }

        const displayResults = results.slice(0, 200);

        container.innerHTML = `
            <div class="results-grid">
                ${displayResults.map((item, index) => this.renderCard(item, index)).join('')}
            </div>
            ${results.length > 200 ? `
                <div class="empty-state">
                    <p>Showing first 200 results. Refine your search for more specific results.</p>
                </div>
            ` : ''}
        `;

        container.querySelectorAll('.result-card').forEach((card, index) => {
            card.addEventListener('click', () => this.showModal(displayResults[index]));
        });
    }

    renderCard(item, index) {
        const source = this.sources.find(s => s.id === item.s);
        const sourceName = source ? source.name : item.s;

        const iconHtml = item.p
            ? `<img src="${item.p}" alt="${this.escapeHtml(item.n)}" loading="lazy">`
            : `<div class="placeholder"></div>`;

        const tags = (item.t || []).slice(0, 3);
        const tagsHtml = tags.length > 0
            ? `<div class="result-tags">${tags.map(t => `<span class="tag">${this.escapeHtml(t)}</span>`).join('')}</div>`
            : '';

        return `
            <div class="result-card" data-index="${index}">
                <div class="result-icon">${iconHtml}</div>
                <div class="result-name">${this.escapeHtml(item.n)}</div>
                <div class="result-meta">${this.escapeHtml(sourceName)}${item.y ? ` / ${this.escapeHtml(item.y)}` : ''}</div>
                ${tagsHtml}
            </div>
        `;
    }

    showNoResults(query) {
        document.getElementById('statsText').textContent = `No results for "${query}"`;
        this.showEmptyState();
    }

    showError(message) {
        document.getElementById('resultsContainer').innerHTML = `
            <div class="empty-state">
                <h3>Error</h3>
                <p>${this.escapeHtml(message)}</p>
            </div>
        `;
    }

    getColorMode(item) {
        if (item.y && item.y.toLowerCase() === 'duotone') return 'duotone';
        return this.sourceColorModes[item.s] || 'monochrome';
    }

    showModal(item) {
        this.currentItem = item;
        this.zoomLevel = 3;
        this.colorizeEnabled = false;
        this.colorMode = this.getColorMode(item);

        const source = this.sources.find(s => s.id === item.s);
        const sourceName = source ? source.name : item.s;
        const license = item.l || (source ? source.license : 'Unknown');
        const isColorizable = !this.nonColorableSources.has(item.s);

        document.getElementById('modalTitle').textContent = item.n;

        const previewImage = document.getElementById('previewImage');
        if (item.p) {
            const largeUrl = item.p.replace(/_64\.(jpg|png)$/, '_256.$1');
            this.originalImageUrl = largeUrl;
            previewImage.src = largeUrl;
            previewImage.alt = item.n;

            previewImage.onload = () => {
                if (this.colorMode === 'monochrome' && isColorizable) {
                    this.detectAndUpdateColorMode(previewImage);
                }
            };
        } else {
            previewImage.src = '';
            this.originalImageUrl = null;
        }

        this.setZoom(3);

        const colorizeToggle = document.getElementById('colorizeToggle');
        const colorizeContainer = colorizeToggle.closest('.colorize-toggle');
        if (isColorizable) {
            colorizeContainer.style.display = 'flex';
            colorizeToggle.checked = false;
            this.toggleColorControls(false);
            this.updateColorModeUI();
        } else {
            colorizeContainer.style.display = 'none';
            this.toggleColorControls(false);
        }

        const infoContainer = document.getElementById('modalInfo');
        const tags = (item.t || []).map(t => `<span class="tag">${this.escapeHtml(t)}</span>`).join(' ');

        const licenseUrl = license && license !== 'Unknown'
            ? `https://spdx.org/licenses/${encodeURIComponent(license)}.html`
            : null;
        const licenseHtml = licenseUrl
            ? `<a href="${licenseUrl}" target="_blank" rel="noopener">${this.escapeHtml(license)}</a>`
            : this.escapeHtml(license);

        const downloadUrl = this.originalImageUrl || item.p;

        infoContainer.innerHTML = `
            <h2>${this.escapeHtml(item.n)}</h2>
            <p>
                Source: ${this.escapeHtml(sourceName)}<br>
                ${item.y ? `Style: ${this.escapeHtml(item.y)}<br>` : ''}
                License: ${licenseHtml}
            </p>
            ${tags ? `<div class="result-tags">${tags}</div>` : ''}
            <div class="modal-actions">
                <button class="btn btn-secondary" onclick="stagvault.copyToClipboard('${item.id}')">
                    Copy ID
                </button>
                ${downloadUrl ? `
                    <a href="${downloadUrl}" target="_blank" class="btn btn-primary">
                        Download
                    </a>
                ` : ''}
            </div>
        `;

        document.getElementById('modalOverlay').classList.add('active');
    }

    detectAndUpdateColorMode(img) {
        this.canvas.width = img.naturalWidth;
        this.canvas.height = img.naturalHeight;
        this.ctx.drawImage(img, 0, 0);

        const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
        const data = imageData.data;

        let hasGrayValues = false;
        let hasColor = false;

        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
            if (a < 10) continue;

            if (Math.abs(r - g) > 10 || Math.abs(g - b) > 10 || Math.abs(r - b) > 10) {
                hasColor = true;
                break;
            }

            if (r > 20 && r < 235) hasGrayValues = true;
        }

        if (hasColor) {
            this.colorMode = 'duotone';
        } else if (hasGrayValues) {
            this.colorMode = 'grayscale';
        } else {
            this.colorMode = 'monochrome';
        }

        this.updateColorModeUI();
    }

    updateColorModeUI() {
        const secondaryControl = document.getElementById('secondaryColorControl');
        const primaryLabel = document.querySelector('#primaryColorControl label');

        if (this.colorMode === 'duotone') {
            secondaryControl.style.display = this.colorizeEnabled ? 'flex' : 'none';
            primaryLabel.textContent = 'Dark:';
        } else {
            secondaryControl.style.display = 'none';
            primaryLabel.textContent = 'Color:';
        }
    }

    closeModal() {
        this.currentItem = null;
        const previewImage = document.getElementById('previewImage');
        if (this.originalImageUrl) previewImage.src = this.originalImageUrl;
        document.getElementById('modalOverlay').classList.remove('active');
    }

    setZoom(level) {
        this.zoomLevel = Math.max(1, Math.min(3, level));
        const previewImage = document.getElementById('previewImage');
        previewImage.className = `preview-image zoom-${this.zoomLevel}`;
        const zoomPercent = [50, 75, 100][this.zoomLevel - 1];
        document.getElementById('zoomLevel').textContent = `${zoomPercent}%`;
    }

    toggleColorControls(show) {
        document.getElementById('primaryColorControl').style.display = show ? 'flex' : 'none';
        if (this.colorMode === 'duotone') {
            document.getElementById('secondaryColorControl').style.display = show ? 'flex' : 'none';
        } else {
            document.getElementById('secondaryColorControl').style.display = 'none';
        }
    }

    applyColorization() {
        const previewImage = document.getElementById('previewImage');

        if (!this.colorizeEnabled || !this.originalImageUrl) {
            if (this.originalImageUrl) previewImage.src = this.originalImageUrl;
            return;
        }

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
            this.canvas.width = img.naturalWidth;
            this.canvas.height = img.naturalHeight;
            this.ctx.drawImage(img, 0, 0);

            const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
            const data = imageData.data;
            const primary = this.hexToRgb(this.primaryColor);
            const secondary = this.hexToRgb(this.secondaryColor);

            if (this.colorMode === 'duotone') {
                this.applyDuotone(data, primary, secondary);
            } else if (this.colorMode === 'grayscale') {
                this.applyMultiply(data, primary);
            } else {
                this.applyReplace(data, primary);
            }

            this.ctx.putImageData(imageData, 0, 0);
            previewImage.src = this.canvas.toDataURL('image/png');
        };
        img.src = this.originalImageUrl;
    }

    applyDuotone(data, primary, secondary) {
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const lum = 0.299 * r + 0.587 * g + 0.114 * b;
            if (lum > 200) continue;
            if (lum < 80) {
                data[i] = primary.r;
                data[i + 1] = primary.g;
                data[i + 2] = primary.b;
            } else {
                data[i] = secondary.r;
                data[i + 1] = secondary.g;
                data[i + 2] = secondary.b;
            }
        }
    }

    applyMultiply(data, color) {
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const lum = 0.299 * r + 0.587 * g + 0.114 * b;
            if (lum > 200) continue;
            const factor = 1 - (lum / 200);
            data[i] = Math.round(color.r * factor + r * (1 - factor));
            data[i + 1] = Math.round(color.g * factor + g * (1 - factor));
            data[i + 2] = Math.round(color.b * factor + b * (1 - factor));
        }
    }

    applyReplace(data, color) {
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const lum = 0.299 * r + 0.587 * g + 0.114 * b;
            if (lum > 200) continue;
            data[i] = color.r;
            data[i + 1] = color.g;
            data[i + 2] = color.b;
        }
    }

    hexToRgb(hex) {
        hex = hex.replace('#', '');
        return {
            r: parseInt(hex.substr(0, 2), 16),
            g: parseInt(hex.substr(2, 2), 16),
            b: parseInt(hex.substr(4, 2), 16)
        };
    }

    copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Copied to clipboard!');
        }).catch(() => {
            this.showToast('Failed to copy');
        });
    }

    showToast(message) {
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--accent);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            z-index: 2000;
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.stagvault = new StagVault();
});
