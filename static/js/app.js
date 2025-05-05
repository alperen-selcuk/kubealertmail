// Initialize the Feather icons
document.addEventListener('DOMContentLoaded', function() {
    feather.replace();
    
    // Set up auto-refresh
    initializeAutoRefresh();
    
    // Load the initial data
    refreshData();
    
    // Set up event listeners
    setupEventListeners();
});

// Charts
let nodeChart = null;
let podChart = null;

// Auto-refresh settings
let autoRefreshEnabled = true;
let refreshInterval = 30000; // 30 seconds
let refreshTimer = null;

// Store the current data
let currentData = {
    nodes: [],
    pods: [],
    alerts: []
};

function initializeAutoRefresh() {
    const autoRefreshSwitch = document.getElementById('autoRefreshSwitch');
    
    if (autoRefreshSwitch) {
        autoRefreshSwitch.checked = autoRefreshEnabled;
        
        autoRefreshSwitch.addEventListener('change', function() {
            autoRefreshEnabled = this.checked;
            
            if (autoRefreshEnabled) {
                startRefreshTimer();
            } else {
                stopRefreshTimer();
            }
        });
        
        if (autoRefreshEnabled) {
            startRefreshTimer();
        }
    }
}

function startRefreshTimer() {
    stopRefreshTimer();
    refreshTimer = setInterval(refreshData, refreshInterval);
}

function stopRefreshTimer() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

function setupEventListeners() {
    // Set up refresh buttons
    const refreshButtons = [
        'btn-refresh-nodes', 
        'btn-refresh-pods',
        'btn-refresh-node-list',
        'btn-refresh-pod-list'
    ];
    
    refreshButtons.forEach(id => {
        const button = document.getElementById(id);
        if (button) {
            button.addEventListener('click', refreshData);
        }
    });
    
    // Set up search inputs
    const nodeSearch = document.getElementById('node-search');
    if (nodeSearch) {
        nodeSearch.addEventListener('input', filterNodes);
    }
    
    const podSearch = document.getElementById('pod-search');
    if (podSearch) {
        podSearch.addEventListener('input', filterPods);
    }
    
    // Set up namespace filter
    const namespaceFilter = document.getElementById('namespace-filter');
    if (namespaceFilter) {
        namespaceFilter.addEventListener('change', filterPods);
    }
}

function refreshData() {
    // Show the refreshing indicator
    const refreshIndicator = document.getElementById('refresh-indicator');
    if (refreshIndicator) {
        refreshIndicator.classList.add('refreshing');
    }
    
    // Fetch the latest resource data
    fetch('/api/resources')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            currentData.nodes = data.nodes;
            currentData.pods = data.pods;
            updateDashboard(data);
            updateResourcesTables(data);
        })
        .catch(error => {
            console.error('Error fetching resource data:', error);
            updateStatusError(error.message);
        });
        
    // Fetch the latest alerts data
    fetch('/api/alerts?status=active')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            console.log('Alerts data:', data); // Debug log
            // Only update if data is in the correct format
            if (data.alerts && Array.isArray(data.alerts) && data.alerts.length > 0 && data.alerts[0].id) {
                currentData.alerts = data.alerts;
                updateAlertsTable(currentData.alerts);
            } else if (data.alerts && Array.isArray(data.alerts) && data.alerts.length === 0) {
                currentData.alerts = [];
                updateAlertsTable([]);
                console.log('No active alerts found');
            } else {
                console.warn('Received alert data is not in the expected format, ignoring:', data);
            }
        })
        .catch(error => {
            console.error('Error fetching alerts data:', error);
            updateStatusError(error.message);
        })
        .finally(() => {
            // Hide the refreshing indicator
            if (refreshIndicator) {
                refreshIndicator.classList.remove('refreshing');
            }
        });
}

