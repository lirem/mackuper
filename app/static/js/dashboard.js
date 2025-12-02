// Dashboard component
async function renderDashboard() {
    try {
        // Fetch all dashboard data
        const [overview, recentActivity, statistics] = await Promise.all([
            fetch('/api/dashboard/overview').then(r => r.json()),
            fetch('/api/dashboard/recent-activity').then(r => r.json()),
            fetch('/api/dashboard/statistics').then(r => r.json())
        ]);

        return `
            <div class="space-y-6">
                <!-- Overview Stats Cards -->
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div class="stat-card">
                        <div class="stat-label">Total Jobs</div>
                        <div class="stat-value">${overview.total_jobs}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Active Jobs</div>
                        <div class="stat-value">${overview.active_jobs}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Last Backup</div>
                        <div class="stat-value text-lg">${formatRelativeTime(overview.last_backup_time)}</div>
                        <div class="stat-change">
                            ${overview.last_backup_status ?
                                `<span class="badge ${getStatusBadgeClass(overview.last_backup_status)}">${overview.last_backup_status}</span>`
                                : 'No backups yet'}
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Scheduler</div>
                        <div class="stat-value text-lg">${overview.scheduler_running ? 'Running' : 'Stopped'}</div>
                        <div class="stat-change">
                            <span class="${overview.scheduler_running ? 'text-green-600' : 'text-red-600'}">
                                ${overview.scheduler_running ? '● Active' : '● Inactive'}
                            </span>
                        </div>
                    </div>
                </div>

                <!-- Overall Statistics -->
                <div class="card">
                    <h2 class="card-header">Overall Statistics</h2>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                            <p class="text-sm text-gray-500 mb-1">Total Backups</p>
                            <p class="text-2xl font-semibold">${statistics.total_backups || 0}</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-500 mb-1">Success Rate</p>
                            <p class="text-2xl font-semibold">${statistics.success_rate || 0}%</p>
                        </div>
                        <div>
                            <p class="text-sm text-gray-500 mb-1">Total Size</p>
                            <p class="text-2xl font-semibold">${formatBytes(statistics.total_size || 0)}</p>
                        </div>
                    </div>
                </div>

                <!-- Recent Activity -->
                <div class="card">
                    <h2 class="card-header">Recent Activity</h2>
                    ${recentActivity.length === 0 ? `
                        <div class="empty-state">
                            <p class="empty-state-text">No backup history yet</p>
                            <p class="empty-state-subtext">Create a backup job to get started</p>
                        </div>
                    ` : `
                        <div class="overflow-x-auto">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Job Name</th>
                                        <th>Status</th>
                                        <th>Started</th>
                                        <th>Duration</th>
                                        <th>Size</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${recentActivity.map(item => {
                                        const duration = item.completed_at && item.started_at
                                            ? Math.round((new Date(item.completed_at) - new Date(item.started_at)) / 1000)
                                            : null;
                                        return `
                                            <tr>
                                                <td class="font-medium">${escapeHtml(item.job_name)}</td>
                                                <td>
                                                    <span class="badge ${getStatusBadgeClass(item.status)}">
                                                        ${item.status}
                                                    </span>
                                                </td>
                                                <td class="text-gray-600">${formatRelativeTime(item.started_at)}</td>
                                                <td class="text-gray-600">${duration ? duration + 's' : '-'}</td>
                                                <td class="text-gray-600">${item.file_size_bytes ? formatBytes(item.file_size_bytes) : '-'}</td>
                                                <td>
                                                    ${item.status === 'running' || item.status === 'cancelling' ? `
                                                        <button
                                                            onclick="cancelBackupFromDashboard(${item.id})"
                                                            class="btn-secondary btn-sm"
                                                            ${item.status === 'cancelling' ? 'disabled' : ''}>
                                                            ${item.status === 'cancelling' ? 'Cancelling...' : 'Cancel'}
                                                        </button>
                                                    ` : '-'}
                                                </td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    `}
                </div>

                <!-- Quick Actions -->
                <div class="card">
                    <h2 class="card-header">Quick Actions</h2>
                    <div class="flex gap-4">
                        <button onclick="window.dispatchEvent(new CustomEvent('switch-tab', {detail: 'jobs'}))"
                                class="btn-primary">
                            Create Backup Job
                        </button>
                        <button onclick="window.dispatchEvent(new CustomEvent('switch-tab', {detail: 'history'}))"
                                class="btn-secondary">
                            View All History
                        </button>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Dashboard render error:', error);
        return `
            <div class="alert alert-error">
                Failed to load dashboard data. Please refresh the page.
            </div>
        `;
    }
}

async function cancelBackupFromDashboard(historyId) {
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

        // Refresh dashboard to show updated status
        setTimeout(() => app.refreshDashboard(), 1000);
    } catch (error) {
        alert('Failed to cancel backup: ' + error.message);
    }
}

// Event listener for quick action tab switching
window.addEventListener('switch-tab', (e) => {
    const app = Alpine.$data(document.querySelector('[x-data]'));
    if (app) {
        app.currentTab = e.detail;
    }
});
