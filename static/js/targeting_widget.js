/**
 * Targeting Widget - Visual selector for product targeting configuration
 *
 * Enhanced with:
 * - OR/AND operator support between different keys
 * - Include/Exclude toggle for values
 * - Improved search functionality
 *
 * Data Structure:
 * {
 *   key_value_pairs: {
 *     include: { "key_id": ["value1", "value2"] },  // Values to include (OR within same key)
 *     exclude: { "key_id": ["value3"] },             // Values to exclude
 *     operator: "AND"  // "AND" or "OR" - how to combine different keys
 *   }
 * }
 *
 * Usage:
 *   const widget = new TargetingWidget('tenant_id', 'targeting-widget', '/admin');
 *   // Widget will initialize automatically and populate #targeting-data hidden field
 */

class TargetingWidget {
    constructor(tenantId, containerId = 'targeting-widget', scriptRoot = '') {
        this.tenantId = tenantId;
        this.container = document.getElementById(containerId);
        this.scriptRoot = scriptRoot;  // Base path for URLs (e.g., '/admin' or '')
        this.selectedTargeting = {
            key_value_pairs: {
                include: {},
                exclude: {},
                operator: 'AND'
            },
            geography: {
                countries: []
            },
            device_platform: {
                device_types: []
            },
            audiences: []
        };
        this.currentKeyId = null;
        this.keyMetadata = {};  // Cache key metadata for display names

        if (!this.container) {
            console.error(`Targeting widget container '#${containerId}' not found`);
            return;
        }

        this.init();
    }

    async init() {
        try {
            // Load initial data
            await this.loadTargetingData();
            this.renderTabs();
            this.attachEventListeners();
            this.updateHiddenField();
        } catch (error) {
            console.error('Error initializing targeting widget:', error);
            this.container.innerHTML = `<div class="alert alert-error">Failed to load targeting options: ${error.message}</div>`;
        }
    }

    async loadTargetingData() {
        const url = `${this.scriptRoot}/api/tenant/${this.tenantId}/targeting/all`;
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        this.targetingData = await response.json();

        // Cache key metadata for later use
        (this.targetingData.custom_targeting_keys || []).forEach(key => {
            this.keyMetadata[key.id] = {
                name: key.name,
                display_name: key.display_name || key.name
            };
        });
    }

    renderTabs() {
        const tabsHTML = `
            <div class="targeting-tabs">
                <button class="targeting-tab active" data-tab="key-value">Custom Key-Value Pairs</button>
                <button class="targeting-tab" data-tab="geography">Geography</button>
                <button class="targeting-tab" data-tab="device">Device & Platform</button>
                <button class="targeting-tab" data-tab="audiences">Audiences</button>
            </div>
            <div class="targeting-tab-content">
                <div class="tab-pane active" id="tab-key-value"></div>
                <div class="tab-pane" id="tab-geography"></div>
                <div class="tab-pane" id="tab-device"></div>
                <div class="tab-pane" id="tab-audiences"></div>
            </div>
            <div class="selected-summary" id="targeting-summary" style="display: none;">
                <h5>Selected Targeting:</h5>
                <div class="summary-operator" id="summary-operator"></div>
                <div class="selected-tags" id="targeting-tags"></div>
            </div>
        `;
        this.container.innerHTML = tabsHTML;

        this.renderKeyValueTab();
        this.renderGeographyTab();
        this.renderDeviceTab();
        this.renderAudiencesTab();
    }