function updateDashboard(data) {
    // Update summary counts
    updateElementText('nodes-count', data.nodes.length);
    updateElementText('nodes-ready', data.nodes.filter(n => n.status === 'Ready').length);
    updateElementText('nodes-notready', data.nodes.filter(n => n.status !== 'Ready').length);
    
    updateElementText('pods-count', data.pods.length);
    updateElementText('pods-running', data.pods.filter(p => p.phase === 'Running').length);
    updateElementText('pods-pending', data.pods.filter(p => p.phase === 'Pending').length);
    updateElementText('pods-failed', data.pods.filter(p => p.phase === 'Failed').length);
    
    // Only update alerts if we're getting them from the right source
    // and they are in the correct format (have an 'id' field)
    if (data.alerts && Array.isArray(data.alerts) && data.alerts.length > 0 && data.alerts[0].id) {
        const alerts = data.alerts;
        
        updateElementText('alerts-count', alerts.length);
        updateElementText('alerts-today', alerts.filter(a => {
            const today = new Date().toISOString().split('T')[0];
            // Check if created_at exists before using it
            return a.created_at && a.created_at.startsWith(today);
        }).length);
        updateElementText('alerts-total', alerts.length);
        
        // Update alert table
        updateAlertsTable(alerts);
    }
    
    // Update status indicator
    if (data.nodes.some(n => n.status !== 'Ready') || 
        data.pods.some(p => p.phase === 'Failed' || p.phase === 'Pending')) {
        updateStatusWarning();
    } else {
        updateStatusOk();
    }
    
    // Update charts
    updateNodeChart(data.nodes);
    updatePodChart(data.pods);
}

