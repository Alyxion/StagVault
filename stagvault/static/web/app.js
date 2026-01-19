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
        this.apiSearchDebounceTimer = null;
        this.currentSearchId = 0; // Track search requests to handle race conditions
        this.apiCache = new Map(); // In-memory cache for API responses
        this.API_CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours in ms

        // Filter state - these track EXCLUDED items (unchecked = excluded)
        this.excludedSources = new Set();
        this.excludedLicenses = new Set();

        // Expanded tree nodes
        this.expandedNodes = new Set(['Vector', 'Icons', 'Emoji']);

        // Modal state
        this.currentItem = null;
        this.zoomPercent = 100;
        this.fitZoomPercent = 100; // Calculated zoom to fit container
        this.panX = 0;
        this.panY = 0;
        this.isPanning = false;
        this.panStartX = 0;
        this.panStartY = 0;
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

        // API provider configuration
        this.apiProviders = {
            pexels: {
                name: 'Pexels',
                apiKey: null,
                enabled: false,
                baseUrl: 'https://api.pexels.com/v1',
                searchEndpoint: '/search',
                rateLimit: { remaining: 200, reset: null },
                licenses: ['Pexels License']
            },
            pixabay: {
                name: 'Pixabay',
                apiKey: null,
                enabled: false,
                baseUrl: 'https://pixabay.com/api',
                rateLimit: { remaining: 100, reset: null },
                licenses: ['Pixabay License']
            },
            unsplash: {
                name: 'Unsplash',
                apiKey: null,
                enabled: false,
                baseUrl: 'https://api.unsplash.com',
                searchEndpoint: '/search/photos',
                rateLimit: { remaining: 50, reset: null },
                licenses: ['Unsplash License']
            },
            wikimedia: {
                name: 'Wikimedia Commons',
                apiKey: null, // No key required
                enabled: true, // Enabled by default
                baseUrl: 'https://commons.wikimedia.org/w/api.php',
                rateLimit: { remaining: 100, reset: null },
                licenses: ['CC0', 'CC-BY', 'CC-BY-SA', 'CC-BY-SA-4.0', 'CC-BY-4.0', 'Public domain', 'GFDL']
            }
        };

        // Track dynamically discovered licenses from API results
        this.discoveredLicenses = new Set();

        // Load API keys from localStorage
        this.loadApiKeys();

        // Load API cache from localStorage
        this.loadApiCache();

        this.init();
    }

    async init() {
        try {
            const [sourcesData, licenses, tags, manifest] = await Promise.all([
                this.fetchJSON(`${this.indexBase}/sources.json`),
                this.fetchJSON(`${this.indexBase}/licenses.json`).catch(() => []),
                this.fetchJSON(`${this.indexBase}/tags.json`),
                this.fetchJSON(`${this.indexBase}/search/_manifest.json`),
            ]);

            // Handle both old format (array) and new format ({ sources: [], tree: {} })
            if (Array.isArray(sourcesData)) {
                this.sources = sourcesData;
            } else {
                this.sources = sourcesData.sources || [];
                if (sourcesData.tree) {
                    this.sourceTree = sourcesData.tree;
                }
            }
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
        this.addApiSourcesToTree();
        this.renderSourcesTree();
        this.renderLicenses();
        // Categories are filtered via search word, not sidebar
    }

    addApiSourcesToTree() {
        // Add enabled API providers as sources
        for (const [providerId, config] of Object.entries(this.apiProviders)) {
            if (config.enabled && (providerId === 'wikimedia' || config.apiKey)) {
                // Check if source already exists
                if (!this.sources.find(s => s.id === providerId)) {
                    this.sources.push({
                        id: providerId,
                        name: config.name,
                        count: 0, // Dynamic, unknown count
                        license: config.licenses[0] || 'Various',
                        _isApi: true
                    });
                }
                // Add known licenses for this provider
                config.licenses.forEach(lic => this.discoveredLicenses.add(lic));
            }
        }
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

        // Count from static sources
        this.sources.forEach(source => {
            const lic = source.license || 'Unknown';
            licenseCounts.set(lic, (licenseCounts.get(lic) || 0) + source.count);
        });

        // Add from licenses.json
        this.licenses.forEach(l => {
            if (!licenseCounts.has(l.type)) {
                licenseCounts.set(l.type, l.count);
            }
        });

        // Add discovered licenses from API results (with 0 count initially)
        this.discoveredLicenses.forEach(lic => {
            if (!licenseCounts.has(lic)) {
                licenseCounts.set(lic, 0);
            }
        });

        const container = document.getElementById('licensesList');
        container.innerHTML = Array.from(licenseCounts.entries())
            .sort((a, b) => {
                // Sort by count descending, but keep 0-count items at the end
                if (a[1] === 0 && b[1] > 0) return 1;
                if (b[1] === 0 && a[1] > 0) return -1;
                return b[1] - a[1];
            })
            .map(([license, count]) => {
                const isChecked = !this.excludedLicenses.has(license);
                const safeId = license.replace(/[^a-zA-Z0-9-_]/g, '_');
                const countDisplay = count > 0 ? count.toLocaleString() : 'API';
                return `
                    <div class="filter-item${isChecked ? '' : ' excluded'}" data-id="${license}" data-type="license">
                        <input type="checkbox" id="license-${safeId}" ${isChecked ? 'checked' : ''}>
                        <label for="license-${safeId}">${this.escapeHtml(license)}</label>
                        <span class="filter-count" data-license="${license}">${countDisplay}</span>
                    </div>
                `;
            }).join('');

        this.attachFilterHandlers('licensesList', 'license', this.excludedLicenses);
    }

    // Called when API results contain new licenses
    addDiscoveredLicense(license) {
        if (!license || this.discoveredLicenses.has(license)) return false;
        this.discoveredLicenses.add(license);
        return true;
    }

    // Update sidebar when new licenses are discovered
    refreshLicensesIfNeeded(items) {
        let needsRefresh = false;
        for (const item of items) {
            if (item.l && this.addDiscoveredLicense(item.l)) {
                needsRefresh = true;
            }
        }
        if (needsRefresh) {
            this.renderLicenses();
        }
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
        else return; // Only source and license filters supported

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

        document.getElementById('zoomIn').addEventListener('click', () => this.zoomIn());
        document.getElementById('zoomOut').addEventListener('click', () => this.zoomOut());
        document.getElementById('zoomFit').addEventListener('click', () => this.zoomToFit());

        // SVG size preset buttons
        document.querySelectorAll('.svg-size-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setSvgSize(parseInt(btn.dataset.size)));
        });

        // Pan/drag support for preview image
        const previewContainer = document.getElementById('previewContainer');
        previewContainer.addEventListener('mousedown', (e) => this.startPan(e));
        previewContainer.addEventListener('mousemove', (e) => this.doPan(e));
        previewContainer.addEventListener('mouseup', () => this.endPan());
        previewContainer.addEventListener('mouseleave', () => this.endPan());
        previewContainer.addEventListener('wheel', (e) => this.handleWheel(e), { passive: false });

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
            if (e.key === 'Escape') {
                this.closeModal();
                this.closeSettings();
            }
            if (e.key === '/' && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
            }
            if (this.currentItem) {
                if (e.key === '+' || e.key === '=') this.zoomIn();
                if (e.key === '-') this.zoomOut();
                if (e.key === '0') this.zoomToFit();
            }
        });

        // Close settings modal when clicking outside
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target.id === 'settingsModal') this.closeSettings();
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

        // Cancel any pending API search
        if (this.apiSearchDebounceTimer) {
            clearTimeout(this.apiSearchDebounceTimer);
            this.apiSearchDebounceTimer = null;
        }

        if (query.length < 2) {
            this.currentSearchId++;
            await this.loadAndDisplaySamples();
            return;
        }

        // Increment search ID to track this search request
        const searchId = ++this.currentSearchId;

        document.getElementById('resultsContainer').innerHTML = `
            <div class="loading">
                <div class="loading-spinner"></div>
                <p>Searching...</p>
            </div>
        `;

        try {
            // First, get static results immediately
            const staticResults = await this.searchStaticIndex(query);

            // Check if this search is still current
            if (searchId !== this.currentSearchId) return;

            // Display static results immediately
            let results = this.rankResults([...staticResults], query);
            this.currentResults = results;
            this.displayResults(results, query, true); // true = API search pending

            // Schedule API search after user stops typing (800ms delay)
            const enabledProviders = this.getEnabledProviders();
            if (enabledProviders.length > 0) {
                this.apiSearchDebounceTimer = setTimeout(async () => {
                    // Check if this search is still current
                    if (searchId !== this.currentSearchId) return;

                    try {
                        const apiResults = await this.searchApiProviders(query);

                        // Check again after API call completes
                        if (searchId !== this.currentSearchId) return;

                        // Discover new licenses from API results
                        this.refreshLicensesIfNeeded(apiResults);

                        // Apply filters to API results too
                        const filteredApiResults = this.applyFilters(apiResults);

                        // Merge and re-rank all results
                        const mergedResults = [...staticResults, ...filteredApiResults];
                        const rankedResults = this.rankResults(mergedResults, query);

                        this.currentResults = rankedResults;
                        this.displayResults(rankedResults, query, false); // false = API search complete
                    } catch (error) {
                        console.error('API search failed:', error);
                        // Keep showing static results on API error
                    }
                }, 800); // 800ms delay for API search
            }

        } catch (error) {
            console.error('Search failed:', error);
            if (searchId === this.currentSearchId) {
                this.showError('Search failed. Please try again.');
            }
        }
    }

    async searchStaticIndex(query) {
        const prefix = query.substring(0, 2);
        const prefixEntry = this.prefixManifest.find(p => p.prefix === prefix);

        if (!prefixEntry) {
            return [];
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

        return results;
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

    displayResults(results, query, apiPending = false) {
        const container = document.getElementById('resultsContainer');

        // Count static vs API results
        const staticCount = results.filter(r => !r._apiItem).length;
        const apiCount = results.filter(r => r._apiItem).length;

        if (query) {
            let statsText = `Found <strong>${results.length.toLocaleString()}</strong> results for "${this.escapeHtml(query)}"`;
            if (apiCount > 0) {
                statsText += ` <span style="opacity: 0.7">(${staticCount} icons + ${apiCount} from APIs)</span>`;
            } else if (apiPending && this.getEnabledProviders().length > 0) {
                statsText += ` <span style="opacity: 0.7">— searching APIs...</span>`;
            }
            document.getElementById('statsText').innerHTML = statsText;
        } else {
            const hasExclusions = this.excludedSources.size + this.excludedLicenses.size > 0;
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
        const sourceName = this.getSourceDisplayName(item.s);
        const isApiItem = item._apiItem === true;

        const iconHtml = item.p
            ? `<img src="${item.p}" alt="${this.escapeHtml(item.n)}" loading="lazy" onerror="this.style.display='none';this.parentElement.classList.add('placeholder')">`
            : `<div class="placeholder"></div>`;

        const tags = (item.t || []).slice(0, 3);
        const tagsHtml = tags.length > 0
            ? `<div class="result-tags">${tags.map(t => `<span class="tag">${this.escapeHtml(t)}</span>`).join('')}</div>`
            : '';

        return `
            <div class="result-card${isApiItem ? ' api-result' : ''}" data-index="${index}">
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
        this.zoomPercent = 100; // Will be recalculated on image load
        this.fitZoomPercent = 100;
        this.panX = 0;
        this.panY = 0;
        this.colorizeEnabled = false;
        this.colorMode = this.getColorMode(item);

        const source = this.sources.find(s => s.id === item.s);
        const sourceName = this.getSourceDisplayName(item.s);
        const license = item.l || (source ? source.license : 'Unknown');
        const isApiItem = item._apiItem === true;
        const isColorizable = !isApiItem && !this.nonColorableSources.has(item.s);

        document.getElementById('modalTitle').textContent = item.n;

        const previewImage = document.getElementById('previewImage');

        // Common onload handler to calculate fit zoom
        const onImageLoad = () => {
            this.calculateFitZoom(previewImage);
            if (this.colorMode === 'monochrome' && isColorizable) {
                this.detectAndUpdateColorMode(previewImage);
            }
        };

        // Error handler for failed images - with fallback chain
        let fallbackAttempted = false;
        const onImageError = () => {
            const failedSrc = previewImage.src;
            console.error('Failed to load image:', failedSrc);

            // For static items, try falling back to thumbnail (_64) if _256 failed
            if (!fallbackAttempted && item.p && failedSrc.includes('_256.')) {
                fallbackAttempted = true;
                console.log('Falling back to thumbnail:', item.p);
                previewImage.src = item.p;
                this.originalImageUrl = item.p;
                return;
            }

            // Show placeholder
            previewImage.src = 'data:image/svg+xml,' + encodeURIComponent(
                '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">' +
                '<rect fill="#1a1a2e" width="200" height="200"/>' +
                '<text x="100" y="90" text-anchor="middle" fill="#666" font-size="14">Image not available</text>' +
                '<text x="100" y="115" text-anchor="middle" fill="#555" font-size="11">CORS or hotlink blocked</text>' +
                '</svg>'
            );
        };
        previewImage.onerror = onImageError;

        if (isApiItem) {
            // API items: show thumbnail first, then load full resolution
            this.originalImageUrl = item._original || item.p;
            previewImage.src = item.p; // Start with thumbnail
            previewImage.alt = item.n;
            previewImage.onload = onImageLoad;

            // Load full resolution image (cached)
            if (item._original && item._original !== item.p) {
                this.loadFullResolutionImage(item._original, previewImage);
            }
        } else if (item.p) {
            const largeUrl = item.p.replace(/_64\.(jpg|png)$/, '_256.$1');
            this.originalImageUrl = largeUrl;
            previewImage.src = largeUrl;
            previewImage.alt = item.n;
            previewImage.onload = onImageLoad;
        } else {
            previewImage.src = '';
            this.originalImageUrl = null;
        }

        // Show/hide SVG size presets
        const svgSizeControls = document.getElementById('svgSizeControls');
        if (svgSizeControls) {
            svgSizeControls.style.display = this.isSvgSource(item.s) ? 'flex' : 'none';
        }

        this.applyZoom();

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

        // Build license HTML
        let licenseHtml;
        if (license && license !== 'Unknown') {
            // Check if it's a standard SPDX license
            if (/^[A-Z0-9.\-]+$/i.test(license) && !license.includes('License')) {
                licenseHtml = `<a href="https://spdx.org/licenses/${encodeURIComponent(license)}.html" target="_blank" rel="noopener">${this.escapeHtml(license)}</a>`;
            } else {
                licenseHtml = this.escapeHtml(license);
            }
        } else {
            licenseHtml = 'Unknown';
        }

        // Build attribution for API items
        let attributionHtml = '';
        if (isApiItem) {
            if (item._photographer && item._photographerUrl) {
                attributionHtml = `<br>Photo by <a href="${item._photographerUrl}" target="_blank" rel="noopener">${this.escapeHtml(item._photographer)}</a>`;
            } else if (item._user && item._userUrl) {
                attributionHtml = `<br>By <a href="${item._userUrl}" target="_blank" rel="noopener">${this.escapeHtml(item._user)}</a>`;
            } else if (item._artist) {
                // Strip HTML tags from Wikimedia artist field
                const artistText = item._artist.replace(/<[^>]*>/g, '');
                attributionHtml = `<br>By ${this.escapeHtml(artistText)}`;
            }
        }

        // Build resolution info for API items
        let resolutionHtml = '';
        if (isApiItem && item._width && item._height) {
            resolutionHtml = `<br>Resolution: ${item._width} × ${item._height}`;
        }

        // Determine download button type
        const isSvgSource = !isApiItem && this.isSvgSource(item.s);
        const downloadButton = isApiItem
            ? this.renderApiDownloadButton(item)
            : this.renderDownloadButton(item, isSvgSource);

        infoContainer.innerHTML = `
            <h2>${this.escapeHtml(item.n)}</h2>
            <p>
                Source: ${this.escapeHtml(sourceName)}${attributionHtml}${resolutionHtml}<br>
                ${item.y ? `Style: ${this.escapeHtml(item.y)}<br>` : ''}
                License: ${licenseHtml}
            </p>
            ${tags ? `<div class="result-tags">${tags}</div>` : ''}
            <div class="modal-actions">
                ${downloadButton}
            </div>
        `;

        document.getElementById('modalOverlay').classList.add('active');
    }

    getSourceDisplayName(sourceId) {
        // Check static sources first
        const source = this.sources.find(s => s.id === sourceId);
        if (source) return source.name;

        // Check API providers
        const providerNames = {
            'pexels': 'Pexels',
            'pixabay': 'Pixabay',
            'unsplash': 'Unsplash',
            'wikimedia': 'Wikimedia Commons'
        };
        return providerNames[sourceId] || sourceId;
    }

    renderApiDownloadButton(item) {
        const downloadUrl = item._directUrl || item._original || item.p;
        if (!downloadUrl) return '';

        // For Pixabay and some others, direct download is blocked - show link to page
        const pageUrl = item._pageUrl;
        const hasPageLink = pageUrl && (item.s === 'pixabay' || item.s === 'wikimedia');

        let buttons = `
            <button class="btn btn-primary" onclick="stagvault.downloadApiImage('${downloadUrl}', '${this.sanitizeFilename(item.n)}')">
                Download
            </button>
        `;

        if (hasPageLink) {
            buttons += `
                <a href="${pageUrl}" target="_blank" rel="noopener" class="btn btn-secondary" style="margin-left: 8px;">
                    View on ${item.s === 'pixabay' ? 'Pixabay' : 'Wikimedia'}
                </a>
            `;
        }

        return buttons;
    }

    async downloadApiImage(url, filename) {
        try {
            // For some APIs we need to trigger download differently
            if (this.currentItem?._downloadUrl) {
                // Unsplash requires using their download endpoint
                window.open(this.currentItem._downloadUrl, '_blank');
                this.showToast('Download started');
                return;
            }

            // Try to fetch and download
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to fetch image');

            const blob = await response.blob();
            const ext = this.getExtensionFromMime(blob.type) || 'jpg';
            this.downloadBlob(blob, `${filename}.${ext}`);
            this.showToast('Downloaded!');
        } catch (error) {
            // Fallback: open in new tab
            console.error('Download failed, opening in new tab:', error);
            window.open(url, '_blank');
        }
    }

    getExtensionFromMime(mimeType) {
        const mimeMap = {
            'image/jpeg': 'jpg',
            'image/png': 'png',
            'image/gif': 'gif',
            'image/webp': 'webp',
            'image/svg+xml': 'svg'
        };
        return mimeMap[mimeType] || null;
    }

    async loadFullResolutionImage(url, imgElement) {
        // Check if we have this image cached as a blob URL
        const cacheKey = `img:${url}`;
        const cached = this.getCachedApiResponse(cacheKey);

        if (cached) {
            // Use cached blob URL
            imgElement.src = cached;
            this.originalImageUrl = cached;
            return;
        }

        try {
            // Fetch the full resolution image
            const response = await fetch(url);
            if (!response.ok) return;

            const blob = await response.blob();
            const blobUrl = URL.createObjectURL(blob);

            // Only update if this modal is still showing the same item
            if (imgElement.isConnected && this.currentItem) {
                imgElement.src = blobUrl;
                this.originalImageUrl = blobUrl;

                // Cache the blob URL (note: blob URLs are session-specific)
                // We'll cache the URL for quick re-access within the same session
                this.setCachedApiResponse(cacheKey, blobUrl);
            } else {
                // Clean up if modal was closed
                URL.revokeObjectURL(blobUrl);
            }
        } catch (error) {
            console.error('Failed to load full resolution image:', error);
            // Keep showing the thumbnail
        }
    }

    isSvgSource(sourceId) {
        // Icon sources that are SVG-based
        const svgSources = new Set([
            'phosphor-icons', 'lucide', 'heroicons', 'feather', 'tabler-icons',
            'bootstrap-icons', 'ionicons', 'octicons', 'boxicons', 'eva-icons',
            'iconoir', 'remix-icon', 'simple-icons', 'material-design'
        ]);
        return svgSources.has(sourceId);
    }

    renderDownloadButton(item, isSvgSource) {
        if (isSvgSource) {
            return `
                <div class="download-dropdown">
                    <button class="btn btn-primary" onclick="stagvault.toggleDownloadMenu(event)">
                        ↓ Download
                    </button>
                    <div class="download-menu" id="downloadMenu">
                        <div class="download-menu-header">Vector</div>
                        <button class="download-menu-item" onclick="stagvault.downloadSvg()">
                            SVG (Original)
                        </button>
                        <div class="download-menu-divider"></div>
                        <div class="download-menu-header">PNG Export</div>
                        <button class="download-menu-item" onclick="stagvault.downloadPng(128)">
                            PNG 128×128
                        </button>
                        <button class="download-menu-item" onclick="stagvault.downloadPng(256)">
                            PNG 256×256
                        </button>
                        <button class="download-menu-item" onclick="stagvault.downloadPng(512)">
                            PNG 512×512
                        </button>
                    </div>
                </div>
            `;
        } else {
            // For raster images (emoji, photos), just download original
            const downloadUrl = this.originalImageUrl || item.p;
            if (!downloadUrl) return '';
            return `
                <button class="btn btn-primary" onclick="stagvault.downloadOriginal()">
                    ↓ Download
                </button>
            `;
        }
    }

    toggleDownloadMenu(event) {
        event.stopPropagation();
        const menu = document.getElementById('downloadMenu');
        menu.classList.toggle('active');

        // Close menu when clicking outside
        const closeMenu = (e) => {
            if (!menu.contains(e.target) && !e.target.closest('.download-dropdown')) {
                menu.classList.remove('active');
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }

    async downloadSvg() {
        if (!this.currentItem) return;

        const item = this.currentItem;
        // Construct SVG URL from source and item info
        const svgUrl = this.getSvgUrl(item);

        if (!svgUrl) {
            this.showToast('SVG not available');
            return;
        }

        try {
            const response = await fetch(svgUrl);
            if (!response.ok) throw new Error('Failed to fetch SVG');

            let svgText = await response.text();

            // Apply colorization if enabled
            if (this.colorizeEnabled) {
                svgText = this.colorizeSvg(svgText);
            }

            // Download
            const blob = new Blob([svgText], { type: 'image/svg+xml' });
            this.downloadBlob(blob, `${this.sanitizeFilename(item.n)}.svg`);
            this.showToast('SVG downloaded!');
        } catch (error) {
            console.error('SVG download failed:', error);
            this.showToast('Download failed');
        }

        document.getElementById('downloadMenu').classList.remove('active');
    }

    getSvgUrl(item) {
        // Construct SVG URL based on source repository structure
        const name = item.n.toLowerCase().replace(/\s+/g, '-');
        const style = item.y || 'regular';

        // Source-specific URL patterns
        const urlBuilders = {
            'phosphor-icons': () => {
                // Phosphor uses: assets/{weight}/{name}.svg
                const weight = style === 'regular' ? 'regular' : style;
                return `https://raw.githubusercontent.com/phosphor-icons/core/main/assets/${weight}/${name}.svg`;
            },
            'lucide': () => {
                // Lucide uses: icons/{name}.svg
                return `https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/${name}.svg`;
            },
            'feather': () => {
                // Feather uses: icons/{name}.svg
                return `https://raw.githubusercontent.com/feathericons/feather/main/icons/${name}.svg`;
            },
            'heroicons': () => {
                // Heroicons uses: src/{style}/24/{style}/{name}.svg
                const heroStyle = style === 'solid' ? 'solid' : 'outline';
                return `https://raw.githubusercontent.com/tailwindlabs/heroicons/master/src/24/${heroStyle}/${name}.svg`;
            },
            'tabler-icons': () => {
                // Tabler uses: icons/outline/{name}.svg or icons/filled/{name}.svg
                const tablerStyle = style === 'filled' ? 'filled' : 'outline';
                return `https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/${tablerStyle}/${name}.svg`;
            },
            'bootstrap-icons': () => {
                return `https://raw.githubusercontent.com/twbs/icons/main/icons/${name}.svg`;
            },
            'ionicons': () => {
                return `https://raw.githubusercontent.com/ionic-team/ionicons/main/src/svg/${name}.svg`;
            },
            'octicons': () => {
                return `https://raw.githubusercontent.com/primer/octicons/main/icons/${name}-24.svg`;
            },
            'simple-icons': () => {
                return `https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/${name}.svg`;
            },
            'remix-icon': () => {
                // RemixIcon has category folders, try common pattern
                return `https://raw.githubusercontent.com/Remix-Design/RemixIcon/master/icons/System/${name}.svg`;
            },
        };

        const builder = urlBuilders[item.s];
        if (builder) {
            return builder();
        }

        return null;
    }

    colorizeSvg(svgText) {
        // Replace fill and stroke colors in SVG
        const color = this.primaryColor;

        // Replace currentColor
        svgText = svgText.replace(/currentColor/gi, color);

        // Replace black/dark fills (but preserve 'none')
        svgText = svgText.replace(/fill="(?!none)(#[0-9a-fA-F]{3,6}|black|rgb\([^)]+\))"/gi, `fill="${color}"`);

        // Replace strokes
        svgText = svgText.replace(/stroke="(?!none)(#[0-9a-fA-F]{3,6}|black|currentColor|rgb\([^)]+\))"/gi, `stroke="${color}"`);

        return svgText;
    }

    async downloadPng(size) {
        if (!this.currentItem) return;

        const item = this.currentItem;
        document.getElementById('downloadMenu').classList.remove('active');

        try {
            // For SVG sources, render fresh from SVG
            const svgUrl = this.getSvgUrl(item);

            if (svgUrl) {
                await this.renderSvgToPng(svgUrl, size, item.n);
            } else {
                // Fallback: try to use the thumbnail but warn about quality
                this.showToast('SVG not available, using thumbnail');
                await this.renderImageToPng(size, item.n);
            }
        } catch (error) {
            console.error('PNG export failed:', error);
            this.showToast('Export failed');
        }
    }

    async renderSvgToPng(svgUrl, size, name) {
        // Fetch the SVG
        const response = await fetch(svgUrl);
        if (!response.ok) throw new Error('Failed to fetch SVG');

        let svgText = await response.text();

        // Apply colorization if enabled
        if (this.colorizeEnabled) {
            svgText = this.colorizeSvg(svgText);
        }

        // Parse SVG to get dimensions
        const parser = new DOMParser();
        const svgDoc = parser.parseFromString(svgText, 'image/svg+xml');
        const svgEl = svgDoc.documentElement;

        // Set explicit size on SVG for proper rendering
        svgEl.setAttribute('width', size);
        svgEl.setAttribute('height', size);

        // Serialize back to string
        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(svgEl);

        // Create blob URL for the SVG
        const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
        const svgBlobUrl = URL.createObjectURL(svgBlob);

        // Create canvas
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        // Render SVG to canvas
        const img = new Image();

        await new Promise((resolve, reject) => {
            img.onload = () => {
                // Clear canvas (transparent background)
                ctx.clearRect(0, 0, size, size);

                // Draw SVG centered
                ctx.drawImage(img, 0, 0, size, size);

                URL.revokeObjectURL(svgBlobUrl);
                resolve();
            };
            img.onerror = () => {
                URL.revokeObjectURL(svgBlobUrl);
                reject(new Error('Failed to load SVG'));
            };
            img.src = svgBlobUrl;
        });

        // Export as PNG
        canvas.toBlob((blob) => {
            if (blob) {
                this.downloadBlob(blob, `${this.sanitizeFilename(name)}_${size}.png`);
                this.showToast(`PNG ${size}×${size} downloaded!`);
            }
        }, 'image/png');
    }

    async renderImageToPng(size, name) {
        const previewImage = document.getElementById('previewImage');

        // Create canvas
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');

        // Load from original URL (not the displayed one which may have checkerboard)
        const img = new Image();
        img.crossOrigin = 'anonymous';

        await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = reject;
            img.src = this.originalImageUrl || previewImage.src;
        });

        // Clear canvas (transparent)
        ctx.clearRect(0, 0, size, size);

        // Calculate scaling to fit while maintaining aspect ratio
        const scale = Math.min(size / img.naturalWidth, size / img.naturalHeight);
        const w = img.naturalWidth * scale;
        const h = img.naturalHeight * scale;
        const x = (size - w) / 2;
        const y = (size - h) / 2;

        ctx.drawImage(img, x, y, w, h);

        // Apply colorization if enabled
        if (this.colorizeEnabled) {
            const imageData = ctx.getImageData(0, 0, size, size);
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

            ctx.putImageData(imageData, 0, 0);
        }

        // Export as PNG
        canvas.toBlob((blob) => {
            if (blob) {
                this.downloadBlob(blob, `${this.sanitizeFilename(name)}_${size}.png`);
                this.showToast(`PNG ${size}×${size} downloaded!`);
            }
        }, 'image/png');
    }

    async downloadOriginal() {
        if (!this.currentItem) return;

        const item = this.currentItem;
        const url = this.originalImageUrl || item.p;

        if (!url) {
            this.showToast('Download not available');
            return;
        }

        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to fetch');

            const blob = await response.blob();
            const ext = url.includes('.png') ? 'png' : url.includes('.svg') ? 'svg' : 'jpg';
            this.downloadBlob(blob, `${this.sanitizeFilename(item.n)}.${ext}`);
            this.showToast('Downloaded!');
        } catch (error) {
            // Fallback: open in new tab
            window.open(url, '_blank');
        }
    }

    downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    sanitizeFilename(name) {
        return name.replace(/[^a-zA-Z0-9_-]/g, '_').replace(/_+/g, '_').slice(0, 50);
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

    calculateFitZoom(img) {
        const container = document.getElementById('previewContainer');
        if (!img.naturalWidth || !img.naturalHeight || !container) return;

        const containerWidth = container.clientWidth - 20; // padding
        const containerHeight = container.clientHeight - 20;

        const scaleX = containerWidth / img.naturalWidth;
        const scaleY = containerHeight / img.naturalHeight;
        const fitScale = Math.min(scaleX, scaleY, 1); // Don't upscale beyond 100%

        this.fitZoomPercent = Math.round(fitScale * 100);
        this.zoomPercent = this.fitZoomPercent;
        this.panX = 0;
        this.panY = 0;
        this.applyZoom();
    }

    // Zoom steps: double/half, clamped to 10-400%
    zoomIn() {
        if (this.zoomPercent < 400) {
            this.zoomPercent = Math.min(400, Math.round(this.zoomPercent * 1.5));
        }
        this.applyZoom();
    }

    zoomOut() {
        if (this.zoomPercent > 10) {
            this.zoomPercent = Math.max(10, Math.round(this.zoomPercent / 1.5));
        }
        this.applyZoom();
    }

    zoomToFit() {
        this.zoomPercent = this.fitZoomPercent;
        this.panX = 0;
        this.panY = 0;
        this.applyZoom();
    }

    setSvgSize(size) {
        // Set zoom to show SVG at exact pixel size
        const img = document.getElementById('previewImage');
        if (!img.naturalWidth) return;

        // Calculate zoom % to show at this size
        this.zoomPercent = Math.round((size / img.naturalWidth) * 100);
        this.panX = 0;
        this.panY = 0;
        this.applyZoom();
    }

    applyZoom() {
        const previewImage = document.getElementById('previewImage');
        if (!previewImage) return;

        const scale = this.zoomPercent / 100;

        previewImage.style.width = 'auto';
        previewImage.style.height = 'auto';
        previewImage.style.maxWidth = 'none';
        previewImage.style.maxHeight = 'none';
        previewImage.style.objectFit = 'none';
        previewImage.style.transform = `scale(${scale}) translate(${this.panX / scale}px, ${this.panY / scale}px)`;
        previewImage.style.cursor = this.zoomPercent > this.fitZoomPercent ? 'grab' : 'zoom-in';

        document.getElementById('zoomLevel').textContent = `${this.zoomPercent}%`;
    }

    startPan(e) {
        if (this.zoomPercent <= this.fitZoomPercent) {
            // At or below fit, click to zoom in
            this.zoomIn();
            return;
        }
        this.isPanning = true;
        this.panStartX = e.clientX - this.panX;
        this.panStartY = e.clientY - this.panY;
        document.getElementById('previewImage').style.cursor = 'grabbing';
    }

    doPan(e) {
        if (!this.isPanning) return;
        e.preventDefault();
        this.panX = e.clientX - this.panStartX;
        this.panY = e.clientY - this.panStartY;
        this.applyZoom();
    }

    endPan() {
        this.isPanning = false;
        if (this.zoomPercent > this.fitZoomPercent) {
            document.getElementById('previewImage').style.cursor = 'grab';
        }
    }

    handleWheel(e) {
        if (!this.currentItem) return;
        e.preventDefault();
        if (e.deltaY < 0) {
            this.zoomIn();
        } else {
            this.zoomOut();
        }
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

    // ==========================================
    // API Provider Methods
    // ==========================================

    loadApiKeys() {
        try {
            const stored = localStorage.getItem('stagvault_api_keys');
            if (stored) {
                const keys = JSON.parse(stored);
                for (const [provider, data] of Object.entries(keys)) {
                    if (this.apiProviders[provider]) {
                        this.apiProviders[provider].apiKey = data.apiKey || null;
                        this.apiProviders[provider].enabled = data.enabled || false;
                    }
                }
            }
            // Wikimedia is always enabled by default (no key needed)
            const wikimediaEnabled = localStorage.getItem('stagvault_wikimedia_enabled');
            if (wikimediaEnabled !== null) {
                this.apiProviders.wikimedia.enabled = wikimediaEnabled === 'true';
            }
        } catch (e) {
            console.error('Failed to load API keys:', e);
        }
    }

    loadApiCache() {
        try {
            const stored = localStorage.getItem('stagvault_api_cache');
            if (stored) {
                const cacheData = JSON.parse(stored);
                const now = Date.now();
                // Load only non-expired entries
                for (const [url, entry] of Object.entries(cacheData)) {
                    if (entry.expires > now) {
                        this.apiCache.set(url, entry);
                    }
                }
            }
        } catch (e) {
            console.error('Failed to load API cache:', e);
        }
    }

    saveApiCache() {
        try {
            const cacheObj = {};
            const now = Date.now();
            // Only save non-expired entries, limit to 100 most recent
            const entries = Array.from(this.apiCache.entries())
                .filter(([, entry]) => entry.expires > now)
                .sort((a, b) => b[1].timestamp - a[1].timestamp)
                .slice(0, 100);

            for (const [url, entry] of entries) {
                cacheObj[url] = entry;
            }
            localStorage.setItem('stagvault_api_cache', JSON.stringify(cacheObj));
        } catch (e) {
            // localStorage might be full, clear old cache
            console.error('Failed to save API cache:', e);
            try {
                localStorage.removeItem('stagvault_api_cache');
            } catch {}
        }
    }

    getCachedApiResponse(url) {
        const entry = this.apiCache.get(url);
        if (entry && entry.expires > Date.now()) {
            return entry.data;
        }
        // Remove expired entry
        if (entry) {
            this.apiCache.delete(url);
        }
        return null;
    }

    setCachedApiResponse(url, data) {
        const entry = {
            data,
            timestamp: Date.now(),
            expires: Date.now() + this.API_CACHE_TTL
        };
        this.apiCache.set(url, entry);
        // Debounce cache saves to avoid excessive writes
        if (this.cacheSaveTimer) clearTimeout(this.cacheSaveTimer);
        this.cacheSaveTimer = setTimeout(() => this.saveApiCache(), 2000);
    }

    saveApiKeys() {
        try {
            const keys = {};
            for (const [provider, config] of Object.entries(this.apiProviders)) {
                if (provider !== 'wikimedia') {
                    keys[provider] = {
                        apiKey: config.apiKey,
                        enabled: config.enabled
                    };
                }
            }
            localStorage.setItem('stagvault_api_keys', JSON.stringify(keys));
            localStorage.setItem('stagvault_wikimedia_enabled', this.apiProviders.wikimedia.enabled);
        } catch (e) {
            console.error('Failed to save API keys:', e);
        }
    }

    saveApiKey(provider, value) {
        if (!this.apiProviders[provider]) return;

        const trimmedValue = value.trim();
        this.apiProviders[provider].apiKey = trimmedValue || null;

        // Auto-enable if key is provided
        if (trimmedValue) {
            this.apiProviders[provider].enabled = true;
            const enabledToggle = document.getElementById(`${provider}-enabled`);
            if (enabledToggle) enabledToggle.checked = true;
        }

        this.saveApiKeys();
        this.updateProviderStatus(provider);

        // Refresh sidebar to show new API source and licenses
        this.addApiSourcesToTree();
        this.renderSourcesTree();
        this.renderLicenses();
    }

    toggleProvider(provider, enabled) {
        if (!this.apiProviders[provider]) return;

        this.apiProviders[provider].enabled = enabled;
        this.saveApiKeys();
        this.updateProviderStatus(provider);

        // Refresh sidebar to show/hide API sources and licenses
        this.addApiSourcesToTree();
        this.renderSourcesTree();
        this.renderLicenses();
    }

    updateProviderStatus(provider) {
        const statusEl = document.getElementById(`${provider}-status`);
        if (!statusEl) return;

        const config = this.apiProviders[provider];
        const isActive = config.enabled && (provider === 'wikimedia' || config.apiKey);

        statusEl.textContent = isActive ? 'Active' : 'Inactive';
        statusEl.className = `api-provider-status ${isActive ? 'active' : 'inactive'}`;
    }

    openSettings() {
        // Update UI with current values
        for (const [provider, config] of Object.entries(this.apiProviders)) {
            const keyInput = document.getElementById(`${provider}-key`);
            const enabledToggle = document.getElementById(`${provider}-enabled`);

            if (keyInput && config.apiKey) {
                keyInput.value = config.apiKey;
            }
            if (enabledToggle) {
                enabledToggle.checked = config.enabled;
            }

            this.updateProviderStatus(provider);
        }

        document.getElementById('settingsModal').classList.add('active');
    }

    closeSettings() {
        document.getElementById('settingsModal').classList.remove('active');
    }

    clearAllApiKeys() {
        for (const provider of Object.keys(this.apiProviders)) {
            if (provider !== 'wikimedia') {
                this.apiProviders[provider].apiKey = null;
                this.apiProviders[provider].enabled = false;

                const keyInput = document.getElementById(`${provider}-key`);
                const enabledToggle = document.getElementById(`${provider}-enabled`);
                if (keyInput) keyInput.value = '';
                if (enabledToggle) enabledToggle.checked = false;
            }
            this.updateProviderStatus(provider);
        }

        localStorage.removeItem('stagvault_api_keys');
        this.showToast('API keys cleared');
    }

    parseBulkApiKeys(text) {
        if (!text || text.trim().length < 10) return;

        // Map of env var names to provider IDs
        const keyMap = {
            'PEXELS_API_KEY': 'pexels',
            'PEXELS_KEY': 'pexels',
            'PIXABAY_API_KEY': 'pixabay',
            'PIXABAY_KEY': 'pixabay',
            'UNSPLASH_API_KEY': 'unsplash',
            'UNSPLASH_ACCESS_KEY': 'unsplash',
            'UNSPLASH_KEY': 'unsplash'
        };

        let foundAny = false;

        // Parse each line
        const lines = text.split(/[\n\r]+/);
        for (const line of lines) {
            // Match KEY=value or KEY = value patterns
            const match = line.match(/^\s*([A-Z_]+)\s*=\s*(.+?)\s*$/);
            if (match) {
                const [, envKey, value] = match;
                const provider = keyMap[envKey];

                if (provider && value) {
                    this.apiProviders[provider].apiKey = value;
                    this.apiProviders[provider].enabled = true;

                    // Update UI
                    const keyInput = document.getElementById(`${provider}-key`);
                    const enabledToggle = document.getElementById(`${provider}-enabled`);
                    if (keyInput) keyInput.value = value;
                    if (enabledToggle) enabledToggle.checked = true;

                    this.updateProviderStatus(provider);
                    foundAny = true;
                }
            }
        }

        if (foundAny) {
            this.saveApiKeys();
            // Clear the textarea after successful import
            const textarea = document.getElementById('bulkApiKeys');
            if (textarea) textarea.value = '';
            this.showToast('API keys imported!');
        }
    }

    // Get list of enabled API providers
    getEnabledProviders() {
        return Object.entries(this.apiProviders)
            .filter(([id, config]) => config.enabled && (id === 'wikimedia' || config.apiKey))
            .map(([id]) => id);
    }

    // ==========================================
    // API Search Methods
    // ==========================================

    async searchPexels(query, page = 1, perPage = 20) {
        const config = this.apiProviders.pexels;
        if (!config.apiKey || !config.enabled) return [];

        const url = `${config.baseUrl}/search?query=${encodeURIComponent(query)}&page=${page}&per_page=${perPage}`;

        // Check cache first
        const cached = this.getCachedApiResponse(url);
        if (cached) {
            return cached;
        }

        try {
            const response = await fetch(url, {
                headers: { 'Authorization': config.apiKey }
            });

            if (!response.ok) throw new Error(`Pexels API error: ${response.status}`);

            // Track rate limit
            const remaining = response.headers.get('X-Ratelimit-Remaining');
            if (remaining) config.rateLimit.remaining = parseInt(remaining);

            const data = await response.json();

            const results = (data.photos || []).map(photo => ({
                id: `pexels-${photo.id}`,
                n: photo.alt || `Photo ${photo.id}`,
                s: 'pexels',
                t: ['photo', 'pexels'],
                p: photo.src.small,
                l: 'Pexels License',
                _apiItem: true,
                _original: photo.src.original,
                _width: photo.width,
                _height: photo.height,
                _photographer: photo.photographer,
                _photographerUrl: photo.photographer_url
            }));

            // Cache the results
            this.setCachedApiResponse(url, results);
            return results;
        } catch (error) {
            console.error('Pexels search failed:', error);
            return [];
        }
    }

    async searchPixabay(query, page = 1, perPage = 20) {
        const config = this.apiProviders.pixabay;
        if (!config.apiKey || !config.enabled) return [];

        const url = `${config.baseUrl}/?key=${encodeURIComponent(config.apiKey)}&q=${encodeURIComponent(query)}&page=${page}&per_page=${perPage}&image_type=photo`;

        // Check cache first (use URL without key for cache key)
        const cacheKey = `pixabay:${query}:${page}:${perPage}`;
        const cached = this.getCachedApiResponse(cacheKey);
        if (cached) {
            return cached;
        }

        try {
            const response = await fetch(url);

            if (!response.ok) throw new Error(`Pixabay API error: ${response.status}`);

            // Track rate limit from headers
            const remaining = response.headers.get('X-RateLimit-Remaining');
            if (remaining) config.rateLimit.remaining = parseInt(remaining);

            const data = await response.json();

            const results = (data.hits || []).map(image => ({
                id: `pixabay-${image.id}`,
                n: image.tags || `Image ${image.id}`,
                s: 'pixabay',
                t: (image.tags || '').split(',').map(t => t.trim()).filter(Boolean),
                p: image.previewURL,
                l: 'Pixabay License',
                _apiItem: true,
                // Use webformatURL (640px) - largeImageURL blocks hotlinking
                _original: image.webformatURL,
                _width: image.webformatWidth || image.imageWidth,
                _height: image.webformatHeight || image.imageHeight,
                _fullWidth: image.imageWidth,
                _fullHeight: image.imageHeight,
                _user: image.user,
                _userUrl: `https://pixabay.com/users/${image.user}-${image.user_id}/`,
                _pageUrl: image.pageURL
            }));

            // Cache the results
            this.setCachedApiResponse(cacheKey, results);
            return results;
        } catch (error) {
            console.error('Pixabay search failed:', error);
            return [];
        }
    }

    async searchUnsplash(query, page = 1, perPage = 20) {
        const config = this.apiProviders.unsplash;
        if (!config.apiKey || !config.enabled) return [];

        const url = `${config.baseUrl}/search/photos?query=${encodeURIComponent(query)}&page=${page}&per_page=${perPage}`;

        // Check cache first
        const cached = this.getCachedApiResponse(url);
        if (cached) {
            return cached;
        }

        try {
            const response = await fetch(url, {
                headers: { 'Authorization': `Client-ID ${config.apiKey}` }
            });

            if (!response.ok) throw new Error(`Unsplash API error: ${response.status}`);

            // Track rate limit
            const remaining = response.headers.get('X-Ratelimit-Remaining');
            if (remaining) config.rateLimit.remaining = parseInt(remaining);

            const data = await response.json();

            const results = (data.results || []).map(photo => ({
                id: `unsplash-${photo.id}`,
                n: photo.alt_description || photo.description || `Photo by ${photo.user.name}`,
                s: 'unsplash',
                t: (photo.tags || []).map(t => t.title).filter(Boolean),
                p: photo.urls.small,
                l: 'Unsplash License',
                _apiItem: true,
                _original: photo.urls.full,
                _width: photo.width,
                _height: photo.height,
                _photographer: photo.user.name,
                _photographerUrl: photo.user.links.html,
                _downloadUrl: photo.links.download
            }));

            // Cache the results
            this.setCachedApiResponse(url, results);
            return results;
        } catch (error) {
            console.error('Unsplash search failed:', error);
            return [];
        }
    }

    async searchWikimedia(query, limit = 20) {
        const config = this.apiProviders.wikimedia;
        if (!config.enabled) return [];

        // Use MediaWiki API to search for images
        const params = new URLSearchParams({
            action: 'query',
            format: 'json',
            origin: '*',
            generator: 'search',
            gsrsearch: `${query} filetype:bitmap|drawing`,
            gsrlimit: limit,
            gsrnamespace: '6', // File namespace
            prop: 'imageinfo',
            iiprop: 'url|extmetadata|size',
            iiurlwidth: 800  // Request larger thumbnail (avoids CORS issues with direct URLs)
        });

        const url = `${config.baseUrl}?${params}`;

        // Check cache first
        const cached = this.getCachedApiResponse(url);
        if (cached) {
            return cached;
        }

        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error(`Wikimedia API error: ${response.status}`);

            const data = await response.json();
            const pages = data.query?.pages || {};

            const results = Object.values(pages)
                .filter(page => page.imageinfo && page.imageinfo[0])
                .map(page => {
                    const info = page.imageinfo[0];
                    const meta = info.extmetadata || {};
                    const title = page.title.replace(/^File:/, '').replace(/\.[^.]+$/, '');

                    // thumburl at 800px is the best balance for preview
                    // Direct info.url often has CORS issues
                    const previewUrl = info.thumburl || info.url;
                    return {
                        id: `wikimedia-${page.pageid}`,
                        n: meta.ObjectName?.value || title,
                        s: 'wikimedia',
                        t: ['wikimedia', 'commons'],
                        p: previewUrl,
                        l: meta.LicenseShortName?.value || 'Wikimedia Commons',
                        _apiItem: true,
                        _original: previewUrl,  // Use thumbnail - direct URLs have CORS issues
                        _directUrl: info.url,   // Keep original for download
                        _width: info.thumbwidth || info.width,
                        _height: info.thumbheight || info.height,
                        _fullWidth: info.width,
                        _fullHeight: info.height,
                        _description: meta.ImageDescription?.value,
                        _artist: meta.Artist?.value,
                        _pageUrl: `https://commons.wikimedia.org/wiki/File:${encodeURIComponent(page.title.replace(/^File:/, ''))}`
                    };
                });

            // Cache the results
            this.setCachedApiResponse(url, results);
            return results;
        } catch (error) {
            console.error('Wikimedia search failed:', error);
            return [];
        }
    }

    async searchApiProviders(query) {
        const enabledProviders = this.getEnabledProviders();
        if (enabledProviders.length === 0) return [];

        const searches = [];

        if (enabledProviders.includes('pexels')) {
            searches.push(this.searchPexels(query));
        }
        if (enabledProviders.includes('pixabay')) {
            searches.push(this.searchPixabay(query));
        }
        if (enabledProviders.includes('unsplash')) {
            searches.push(this.searchUnsplash(query));
        }
        if (enabledProviders.includes('wikimedia')) {
            searches.push(this.searchWikimedia(query));
        }

        const results = await Promise.all(searches);
        return results.flat();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.stagvault = new StagVault();
});
