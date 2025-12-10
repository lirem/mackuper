// History component
let historyState = {
    history: [],
    filters: {
        status: '',
        job_id: '',
        days: 7
    },
    pagination: {
        page: 1,
        limit: 20
    },
    jobs: [],
    showLogsModal: false,
    selectedLog: null
};

/**
 * Parse backup logs to extract progress information.
 */
function parseBackupProgress(logs, status) {
    if (!logs) {
        return { phase: 'UNKNOWN', percentage: 0, phaseText: 'Initializing...', recentFiles: [] };
    }

    const lines = logs.split('\n');
    const linesToParse = lines.length > 1000 ? lines.slice(-1000) : lines;

    // Find last phase marker
    const phaseRegex = /\[PHASE:(\w+)\]/;
    let lastPhase = null;
    for (let i = linesToParse.length - 1; i >= 0; i--) {
        const match = linesToParse[i].match(phaseRegex);
        if (match) {
            lastPhase = match[1];
            break;
        }
    }

    // Map phase to progress
    const phaseMap = {
        'ACQUIRING': { pct: 15, text: 'Acquiring source files...' },
        'COMPRESSING': { pct: 45, text: 'Creating compressed archive...' },
        'UPLOADING': { pct: 75, text: 'Uploading to S3...' },
        'FINALIZING': { pct: 95, text: 'Finalizing and cleanup...' },
        'COMPLETE': { pct: 100, text: 'Complete' }
    };

    let result = { phase: lastPhase || 'UNKNOWN', percentage: 0, phaseText: 'Starting...', recentFiles: [] };

    if (lastPhase && phaseMap[lastPhase]) {
        result.percentage = phaseMap[lastPhase].pct;
        result.phaseText = phaseMap[lastPhase].text;
    } else if (status === 'success') {
        result.percentage = 100;
        result.phaseText = 'Complete';
    }

    // Extract recent files (→ Processing file: or → Downloading file:)
    const fileRegex = /→ (?:Processing|Downloading) file: (.+?) \((.+?)\)/;
    const recentFiles = [];
    for (const line of linesToParse) {
        const match = line.match(fileRegex);
        if (match) {
            recentFiles.push({ name: match[1], size: match[2] });
        }
    }
    result.recentFiles = recentFiles.slice(-20); // Last 20 files

    return result;
}

// Helper to get job name by ID
function getJobName(jobId, jobs) {
    const job = jobs.find(j => j.id === jobId);
    return job ? job.name : `Job #${jobId}`;
}

// Helper to calculate duration
function calculateDuration(startedAt, completedAt) {
    if (!completedAt || !startedAt) return null;
    return Math.round((new Date(completedAt) - new Date(startedAt)) / 1000);
}

async function renderHistory() {
    const app = Alpine.$data(document.querySelector('[x-data]'));

    try {
        // Fetch jobs for filter dropdown
        if (historyState.jobs.length === 0) {
            historyState.jobs = await fetch('/api/jobs').then(r => r.json());
        }

        // Fetch history with filters
        const params = new URLSearchParams();
        if (historyState.filters.status) params.append('status', historyState.filters.status);
        if (historyState.filters.job_id) params.append('job_id', historyState.filters.job_id);
        if (historyState.filters.days) params.append('days', historyState.filters.days);
        params.append('page', historyState.pagination.page);
        params.append('limit', historyState.pagination.limit);

        const response = await fetch(`/api/history?${params.toString()}`).then(r => r.json());
        historyState.history = response.records || [];

        // Update app data - Alpine will handle DOM updates
        app.historyData = {
            records: historyState.history,
            jobs: historyState.jobs,
            filters: historyState.filters,
            pagination: historyState.pagination
        };
    } catch (error) {
        console.error('History render error:', error);
        app.showToast('Failed to load history', 'error');
    }
}