function updateResourcesTables(data) {
    // Update nodes table
    const nodesTable = document.getElementById('nodes-table');
    if (nodesTable) {
        nodesTable.innerHTML = '';
        
        if (data.nodes.length === 0) {
            nodesTable.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No nodes found</td></tr>';
            return;
        }
        
        // Populate namespaces dropdown
        updateNamespacesDropdown(data.pods);
        
        // Sort nodes by name
        const sortedNodes = [...data.nodes].sort((a, b) => a.name.localeCompare(b.name));
        
        sortedNodes.forEach(node => {
            const row = document.createElement('tr');
            
            // Apply class based on status
            if (node.status !== 'Ready') {
                row.classList.add('table-danger');
            }
            
            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <span class="status-badge ${node.status === 'Ready' ? 'status-ready' : 'status-notready'}"></span>
                        ${node.name}
                    </div>
                </td>
                <td>
                    <span class="badge ${node.status === 'Ready' ? 'bg-success' : 'bg-danger'}">${node.status}</span>
                </td>
                <td>${node.roles ? node.roles.join(', ') : 'none'}</td>
                <td>${node.version || 'N/A'}</td>
                <td>${node.cpu || 'N/A'}</td>
                <td>${node.memory || 'N/A'}</td>
            `;
            
            nodesTable.appendChild(row);
        });
    }
    
    // Update pods table
    const podsTable = document.getElementById('pods-table');
    if (podsTable) {
        podsTable.innerHTML = '';
        
        if (data.pods.length === 0) {
            podsTable.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No pods found</td></tr>';
            return;
        }
        
        // Sort pods by namespace and name
        const sortedPods = [...data.pods].sort((a, b) => {
            const nsCompare = a.namespace.localeCompare(b.namespace);
            return nsCompare !== 0 ? nsCompare : a.name.localeCompare(b.name);
        });
        
        sortedPods.forEach(pod => {
            const row = document.createElement('tr');
            
            // Apply class based on phase
            if (pod.phase === 'Failed') {
                row.classList.add('table-danger');
            } else if (pod.phase === 'Pending') {
                row.classList.add('table-warning');
            }
            
            // Create container status HTML
            let containerStatusHtml = '';
            if (pod.containers && pod.containers.length > 0) {
                containerStatusHtml = pod.containers.map(container => {
                    let statusClass = 'bg-secondary';
                    let displayState = container.state;
                    
                    if (container.state === 'Running' && container.ready) {
                        statusClass = 'bg-success';
                    } else if (container.state === 'Waiting') {
                        // Özel bekleyen durumları kontrol et
                        if (container.reason === 'CrashLoopBackOff' || 
                            container.reason === 'ImagePullBackOff' || 
                            container.reason === 'ErrImagePull' || 
                            container.reason === 'CreateContainerError') {
                            statusClass = 'bg-danger';
                            displayState = container.reason; // Durum görüntüsünü spesifik hataya güncelle
                        } else if (container.reason === 'ContainerCreating') {
                            statusClass = 'bg-info';
                            displayState = 'Creating';
                        } else {
                            statusClass = 'bg-warning';
                        }
                    } else if (container.state === 'Terminated') {
                        statusClass = 'bg-danger';
                    }
                    
                    let tooltip = '';
                    if (container.reason) {
                        tooltip = ` data-bs-toggle="tooltip" title="${container.reason}"`;
                    }
                    
                    const restartBadge = container.restarts > 0 
                        ? `<span class="badge bg-warning" data-bs-toggle="tooltip" title="${container.restarts} restarts">↻${container.restarts}</span>` 
                        : '';
                    
                    return `<div class="container-status"${tooltip}>
                        ${container.name} <span class="badge ${statusClass}">${displayState}</span> ${restartBadge}
                    </div>`;
                }).join('');
            } else {
                containerStatusHtml = '<span class="text-muted">No containers</span>';
            }
            
            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <span class="status-badge status-${pod.phase.toLowerCase()}"></span>
                        ${pod.name}
                    </div>
                </td>
                <td>${pod.namespace}</td>
                <td>
                    <span class="badge ${getStatusBadgeClass(pod.phase)}">${pod.phase}</span>
                </td>
                <td>${containerStatusHtml}</td>
                <td>${pod.node || 'N/A'}</td>
                <td>${pod.ip || 'N/A'}</td>
            `;
            
            podsTable.appendChild(row);
        });
        
        // Enable tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

function updateNamespacesDropdown(pods) {
    const namespaceFilter = document.getElementById('namespace-filter');
    if (!namespaceFilter) return;
    
    // Get unique namespaces
    const namespaces = [...new Set(pods.map(pod => pod.namespace))].sort();
    
    // Save the current selection
    const currentSelection = namespaceFilter.value;
    
    // Clear existing options except the first one
    while (namespaceFilter.options.length > 1) {
        namespaceFilter.remove(1);
    }
    
    // Add namespace options
    namespaces.forEach(namespace => {
        const option = document.createElement('option');
        option.value = namespace;
        option.textContent = namespace;
        namespaceFilter.appendChild(option);
    });
    
    // Restore selection if it exists
    if (namespaces.includes(currentSelection)) {
        namespaceFilter.value = currentSelection;
    }
}

function filterNodes() {
    const searchInput = document.getElementById('node-search');
    if (!searchInput) return;
    
    const query = searchInput.value.toLowerCase().trim();
    const nodesTable = document.getElementById('nodes-table');
    if (!nodesTable) return;
    
    // Filter nodes based on search query
    const filteredNodes = currentData.nodes.filter(node => 
        node.name.toLowerCase().includes(query) ||
        (node.roles && node.roles.join(' ').toLowerCase().includes(query)) ||
        node.version.toLowerCase().includes(query)
    );
    
    // Update table with filtered data
    const tempData = { ...currentData, nodes: filteredNodes };
    updateResourcesTables(tempData);
}

function filterPods() {
    const searchInput = document.getElementById('pod-search');
    const namespaceFilter = document.getElementById('namespace-filter');
    if (!searchInput || !namespaceFilter) return;
    
    const query = searchInput.value.toLowerCase().trim();
    const namespace = namespaceFilter.value;
    
    const podsTable = document.getElementById('pods-table');
    if (!podsTable) return;
    
    // Filter pods based on search query and namespace
    const filteredPods = currentData.pods.filter(pod => {
        const matchesQuery = 
            pod.name.toLowerCase().includes(query) ||
            pod.namespace.toLowerCase().includes(query) ||
            pod.phase.toLowerCase().includes(query) ||
            (pod.node && pod.node.toLowerCase().includes(query));
            
        const matchesNamespace = namespace === 'all' || pod.namespace === namespace;
        
        return matchesQuery && matchesNamespace;
    });
    
    // Update table with filtered data
    const tempData = { ...currentData, pods: filteredPods };
    updateResourcesTables(tempData);
}

function updateAlertsTable(alerts) {
    const alertsTable = document.getElementById('alerts-table');
    if (!alertsTable) return;
    
    alertsTable.innerHTML = '';
    
    if (!alerts || alerts.length === 0) {
        alertsTable.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No alerts found</td></tr>';
        return;
    }
    
    // Get the status filter
    const statusFilter = document.getElementById('alert-status-filter');
    const statusValue = statusFilter ? statusFilter.value : 'all';
    
    // Get the search value
    const searchInput = document.getElementById('alert-search');
    const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : '';
    
    // Check if we're in the resource view or main dashboard
    // In resource view, we have the alert-status-filter and we'll show all alerts (including resolved ones)
    // In main dashboard, we only show active alerts
    const isResourceView = !!statusFilter;
    
    // If we need to fetch all alerts for the resource view tab
    if (isResourceView && (statusValue === 'all' || statusValue === 'resolved')) {
        // Fetch all alerts (including resolved) for the resource view
        fetch('/api/alerts?status=all')
            .then(response => response.json())
            .then(data => {
                if (data.alerts && Array.isArray(data.alerts)) {
                    populateAlertsTable(data.alerts, statusValue, searchQuery);
                }
            })
            .catch(error => {
                console.error('Error fetching all alerts:', error);
                // Fall back to current alerts
                populateFilteredAlertsTable(alerts, statusValue, searchQuery);
            });
    } else {
        // Just filter the current alerts (which are already active-only for the dashboard)
        populateFilteredAlertsTable(alerts, statusValue, searchQuery);
    }
}

function populateAlertsTable(alerts, statusValue, searchQuery) {
    // We've received alerts directly from the API, just apply filtering
    populateFilteredAlertsTable(alerts, statusValue, searchQuery);
}

function populateFilteredAlertsTable(alerts, statusValue, searchQuery) {
    const alertsTable = document.getElementById('alerts-table');
    if (!alertsTable) return;
    
    // Clear the table before populating
    alertsTable.innerHTML = '';
    
    // Filter alerts based on status and search query
    let filteredAlerts = [...alerts];
    
    // Apply status filter if the data has is_resolved property
    if (statusValue === 'active') {
        filteredAlerts = filteredAlerts.filter(alert => alert && alert.is_resolved === false);
    } else if (statusValue === 'resolved') {
        filteredAlerts = filteredAlerts.filter(alert => alert && alert.is_resolved === true);
    }
    
    // Apply search query filter if search term exists
    if (searchQuery) {
        filteredAlerts = filteredAlerts.filter(alert => {
            if (!alert) return false;
            
            // Safely check properties before using them
            const resourceType = (alert.resource_type || '').toLowerCase();
            const resourceName = (alert.resource_name || '').toLowerCase();
            const resourceNamespace = (alert.resource_namespace || '').toLowerCase();
            const status = (alert.status || '').toLowerCase();
            
            return resourceType.includes(searchQuery) ||
                   resourceName.includes(searchQuery) ||
                   resourceNamespace.includes(searchQuery) ||
                   status.includes(searchQuery);
        });
    }
    
    // Sort alerts by creation date (newest first)
    filteredAlerts.sort((a, b) => {
        // Handle missing dates
        if (!a || !a.created_at) return 1;
        if (!b || !b.created_at) return -1;
        
        return new Date(b.created_at) - new Date(a.created_at);
    });
    
    // Render filtered alerts
    filteredAlerts.forEach(alert => {
        const row = document.createElement('tr');
        
        // Apply class based on status
        if (!alert.is_resolved && alert.status) {
            const status = alert.status.toString();
            if (status.includes('NotReady') || 
                status.includes('Failed') || 
                status.includes('CrashLoopBackOff') || 
                status.includes('ImagePullBackOff')) {
                row.classList.add('table-danger');
            } else if (status.includes('Pending')) {
                row.classList.add('table-warning');
            }
        }
        
        // Format dates
        const createdDate = new Date(alert.created_at);
        const resolvedDate = alert.resolved_at ? new Date(alert.resolved_at) : null;
        
        const formatDate = (date) => {
            if (!date) return 'N/A';
            
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            
            const isToday = date.toDateString() === today.toDateString();
            const isYesterday = date.toDateString() === yesterday.toDateString();
            
            if (isToday) {
                return `Today ${date.toTimeString().substring(0, 8)}`;
            } else if (isYesterday) {
                return `Yesterday ${date.toTimeString().substring(0, 8)}`;
            } else {
                return `${date.toLocaleDateString()} ${date.toTimeString().substring(0, 8)}`;
            }
        };
        
        // Make sure we have a valid alert object with required fields
        if (!alert || !alert.id) {
            // Do not log these warnings to avoid console clutter
            // The system may occasionally send temporary monitoring data
            return;
        }
        
        const resourceType = alert.resource_type || 'Unknown';
        const resourceName = alert.resource_name || 'Unknown';
        const resourceNamespace = alert.resource_namespace || 'N/A';
        const status = alert.status || 'Unknown';
        const isResolved = Boolean(alert.is_resolved);
        const alertId = alert.id;
        
        // Generate status badge class
        let statusBadgeClass = 'bg-info';
        if (status.includes('Recovery')) {
            statusBadgeClass = 'bg-success';
        } else if (status.includes('NotReady') || 
                  status.includes('Failed') || 
                  status.includes('CrashLoopBackOff') || 
                  status.includes('ImagePullBackOff')) {
            statusBadgeClass = 'bg-danger';
        } else if (status.includes('Pending')) {
            statusBadgeClass = 'bg-warning';
        }
        
        // Get error message from the alert
        const errorMessage = alert.message || 'No additional details available';
        
        row.innerHTML = `
            <td>${resourceType}</td>
            <td>${resourceName}</td>
            <td>${resourceNamespace}</td>
            <td>
                <span class="badge ${statusBadgeClass}">
                    ${status}
                </span>
            </td>
            <td>
                <small class="text-muted">${errorMessage}</small>
            </td>
            <td>${formatDate(createdDate)}</td>
            <td>${isResolved ? formatDate(resolvedDate) : 'N/A'}</td>
            <td>
                <span class="badge ${isResolved ? 'bg-success' : 'bg-warning'}">
                    ${isResolved ? 'Resolved' : 'Active'}
                </span>
            </td>
            <td>
                <div class="btn-group btn-group-sm" role="group">
                    ${!isResolved ? 
                        `<button type="button" class="btn btn-outline-success btn-sm resolve-alert" data-alert-id="${alertId}" title="Mark as resolved">
                            <i data-feather="check"></i>
                         </button>` : ''}
                    <button type="button" class="btn btn-outline-danger btn-sm delete-alert" data-alert-id="${alertId}" title="Delete alert">
                        <i data-feather="trash-2"></i>
                    </button>
                </div>
            </td>
        `;
        
        alertsTable.appendChild(row);
    });
    
    // Event listeners for alerts tab
    const alertStatusFilter = document.getElementById('alert-status-filter');
    if (alertStatusFilter && !alertStatusFilter.hasListenerSet) {
        alertStatusFilter.addEventListener('change', () => updateAlertsTable(alerts));
        alertStatusFilter.hasListenerSet = true;
    }
    
    const alertSearch = document.getElementById('alert-search');
    if (alertSearch && !alertSearch.hasListenerSet) {
        alertSearch.addEventListener('input', () => updateAlertsTable(alerts));
        alertSearch.hasListenerSet = true;
    }
    
    const refreshAlertsButton = document.getElementById('btn-refresh-alerts-list');
    if (refreshAlertsButton && !refreshAlertsButton.hasListenerSet) {
        refreshAlertsButton.addEventListener('click', refreshData);
        refreshAlertsButton.hasListenerSet = true;
    }
    
    // Initialize icons for newly added buttons
    feather.replace();
    
    // Add event listeners for delete buttons
    const deleteButtons = document.querySelectorAll('.delete-alert');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            const alertId = this.getAttribute('data-alert-id');
            if (confirm('Are you sure you want to delete this alert?')) {
                deleteAlert(alertId);
            }
        });
    });
    
    // Add event listeners for resolve buttons
    const resolveButtons = document.querySelectorAll('.resolve-alert');
    resolveButtons.forEach(button => {
        button.addEventListener('click', function() {
            const alertId = this.getAttribute('data-alert-id');
            resolveAlert(alertId);
        });
    });

}

