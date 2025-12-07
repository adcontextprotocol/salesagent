/**
 * Targeting Widget - Custom key-value targeting selector
 *
 * Features:
 * - OR/AND operator support between different keys
 * - Include/Exclude toggle for values
 * - Search functionality for keys and values
 *
 * Data Structure:
 * {
 *   key_value_pairs: {
 *     include: { "key_id": ["value1", "value2"] },  // Values to include (OR within same key)
 *     exclude: { "key_id": ["value3"] },             // Values to exclude
 *     operator: "AND"  // "AND" or "OR" - how to combine different keys
 *   }
 * }
 */

class TargetingWidget {
    constructor(tenantId, containerId = 'targeting-widget', scriptRoot = '') {
        this.tenantId = tenantId;
        this.container = document.getElementById(containerId);
        this.scriptRoot = scriptRoot;
        this.selectedTargeting = {
            key_value_pairs: {
                include: {},
                exclude: {},
                operator: 'AND'
            }
        };
        this.currentKeyId = null;
        this.keyMetadata = {};
        this.valueMetadata = {};  // Cache value names: { keyId: { valueId: displayName } }

        if (!this.container) {
            console.error(`Targeting widget container '#${containerId}' not found`);
            return;
        }

        this.init();
    }

    async init() {
        try {
            await this.loadTargetingData();
            this.loadExistingTargeting();  // Load from hidden field if present
            this.render();
            this.attachEventListeners();
            this.updateHiddenField();
        } catch (error) {
            console.error('Error initializing targeting widget:', error);
            this.container.innerHTML = `<div class="alert alert-error">Failed to load targeting options: ${error.message}</div>`;
        }
    }

    /**
     * Load existing targeting from the hidden form field.
     * Handles both legacy format (keyId: value) and enhanced format (include/exclude/operator).
     */
    loadExistingTargeting() {
        const hiddenField = document.getElementById('targeting-data');
        if (!hiddenField || !hiddenField.value || hiddenField.value === '{}') {
            return;
        }

        try {
            const existingData = JSON.parse(hiddenField.value);
            const kvPairs = existingData.key_value_pairs;

            if (!kvPairs || Object.keys(kvPairs).length === 0) {
                return;
            }

            // Check if this is enhanced format (has include/exclude keys)
            if ('include' in kvPairs || 'exclude' in kvPairs) {
                // Enhanced format - use directly
                this.selectedTargeting.key_value_pairs = {
                    include: kvPairs.include || {},
                    exclude: kvPairs.exclude || {},
                    operator: kvPairs.operator || 'AND'
                };
                console.log('[TargetingWidget] Loaded enhanced format targeting:', this.selectedTargeting);
            } else {
                // Legacy format: { keyId: value } - convert to enhanced format as includes
                // Legacy format values are strings, new format uses arrays
                const include = {};
                for (const [keyId, value] of Object.entries(kvPairs)) {
                    // Legacy format has single value as string, convert to array
                    if (typeof value === 'string') {
                        include[keyId] = [value];
                    } else if (Array.isArray(value)) {
                        include[keyId] = value;
                    }
                }
                this.selectedTargeting.key_value_pairs = {
                    include: include,
                    exclude: {},
                    operator: 'AND'
                };
                console.log('[TargetingWidget] Converted legacy format to enhanced:', this.selectedTargeting);
            }

            // Pre-load value metadata for display names in summary
            // We need to fetch values for each key that has selections
            this.preloadValueMetadata();

        } catch (error) {
            console.error('[TargetingWidget] Error loading existing targeting:', error);
        }
    }

    /**
     * Pre-load value metadata for keys that have existing selections.
     * This ensures the summary can show value names instead of IDs.
     * Also handles legacy format by converting value names to IDs.
     */
    async preloadValueMetadata() {
        const kvPairs = this.selectedTargeting.key_value_pairs;
        const keyIds = new Set([
            ...Object.keys(kvPairs.include || {}),
            ...Object.keys(kvPairs.exclude || {})
        ]);

        for (const keyId of keyIds) {
            if (!this.valueMetadata[keyId]) {
                try {
                    const url = `${this.scriptRoot}/api/tenant/${this.tenantId}/targeting/values/${keyId}`;
                    const response = await fetch(url, { credentials: 'same-origin' });
                    if (response.ok) {
                        const data = await response.json();
                        this.valueMetadata[keyId] = {};

                        // Build both ID->name and name->ID mappings
                        const nameToId = {};
                        (data.values || []).forEach(val => {
                            this.valueMetadata[keyId][val.id] = val.display_name || val.name || val.id;
                            // Also map by name for legacy format support
                            if (val.name) {
                                nameToId[val.name] = val.id;
                            }
                        });

                        // Convert legacy value names to IDs if needed
                        // Legacy format stores value names, new format stores value IDs
                        const convertValues = (values) => {
                            return values.map(v => {
                                // If value is a name (not numeric), try to find its ID
                                if (!String(v).match(/^\d+$/) && nameToId[v]) {
                                    console.log(`[TargetingWidget] Converted legacy value name "${v}" to ID "${nameToId[v]}"`);
                                    return nameToId[v];
                                }
                                return v;
                            });
                        };

                        if (kvPairs.include[keyId]) {
                            kvPairs.include[keyId] = convertValues(kvPairs.include[keyId]);
                        }
                        if (kvPairs.exclude && kvPairs.exclude[keyId]) {
                            kvPairs.exclude[keyId] = convertValues(kvPairs.exclude[keyId]);
                        }
                    }
                } catch (error) {
                    console.warn(`[TargetingWidget] Failed to preload values for key ${keyId}:`, error);
                }
            }
        }

        // Re-render key list to show selection badges
        const keys = this.targetingData.custom_targeting_keys || [];
        this.renderKeysList(keys);

        // Re-render summary now that we have value names
        this.updateSummary();
    }