    renderKeyValueTab() {
        const keys = this.targetingData.custom_targeting_keys || [];
        const pane = document.getElementById('tab-key-value');

        if (keys.length === 0) {
            pane.innerHTML = '<p class="empty-state">No custom targeting keys available</p>';
            return;
        }

        pane.innerHTML = `
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

    renderGeographyTab() {
        const pane = document.getElementById('tab-geography');
        // Simplified for now - full implementation would have country selector
        pane.innerHTML = '<p class="info-message">Geography targeting coming soon</p>';
    }

    renderDeviceTab() {
        const pane = document.getElementById('tab-device');
        pane.innerHTML = `
            <div class="device-types">
                <h5>Device Types</h5>
                <label><input type="checkbox" value="DESKTOP"> Desktop</label>
                <label><input type="checkbox" value="MOBILE"> Mobile</label>
                <label><input type="checkbox" value="TABLET"> Tablet</label>
                <label><input type="checkbox" value="CONNECTED_TV"> Connected TV</label>
            </div>
        `;
    }

    renderAudiencesTab() {
        const audiences = this.targetingData.audiences || [];
        const pane = document.getElementById('tab-audiences');

        if (audiences.length === 0) {
            pane.innerHTML = '<p class="empty-state">No audiences available</p>';
            return;
        }

        pane.innerHTML = `
            <div class="audience-list">
                ${audiences.map(aud => `
                    <label class="audience-item">
                        <input type="checkbox" value="${aud.id}">
                        <div>
                            <strong>${aud.name}</strong>
                            ${aud.description ? `<small>${aud.description}</small>` : ''}
                        </div>
                    </label>
                `).join('')}
            </div>
        `;
    }

    attachEventListeners() {
        // Tab switching
        this.container.querySelectorAll('.targeting-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Operator toggle
        this.container.addEventListener('click', (e) => {
            const operatorBtn = e.target.closest('.operator-btn');
            if (operatorBtn) {
                const operator = operatorBtn.dataset.operator;
                this.selectedTargeting.key_value_pairs.operator = operator;

                // Update active button
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

    switchTab(tabName) {
        // Update active tab button
        this.container.querySelectorAll('.targeting-tab').forEach(t => t.classList.remove('active'));
        this.container.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update active pane
        this.container.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        this.container.querySelector(`#tab-${tabName}`).classList.add('active');
    }

    handleValueAction(keyId, valueId, action) {
        const include = this.selectedTargeting.key_value_pairs.include;
        const exclude = this.selectedTargeting.key_value_pairs.exclude;

        // Initialize arrays if needed
        if (!include[keyId]) include[keyId] = [];
        if (!exclude[keyId]) exclude[keyId] = [];

        const isCurrentlyIncluded = include[keyId].includes(valueId);
        const isCurrentlyExcluded = exclude[keyId].includes(valueId);

        if (action === 'include') {
            if (isCurrentlyIncluded) {
                // Toggle off
                include[keyId] = include[keyId].filter(id => id !== valueId);
            } else {
                // Add to include, remove from exclude
                include[keyId].push(valueId);
                exclude[keyId] = exclude[keyId].filter(id => id !== valueId);
            }
        } else if (action === 'exclude') {
            if (isCurrentlyExcluded) {
                // Toggle off
                exclude[keyId] = exclude[keyId].filter(id => id !== valueId);
            } else {
                // Add to exclude, remove from include
                exclude[keyId].push(valueId);
                include[keyId] = include[keyId].filter(id => id !== valueId);
            }
        }

        // Clean up empty arrays
        if (include[keyId].length === 0) delete include[keyId];
        if (exclude[keyId].length === 0) delete exclude[keyId];

        // Update UI
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
        // Re-render keys list to update badges
        const keys = this.targetingData.custom_targeting_keys || [];
        this.renderKeysList(keys);

        // Re-select current key
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
        // Build clean targeting object
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

        if (this.selectedTargeting.geography.countries.length > 0) {
            cleanTargeting.geography = this.selectedTargeting.geography;
        }

        if (this.selectedTargeting.device_platform.device_types.length > 0) {
            cleanTargeting.device_platform = this.selectedTargeting.device_platform;
        }

        if (this.selectedTargeting.audiences.length > 0) {
            cleanTargeting.audiences = this.selectedTargeting.audiences;
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

        // Show operator
        operatorDisplay.innerHTML = `
            <span class="operator-display">
                Keys combined with: <strong>${kvPairs.operator}</strong>
            </span>
        `;

        // Build tags HTML
        const tags = [];

        // Include tags
        for (const [keyId, valueIds] of Object.entries(kvPairs.include)) {
            const keyName = this.keyMetadata[keyId]?.display_name || keyId;
            const valuesText = valueIds.length > 1
                ? `(${valueIds.join(' OR ')})`
                : valueIds[0];
            tags.push(`
                <span class="targeting-tag include-tag">
                    <span class="tag-icon">+</span>
                    ${keyName} = ${valuesText}
                </span>
            `);
        }

        // Exclude tags
        for (const [keyId, valueIds] of Object.entries(kvPairs.exclude)) {
            const keyName = this.keyMetadata[keyId]?.display_name || keyId;
            const valuesText = valueIds.length > 1
                ? `(${valueIds.join(' OR ')})`
                : valueIds[0];
            tags.push(`
                <span class="targeting-tag exclude-tag">
                    <span class="tag-icon">-</span>
                    ${keyName} != ${valuesText}
                </span>
            `);
        }

        // Add operator between tags
        const operator = kvPairs.operator;
        tagsContainer.innerHTML = tags.join(`<span class="tag-operator">${operator}</span>`);
    }
}

// Export for use in templates
window.TargetingWidget = TargetingWidget;