function updateNodeChart(nodes) {
    const ctx = document.getElementById('node-chart');
    if (!ctx) return;
    
    // Count node statuses
    const readyCount = nodes.filter(n => n.status === 'Ready').length;
    const notReadyCount = nodes.filter(n => n.status !== 'Ready').length;
    
    const data = {
        labels: ['Ready', 'NotReady'],
        datasets: [{
            label: 'Node Status',
            data: [readyCount, notReadyCount],
            backgroundColor: [
                '#198754', // green for Ready
                '#dc3545'  // red for NotReady
            ],
            borderWidth: 1
        }]
    };
    
    const config = {
        type: 'doughnut',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: false
                }
            }
        }
    };
    
    if (nodeChart) {
        nodeChart.data = data;
        nodeChart.update();
    } else {
        nodeChart = new Chart(ctx, config);
    }
}

function updatePodChart(pods) {
    const ctx = document.getElementById('pod-chart');
    if (!ctx) return;
    
    // Count pod phases
    const runningCount = pods.filter(p => p.phase === 'Running').length;
    const pendingCount = pods.filter(p => p.phase === 'Pending').length;
    const failedCount = pods.filter(p => p.phase === 'Failed').length;
    const otherCount = pods.filter(p => !['Running', 'Pending', 'Failed'].includes(p.phase)).length;
    
    const data = {
        labels: ['Running', 'Pending', 'Failed', 'Other'],
        datasets: [{
            label: 'Pod Status',
            data: [runningCount, pendingCount, failedCount, otherCount],
            backgroundColor: [
                '#198754', // green for Running
                '#ffc107', // yellow for Pending
                '#dc3545', // red for Failed
                '#6c757d'  // gray for Other
            ],
            borderWidth: 1
        }]
    };
    
    const config = {
        type: 'doughnut',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: false
                }
            }
        }
    };
    
    if (podChart) {
        podChart.data = data;
        podChart.update();
    } else {
        podChart = new Chart(ctx, config);
    }
}