// Keep this for reference but it's now unused - will be deleted after confirming new approach works
async function renderHistoryOLD() {
    try {
        // Fetch jobs for filter dropdown
        if (historyState.jobs.length === 0) {
            historyState.jobs = await fetch('/api/jobs').then(r => r.json());
        }

        // Fetch history with filters
        const params = new URLSearchParams();
        if (historyState.filters.status) params.append('status', historyState.filters.status);
        if (historyState.filters.job_id) params.append('job_id', historyState.filters.job_id);
        if (historyState.filters.days) params.append('days', historyState.filters.days);
        params.append('page', historyState.pagination.page);
        params.append('limit', historyState.pagination.limit);

        const response = await fetch(`/api/history?${params.toString()}`).then(r => r.json());
        historyState.history = response.records || [];

        // Get app instance for badge display
        const app = Alpine.$data(document.querySelector('[x-data]'));

        return `
            <div class="space-y-6">
                <!-- Header -->
                <div class="flex justify-between items-center">
                    <div>
                        <h1 class="text-2xl font-bold text-gray-900">Backup History</h1>
                        <div class="flex items-center gap-2 text-sm text-gray-500 mt-1">
                            <div class="w-2 h-2 rounded-full bg-green-500 ${app.isRefreshing ? '' : 'hidden'}"></div>
                            <span>Updated ${formatRelativeTime(app.lastHistoryRefresh)}</span>
                        </div>
                    </div>
                    <button onclick="showCleanupDialog()" class="btn-secondary btn-sm">
                        Cleanup Old Records
                    </button>
                </div>

                <!-- Filters -->
                <div class="card">
                    <h2 class="text-sm font-semibold text-gray-700 mb-3">Filters</h2>
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div>
                            <label class="form-label">Status</label>
                            <select class="form-select" onchange="updateFilter('status', this.value)">
                                <option value="">All</option>
                                <option value="success" ${historyState.filters.status === 'success' ? 'selected' : ''}>Success</option>
                                <option value="failed" ${historyState.filters.status === 'failed' ? 'selected' : ''}>Failed</option>
                                <option value="running" ${historyState.filters.status === 'running' ? 'selected' : ''}>Running</option>
                                <option value="cancelling" ${historyState.filters.status === 'cancelling' ? 'selected' : ''}>Cancelling</option>
                                <option value="cancelled" ${historyState.filters.status === 'cancelled' ? 'selected' : ''}>Cancelled</option>
                            </select>
                        </div>

                        <div>
                            <label class="form-label">Job</label>
                            <select class="form-select" onchange="updateFilter('job_id', this.value)">
                                <option value="">All Jobs</option>
                                ${historyState.jobs.map(job => `
                                    <option value="${job.id}" ${historyState.filters.job_id == job.id ? 'selected' : ''}>
                                        ${escapeHtml(job.name)}
                                    </option>
                                `).join('')}
                            </select>
                        </div>

                        <div>
                            <label class="form-label">Time Range</label>
                            <select class="form-select" onchange="updateFilter('days', this.value)">
                                <option value="1" ${historyState.filters.days == 1 ? 'selected' : ''}>Last 24 hours</option>
                                <option value="7" ${historyState.filters.days == 7 ? 'selected' : ''}>Last 7 days</option>
                                <option value="30" ${historyState.filters.days == 30 ? 'selected' : ''}>Last 30 days</option>
                                <option value="90" ${historyState.filters.days == 90 ? 'selected' : ''}>Last 90 days</option>
                                <option value="" ${historyState.filters.days === '' ? 'selected' : ''}>All time</option>
                            </select>
                        </div>

                        <div class="flex items-end">
                            <button onclick="resetFilters()" class="btn-secondary w-full">
                                Reset Filters
                            </button>
                        </div>
                    </div>
                </div>

                <!-- History Table -->
                ${historyState.history.length === 0 ? `
                    <div class="card">
                        <div class="empty-state">
                            <p class="empty-state-text">No backup history found</p>
                            <p class="empty-state-subtext">No backups match the selected filters</p>
                        </div>
                    </div>
                ` : `
                    <div class="card overflow-hidden">
                        <div class="overflow-x-auto">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Job Name</th>
                                        <th>Status</th>
                                        <th>Started</th>
                                        <th>Completed</th>
                                        <th>Duration</th>
                                        <th>Size</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${historyState.history.map(item => renderHistoryRow(item)).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `}
            </div>
        `;
    } catch (error) {
        console.error('History render error:', error);
        return `
            <div class="alert alert-error">
                Failed to load history. Please refresh the page.
            </div>
        `;
    }
}

function renderHistoryRow(item) {
    const duration = item.completed_at && item.started_at
        ? Math.round((new Date(item.completed_at) - new Date(item.started_at)) / 1000)
        : null;

    const job = historyState.jobs.find(j => j.id === item.job_id);
    const jobName = job ? job.name : `Job #${item.job_id}`;

    return `
        <tr>
            <td class="font-medium">${escapeHtml(jobName)}</td>
            <td>
                <span class="badge ${getStatusBadgeClass(item.status)}">
                    ${item.status}
                </span>
            </td>
            <td class="text-sm text-gray-600">${formatDate(item.started_at)}</td>
            <td class="text-sm text-gray-600">${item.completed_at ? formatDate(item.completed_at) : '-'}</td>
            <td class="text-sm text-gray-600">${duration ? duration + 's' : '-'}</td>
            <td class="text-sm text-gray-600">${item.file_size_bytes ? formatBytes(item.file_size_bytes) : '-'}</td>
            <td>
                <div class="flex gap-2">
                    ${item.status === 'running' || item.status === 'cancelling' ? `
                        <button
                            onclick="cancelBackup(${item.id})"
                            class="btn-secondary btn-sm"
                            ${item.status === 'cancelling' ? 'disabled' : ''}>
                            ${item.status === 'cancelling' ? 'Cancelling...' : 'Cancel'}
                        </button>
                    ` : ''}
                    <button onclick="viewLogs(${item.id})" class="btn-secondary btn-sm">
                        View Logs
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function updateFilter(key, value) {
    historyState.filters[key] = value;
    historyState.pagination.page = 1; // Reset to first page

    const app = Alpine.$data(document.querySelector('[x-data]'));
    app.refreshHistory();
}

function resetFilters() {
    historyState.filters = {
        status: '',
        job_id: '',
        days: 7
    };
    historyState.pagination.page = 1;

    const app = Alpine.$data(document.querySelector('[x-data]'));
    app.refreshHistory();
}

async function viewLogs(historyId) {
    try {
        const app = Alpine.$data(document.querySelector('[x-data]'));

        const response = await fetch(`/api/history/${historyId}`);
        const data = await response.json();

        const job = historyState.jobs.find(j => j.id === data.job_id);
        const jobName = job ? job.name : `Job #${data.job_id}`;
        const progress = parseBackupProgress(data.logs, data.status);
        const isRunning = data.status === 'running' || data.status === 'cancelling';

        // Progress section (only for running or completed phase-tracked backups)
        let progressHtml = '';
        if (isRunning || progress.phase !== 'UNKNOWN') {
            const pct = Math.min(100, Math.max(0, Math.round(progress.percentage)));
            progressHtml = `
                <div class="mb-4 border-l-4 border-blue-600 pl-4 ml-1" id="backup-progress-section">
                    <div class="bg-gray-200 rounded-full h-6 mb-2 overflow-hidden">
                        <div class="bg-blue-600 h-full flex items-center justify-center text-white text-xs font-semibold transition-all duration-300"
                             style="width: ${pct}%" id="progress-bar">
                            ${pct}%
                        </div>
                    </div>
                    <div class="text-sm text-gray-600 mb-4" id="progress-phase-text">
                        ${escapeHtml(progress.phaseText)}
                    </div>
                </div>
            `;
        }

        // Update modal content in persistent modal
        app.historyModalContent = `
            <div class="flex justify-between items-start mb-4">
                <div>
                    <h2 class="text-xl font-bold">${escapeHtml(jobName)} - Backup Logs</h2>
                    <p class="text-sm text-gray-600 mt-1">
                        Started: ${formatDate(data.started_at)}
                        ${data.completed_at ? ` | Completed: ${formatDate(data.completed_at)}` : ''}
                    </p>
                </div>
                <button onclick="closeLogsModal()" class="text-gray-500 hover:text-gray-700">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>

            <div class="mb-4 grid grid-cols-2 gap-4 text-sm">
                <div>
                    <span class="text-gray-500">Status:</span>
                    <span class="ml-2 badge ${getStatusBadgeClass(data.status)}" id="status-badge">${data.status}</span>
                </div>
                <div>
                    <span class="text-gray-500">File Size:</span>
                    <span class="ml-2">${data.file_size_bytes ? formatBytes(data.file_size_bytes) : 'N/A'}</span>
                </div>
                ${data.s3_key ? `
                    <div class="col-span-2">
                        <span class="text-gray-500">S3 Key:</span>
                        <span class="ml-2 monospace text-xs">${escapeHtml(data.s3_key)}</span>
                    </div>
                ` : ''}
                ${data.local_path ? `
                    <div class="col-span-2">
                        <span class="text-gray-500">Local Path:</span>
                        <span class="ml-2 monospace text-xs">${escapeHtml(data.local_path)}</span>
                    </div>
                ` : ''}
                ${data.error_message ? `
                    <div class="col-span-2">
                        <span class="text-gray-500">Error:</span>
                        <span class="ml-2 text-red-600">${escapeHtml(data.error_message)}</span>
                    </div>
                ` : ''}
            </div>

            ${progressHtml}

            <div class="border-t border-gray-200 pt-4">
                <div class="flex justify-between items-center mb-2">
                    <h3 class="text-sm font-semibold text-gray-700">Execution Logs</h3>
                    <button onclick="toggleFullLogs()" class="text-sm text-blue-600 hover:text-blue-800 font-medium" id="toggle-logs-btn">
                        Show Full Logs ▼
                    </button>
                </div>
                <div class="bg-gray-900 text-green-400 p-4 rounded font-mono text-xs overflow-x-auto max-h-96 overflow-y-auto hidden" id="full-logs-content">
                    ${data.logs ? escapeHtml(data.logs).replace(/\n/g, '<br>') : '<span class="text-gray-500">No logs available</span>'}
                </div>
            </div>

            <div class="flex justify-end mt-4">
                <button onclick="closeLogsModal()" class="btn-secondary">
                    Close
                </button>
            </div>
        `;

        // Open persistent modal
        app.historyModalOpen = true;
        app.currentHistoryId = historyId;

        // Start polling if backup is running
        if (isRunning) {
            startLogPolling(historyId);
        }
    } catch (error) {
        alert('Failed to load logs: ' + error.message);
    }
}