    async loadTargetingData() {
        const url = `${this.scriptRoot}/api/tenant/${this.tenantId}/targeting/all`;
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        this.targetingData = await response.json();

        // API returns 'customKeys', normalize to 'custom_targeting_keys'
        if (this.targetingData.customKeys && !this.targetingData.custom_targeting_keys) {
            this.targetingData.custom_targeting_keys = this.targetingData.customKeys;
        }

        // Cache key metadata for later use
        (this.targetingData.custom_targeting_keys || []).forEach(key => {
            this.keyMetadata[key.id] = {
                name: key.name,
                display_name: key.display_name || key.name
            };
        });
    }

    render() {
        const keys = this.targetingData.custom_targeting_keys || [];

        if (keys.length === 0) {
            this.container.innerHTML = '<p class="empty-state">No custom targeting keys available. Sync inventory to load targeting options.</p>';
            return;
        }

        this.container.innerHTML = `
            <div class="kv-operator-toggle">
                <span class="operator-label">Combine keys with:</span>
                <div class="operator-buttons">
                    <button type="button" class="operator-btn ${this.selectedTargeting.key_value_pairs.operator === 'AND' ? 'active' : ''}" data-operator="AND">
                        AND <small>(match all)</small>
                    </button>
                    <button type="button" class="operator-btn ${this.selectedTargeting.key_value_pairs.operator === 'OR' ? 'active' : ''}" data-operator="OR">
                        OR <small>(match any)</small>
                    </button>
                </div>
            </div>
            <div class="kv-selector">
                <div class="kv-keys">
                    <h5>Keys</h5>
                    <input type="search" id="key-search" placeholder="Search keys..." class="search-input">
                    <div class="kv-keys-list" id="keys-list"></div>
                </div>
                <div class="kv-values">
                    <h5>Values</h5>
                    <div id="values-container">
                        <p class="empty-state">Select a key to view available values</p>
                    </div>
                </div>
            </div>
            <div class="selected-summary" id="targeting-summary" style="display: none;">
                <h5>Selected Targeting:</h5>
                <div class="summary-operator" id="summary-operator"></div>
                <div class="selected-tags" id="targeting-tags"></div>
            </div>
        `;

        this.renderKeysList(keys);
    }