function updateStatusOk() {
    const statusIcon = document.getElementById('status-icon');
    const statusMessage = document.getElementById('status-message');
    
    if (statusIcon) {
        statusIcon.className = 'display-4 me-3 text-success';
        statusIcon.innerHTML = '<i data-feather="check-circle"></i>';
        feather.replace();
    }
    
    if (statusMessage) {
        statusMessage.innerHTML = 'All systems operational';
        statusMessage.className = 'text-success';
    }
}

function updateStatusWarning() {
    const statusIcon = document.getElementById('status-icon');
    const statusMessage = document.getElementById('status-message');
    
    if (statusIcon) {
        statusIcon.className = 'display-4 me-3 text-warning';
        statusIcon.innerHTML = '<i data-feather="alert-triangle"></i>';
        feather.replace();
    }
    
    if (statusMessage) {
        statusMessage.innerHTML = 'Issues detected';
        statusMessage.className = 'text-warning';
    }
}

function updateStatusError(message) {
    const statusIcon = document.getElementById('status-icon');
    const statusMessage = document.getElementById('status-message');
    
    if (statusIcon) {
        statusIcon.className = 'display-4 me-3 text-danger';
        statusIcon.innerHTML = '<i data-feather="x-circle"></i>';
        feather.replace();
    }
    
    if (statusMessage) {
        statusMessage.innerHTML = message || 'Connection error';
        statusMessage.className = 'text-danger';
    }
}

