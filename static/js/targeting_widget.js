/**
 * Targeting Widget - Visual selector for product targeting configuration
 *
 * Usage:
 *   const widget = new TargetingWidget('tenant_id');
 *   // Widget will initialize automatically and populate #targeting-data hidden field
 */

class TargetingWidget {
    constructor(tenantId, containerId = 'targeting-widget') {
        this.tenantId = tenantId;
        this.container = document.getElementById(containerId);
        this.selectedTargeting = {
            key_value_pairs: {},
            geography: {
                countries: []
            },
            device_platform: {
                device_types: []
            },
            audiences: []
        };

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
        const response = await fetch(`/api/tenant/${this.tenantId}/targeting/all`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        this.targetingData = await response.json();
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
        keysList.innerHTML = keys.map(key => `
            <div class="kv-key-item" data-key-id="${key.id}">
                <strong>${key.display_name || key.name}</strong>
                ${key.description ? `<small>${key.description}</small>` : ''}
            </div>
        `).join('');
    }

    async loadValuesForKey(keyId) {
        const valuesContainer = document.getElementById('values-container');
        valuesContainer.innerHTML = '<p class="loading">Loading values...</p>';

        try {
            const response = await fetch(`/api/tenant/${this.tenantId}/targeting/values/${keyId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.renderValuesList(keyId, data.values || []);
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
            <div class="kv-values-grid">
                ${values.map(val => `
                    <label class="value-checkbox">
                        <input type="checkbox"
                               data-key-id="${keyId}"
                               data-value-id="${val.id}"
                               data-value-name="${val.name}"
                               ${this.isValueSelected(keyId, val.id) ? 'checked' : ''}>
                        <span>${val.display_name || val.name}</span>
                    </label>
                `).join('')}
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

        // Key selection
        this.container.addEventListener('click', async (e) => {
            if (e.target.closest('.kv-key-item')) {
                const keyId = e.target.closest('.kv-key-item').dataset.keyId;
                await this.loadValuesForKey(keyId);
            }
        });

        // Value selection
        this.container.addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                this.handleCheckboxChange(e.target);
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

    handleCheckboxChange(checkbox) {
        const keyId = checkbox.dataset.keyId;
        const valueId = checkbox.dataset.valueId;
        const valueName = checkbox.dataset.valueName;

        if (keyId && valueId) {
            // Key-value pair
            if (!this.selectedTargeting.key_value_pairs[keyId]) {
                this.selectedTargeting.key_value_pairs[keyId] = [];
            }

            if (checkbox.checked) {
                if (!this.selectedTargeting.key_value_pairs[keyId].includes(valueId)) {
                    this.selectedTargeting.key_value_pairs[keyId].push(valueId);
                }
            } else {
                this.selectedTargeting.key_value_pairs[keyId] =
                    this.selectedTargeting.key_value_pairs[keyId].filter(id => id !== valueId);

                if (this.selectedTargeting.key_value_pairs[keyId].length === 0) {
                    delete this.selectedTargeting.key_value_pairs[keyId];
                }
            }
        }

        this.updateHiddenField();
        this.updateSummary();
    }

    isValueSelected(keyId, valueId) {
        return this.selectedTargeting.key_value_pairs[keyId]?.includes(valueId) || false;
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
        const values = this.container.querySelectorAll('.value-checkbox');
        const lowerQuery = query.toLowerCase();

        values.forEach(val => {
            const text = val.textContent.toLowerCase();
            val.style.display = text.includes(lowerQuery) ? '' : 'none';
        });
    }

    updateHiddenField() {
        // Only include non-empty targeting
        const cleanTargeting = {};

        if (Object.keys(this.selectedTargeting.key_value_pairs).length > 0) {
            cleanTargeting.key_value_pairs = this.selectedTargeting.key_value_pairs;
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
        const tagsContainer = document.getElementById('targeting-tags');

        const hasSelection = Object.keys(this.selectedTargeting.key_value_pairs).length > 0;

        if (!hasSelection) {
            summary.style.display = 'none';
            return;
        }

        summary.style.display = 'block';

        // Build tags HTML
        const tags = [];
        for (const [keyId, valueIds] of Object.entries(this.selectedTargeting.key_value_pairs)) {
            valueIds.forEach(valueId => {
                tags.push(`<span class="targeting-tag">${keyId}: ${valueId}</span>`);
            });
        }

        tagsContainer.innerHTML = tags.join('');
    }
}

// Export for use in templates
window.TargetingWidget = TargetingWidget;