    renderKeysList(keys) {
        const keysList = document.getElementById('keys-list');
        keysList.innerHTML = keys.map(key => {
            const hasInclude = this.selectedTargeting.key_value_pairs.include[key.id]?.length > 0;
            const hasExclude = this.selectedTargeting.key_value_pairs.exclude[key.id]?.length > 0;
            const selectedClass = (hasInclude || hasExclude) ? 'has-selections' : '';

            return `
                <div class="kv-key-item ${selectedClass}" data-key-id="${key.id}">
                    <strong>${key.display_name || key.name}</strong>
                    ${key.description ? `<small>${key.description}</small>` : ''}
                    ${hasInclude || hasExclude ? `
                        <span class="selection-badge">
                            ${hasInclude ? `<span class="badge-include">${this.selectedTargeting.key_value_pairs.include[key.id].length} included</span>` : ''}
                            ${hasExclude ? `<span class="badge-exclude">${this.selectedTargeting.key_value_pairs.exclude[key.id].length} excluded</span>` : ''}
                        </span>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    async loadValuesForKey(keyId) {
        const valuesContainer = document.getElementById('values-container');
        valuesContainer.innerHTML = '<p class="loading">Loading values...</p>';
        this.currentKeyId = keyId;

        // Highlight selected key
        document.querySelectorAll('.kv-key-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.keyId === keyId);
        });

        try {
            const url = `${this.scriptRoot}/api/tenant/${this.tenantId}/targeting/values/${keyId}`;
            const response = await fetch(url, { credentials: 'same-origin' });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.currentValues = data.values || [];

            // Cache value metadata for display names in summary
            if (!this.valueMetadata[keyId]) {
                this.valueMetadata[keyId] = {};
            }
            this.currentValues.forEach(val => {
                this.valueMetadata[keyId][val.id] = val.display_name || val.name || val.id;
            });

            this.renderValuesList(keyId, this.currentValues);
        } catch (error) {
            valuesContainer.innerHTML = `<p class="error-state">Failed to load values: ${error.message}</p>`;
        }
    }

    renderValuesList(keyId, values) {
        const valuesContainer = document.getElementById('values-container');

        if (values.length === 0) {
            valuesContainer.innerHTML = '<p class="empty-state">No values available for this key</p>';
            return;
        }

        valuesContainer.innerHTML = `
            <input type="search" id="value-search" placeholder="Search values..." class="search-input">
            <div class="values-legend">
                <span class="legend-item"><span class="legend-color include"></span> Include</span>
                <span class="legend-item"><span class="legend-color exclude"></span> Exclude</span>
            </div>
            <div class="kv-values-grid">
                ${values.map(val => {
                    const isIncluded = this.isValueIncluded(keyId, val.id);
                    const isExcluded = this.isValueExcluded(keyId, val.id);
                    const stateClass = isIncluded ? 'included' : (isExcluded ? 'excluded' : '');

                    return `
                        <div class="value-item ${stateClass}" data-key-id="${keyId}" data-value-id="${val.id}" data-value-name="${val.name}">
                            <span class="value-name">${val.display_name || val.name}</span>
                            <div class="value-actions">
                                <button type="button" class="action-btn include-btn ${isIncluded ? 'active' : ''}"
                                        data-action="include" title="Include this value">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <polyline points="20 6 9 17 4 12"></polyline>
                                    </svg>
                                </button>
                                <button type="button" class="action-btn exclude-btn ${isExcluded ? 'active' : ''}"
                                        data-action="exclude" title="Exclude this value">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <line x1="18" y1="6" x2="6" y2="18"></line>
                                        <line x1="6" y1="6" x2="18" y2="18"></line>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    attachEventListeners() {
        // Operator toggle
        this.container.addEventListener('click', (e) => {
            const operatorBtn = e.target.closest('.operator-btn');
            if (operatorBtn) {
                const operator = operatorBtn.dataset.operator;
                this.selectedTargeting.key_value_pairs.operator = operator;

                this.container.querySelectorAll('.operator-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.operator === operator);
                });

                this.updateHiddenField();
                this.updateSummary();
            }
        });

        // Key selection
        this.container.addEventListener('click', async (e) => {
            const keyItem = e.target.closest('.kv-key-item');
            if (keyItem && !e.target.closest('.action-btn')) {
                const keyId = keyItem.dataset.keyId;
                await this.loadValuesForKey(keyId);
            }
        });

        // Value action buttons (include/exclude)
        this.container.addEventListener('click', (e) => {
            const actionBtn = e.target.closest('.action-btn');
            if (actionBtn) {
                const valueItem = actionBtn.closest('.value-item');
                const keyId = valueItem.dataset.keyId;
                const valueId = valueItem.dataset.valueId;
                const action = actionBtn.dataset.action;

                this.handleValueAction(keyId, valueId, action);
            }
        });

        // Search
        this.container.addEventListener('input', (e) => {
            if (e.target.id === 'key-search') {
                this.filterKeys(e.target.value);
            } else if (e.target.id === 'value-search') {
                this.filterValues(e.target.value);
            }
        });
    }

    handleValueAction(keyId, valueId, action) {
        const include = this.selectedTargeting.key_value_pairs.include;
        const exclude = this.selectedTargeting.key_value_pairs.exclude;

        if (!include[keyId]) include[keyId] = [];
        if (!exclude[keyId]) exclude[keyId] = [];

        const isCurrentlyIncluded = include[keyId].includes(valueId);
        const isCurrentlyExcluded = exclude[keyId].includes(valueId);

        if (action === 'include') {
            if (isCurrentlyIncluded) {
                include[keyId] = include[keyId].filter(id => id !== valueId);
            } else {
                include[keyId].push(valueId);
                exclude[keyId] = exclude[keyId].filter(id => id !== valueId);
            }
        } else if (action === 'exclude') {
            if (isCurrentlyExcluded) {
                exclude[keyId] = exclude[keyId].filter(id => id !== valueId);
            } else {
                exclude[keyId].push(valueId);
                include[keyId] = include[keyId].filter(id => id !== valueId);
            }
        }

        if (include[keyId].length === 0) delete include[keyId];
        if (exclude[keyId].length === 0) delete exclude[keyId];

        this.updateValueItemState(keyId, valueId);
        this.updateKeySelectionBadges();
        this.updateHiddenField();
        this.updateSummary();
    }

    updateValueItemState(keyId, valueId) {
        const valueItem = this.container.querySelector(`.value-item[data-key-id="${keyId}"][data-value-id="${valueId}"]`);
        if (!valueItem) return;

        const isIncluded = this.isValueIncluded(keyId, valueId);
        const isExcluded = this.isValueExcluded(keyId, valueId);

        valueItem.classList.remove('included', 'excluded');
        if (isIncluded) valueItem.classList.add('included');
        if (isExcluded) valueItem.classList.add('excluded');

        valueItem.querySelector('.include-btn').classList.toggle('active', isIncluded);
        valueItem.querySelector('.exclude-btn').classList.toggle('active', isExcluded);
    }

    updateKeySelectionBadges() {
        const keys = this.targetingData.custom_targeting_keys || [];
        this.renderKeysList(keys);

        if (this.currentKeyId) {
            const currentKeyItem = this.container.querySelector(`.kv-key-item[data-key-id="${this.currentKeyId}"]`);
            if (currentKeyItem) {
                currentKeyItem.classList.add('selected');
            }
        }
    }

    isValueIncluded(keyId, valueId) {
        return this.selectedTargeting.key_value_pairs.include[keyId]?.includes(valueId) || false;
    }

    isValueExcluded(keyId, valueId) {
        return this.selectedTargeting.key_value_pairs.exclude[keyId]?.includes(valueId) || false;
    }

    filterKeys(query) {
        const keys = this.container.querySelectorAll('.kv-key-item');
        const lowerQuery = query.toLowerCase();

        keys.forEach(key => {
            const text = key.textContent.toLowerCase();
            key.style.display = text.includes(lowerQuery) ? '' : 'none';
        });
    }

    filterValues(query) {
        const values = this.container.querySelectorAll('.value-item');
        const lowerQuery = query.toLowerCase();

        values.forEach(val => {
            const text = val.querySelector('.value-name').textContent.toLowerCase();
            val.style.display = text.includes(lowerQuery) ? '' : 'none';
        });
    }

    updateHiddenField() {
        const cleanTargeting = {};

        const kvPairs = this.selectedTargeting.key_value_pairs;
        const hasInclude = Object.keys(kvPairs.include).length > 0;
        const hasExclude = Object.keys(kvPairs.exclude).length > 0;

        if (hasInclude || hasExclude) {
            cleanTargeting.key_value_pairs = {
                include: kvPairs.include,
                exclude: kvPairs.exclude,
                operator: kvPairs.operator
            };
        }

        const hiddenField = document.getElementById('targeting-data');
        if (hiddenField) {
            hiddenField.value = Object.keys(cleanTargeting).length > 0 ? JSON.stringify(cleanTargeting) : '';
        }
    }

    updateSummary() {
        const summary = document.getElementById('targeting-summary');
        const operatorDisplay = document.getElementById('summary-operator');
        const tagsContainer = document.getElementById('targeting-tags');

        const kvPairs = this.selectedTargeting.key_value_pairs;
        const hasInclude = Object.keys(kvPairs.include).length > 0;
        const hasExclude = Object.keys(kvPairs.exclude).length > 0;

        if (!hasInclude && !hasExclude) {
            summary.style.display = 'none';
            return;
        }

        summary.style.display = 'block';

        operatorDisplay.innerHTML = `
            <span class="operator-display">
                Keys combined with: <strong>${kvPairs.operator}</strong>
            </span>
        `;

        const tags = [];

        for (const [keyId, valueIds] of Object.entries(kvPairs.include)) {
            const keyName = this.keyMetadata[keyId]?.display_name || keyId;
            // Get display names for values
            const valueNames = valueIds.map(vid =>
                this.valueMetadata[keyId]?.[vid] || vid
            );
            const valuesText = valueNames.length > 1
                ? valueNames.join(' or ')
                : valueNames[0];
            tags.push(`
                <span class="targeting-tag include-tag">
                    <strong>Include:</strong> ${keyName} = ${valuesText}
                </span>
            `);
        }

        for (const [keyId, valueIds] of Object.entries(kvPairs.exclude)) {
            const keyName = this.keyMetadata[keyId]?.display_name || keyId;
            // Get display names for values
            const valueNames = valueIds.map(vid =>
                this.valueMetadata[keyId]?.[vid] || vid
            );
            const valuesText = valueNames.length > 1
                ? valueNames.join(' or ')
                : valueNames[0];
            tags.push(`
                <span class="targeting-tag exclude-tag">
                    <strong>Exclude:</strong> ${keyName} = ${valuesText}
                </span>
            `);
        }

        const operator = kvPairs.operator;
        tagsContainer.innerHTML = tags.join(`<span class="tag-operator">${operator}</span>`);
    }
}

window.TargetingWidget = TargetingWidget;