function updateElementText(id, text) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = text;
    }
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'Running':
            return 'bg-success';
        case 'Pending':
            return 'bg-warning';
        case 'Failed':
            return 'bg-danger';
        case 'ImagePullBackOff':
        case 'CrashLoopBackOff':
        case 'ErrImagePull':
        case 'CreateContainerError':
            return 'bg-danger';
        case 'ContainerCreating':
        case 'Succeeded':
            return 'bg-info';
        default:
            return 'bg-secondary';
    }
}

// Delete an alert
function deleteAlert(alertId) {
    console.log(`Deleting alert with ID: ${alertId}`); // Debug log
    fetch(`/api/alerts/${alertId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Show success message
            const alertElement = document.createElement('div');
            alertElement.className = 'alert alert-success alert-dismissible fade show';
            alertElement.setAttribute('role', 'alert');
            alertElement.innerHTML = `
                <strong>Success!</strong> ${data.message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            
            const mainContent = document.querySelector('main.container');
            if (mainContent) {
                mainContent.insertBefore(alertElement, mainContent.firstChild);
            }
            
            // Automatically dismiss after 5 seconds
            setTimeout(() => {
                const bsAlert = new bootstrap.Alert(alertElement);
                bsAlert.close();
            }, 5000);
            
            // Refresh the alerts list
            refreshData();
        } else {
            console.error(data.error);
            alert(`Error: ${data.error}`);
        }
    })
    .catch(error => {
        console.error('Error deleting alert:', error);
        alert(`Error deleting alert: ${error.message}`);
    });
}

// Mark an alert as resolved
function resolveAlert(alertId) {
    fetch(`/api/alerts/${alertId}/resolve`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Show success message
            const alertElement = document.createElement('div');
            alertElement.className = 'alert alert-success alert-dismissible fade show';
            alertElement.setAttribute('role', 'alert');
            alertElement.innerHTML = `
                <strong>Success!</strong> ${data.message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            
            const mainContent = document.querySelector('main.container');
            if (mainContent) {
                mainContent.insertBefore(alertElement, mainContent.firstChild);
            }
            
            // Automatically dismiss after 5 seconds
            setTimeout(() => {
                const bsAlert = new bootstrap.Alert(alertElement);
                bsAlert.close();
            }, 5000);
            
            // Refresh the alerts list
            refreshData();
        } else {
            console.error(data.error);
            alert(`Error: ${data.error}`);
        }
    })
    .catch(error => {
        console.error('Error resolving alert:', error);
        alert(`Error resolving alert: ${error.message}`);
    });
}