function toggleFullLogs() {
    const content = document.getElementById('full-logs-content');
    const btn = document.getElementById('toggle-logs-btn');
    if (content && btn) {
        if (content.classList.contains('hidden')) {
            content.classList.remove('hidden');
            btn.textContent = 'Hide Full Logs ▲';
        } else {
            content.classList.add('hidden');
            btn.textContent = 'Show Full Logs ▼';
        }
    }
}

// Polling for real-time progress updates
let logPollingInterval = null;

function startLogPolling(historyId) {
    stopLogPolling();
    console.log(`Starting polling for history ${historyId}`);

    logPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/history/${historyId}`);
            const data = await response.json();
            updateProgressDisplay(data);

            // Stop if no longer running
            if (data.status !== 'running' && data.status !== 'cancelling') {
                stopLogPolling();
                // Refresh modal with final state
                const app = Alpine.$data(document.querySelector('[x-data]'));
                if (app.historyModalOpen && app.currentHistoryId === historyId) {
                    viewLogs(historyId);
                }
            }
        } catch (error) {
            console.error('Polling failed:', error);
        }
    }, 2000);
}

function stopLogPolling() {
    if (logPollingInterval) {
        console.log('Stopping log polling');
        clearInterval(logPollingInterval);
        logPollingInterval = null;
    }
}

function updateProgressDisplay(data) {
    const app = Alpine.$data(document.querySelector('[x-data]'));
    if (!app.historyModalOpen) {
        stopLogPolling();
        return;
    }

    const progress = parseBackupProgress(data.logs, data.status);

    // Update progress bar
    const bar = document.getElementById('progress-bar');
    if (bar) {
        const pct = Math.min(100, Math.max(0, Math.round(progress.percentage)));
        bar.style.width = `${pct}%`;
        bar.textContent = `${pct}%`;
    }

    // Update phase text
    const phaseText = document.getElementById('progress-phase-text');
    if (phaseText) {
        phaseText.textContent = progress.phaseText;
    }

    // Update full logs if visible
    const fullLogs = document.getElementById('full-logs-content');
    if (fullLogs && !fullLogs.classList.contains('hidden')) {
        fullLogs.innerHTML = data.logs
            ? escapeHtml(data.logs).replace(/\n/g, '<br>')
            : '<span class="text-gray-500">No logs available</span>';
    }

    // Update status badge
    const statusBadge = document.getElementById('status-badge');
    if (statusBadge && data.status) {
        statusBadge.className = `badge ${getStatusBadgeClass(data.status)}`;
        statusBadge.textContent = data.status;
    }
}

function closeLogsModal() {
    stopLogPolling();
    const app = Alpine.$data(document.querySelector('[x-data]'));
    app.historyModalOpen = false;
    app.currentHistoryId = null;
}

async function cancelBackup(historyId) {
    if (!confirm('Cancel this running backup? Temporary files will be cleaned up.')) return;

    try {
        const response = await fetch(`/api/history/${historyId}/cancel`, {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to cancel backup');
        }

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(result.message || 'Cancellation requested', 'warning');

        // Refresh history to show updated status
        setTimeout(() => app.refreshHistory(), 1000);
    } catch (error) {
        alert('Failed to cancel backup: ' + error.message);
    }
}

async function showCleanupDialog() {
    const days = prompt('Delete history records older than how many days? (minimum 30)', '90');

    if (!days) return;

    const daysNum = parseInt(days);
    if (isNaN(daysNum) || daysNum < 30) {
        alert('Please enter a number of days (minimum 30)');
        return;
    }

    if (!confirm(`Delete all backup history older than ${daysNum} days?`)) return;

    try {
        const response = await fetch('/api/history/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days: daysNum })
        });

        const result = await response.json();

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(result.message || `Deleted ${result.deleted || 0} records`, 'success');
        app.refreshHistory();
    } catch (error) {
        alert('Cleanup failed: ' + error.message);
    }
}
