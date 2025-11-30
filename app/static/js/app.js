// Main Alpine.js application
function mackuperApp() {
    return {
        // State
        currentTab: 'dashboard',
        schedulerRunning: false,
        toast: {
            show: false,
            message: '',
            type: 'info' // success, error, info
        },

        // Component HTML storage
        dashboardHtml: '',
        jobsHtml: '',
        historyHtml: '',
        settingsHtml: '',

        // Initialization
        async init() {
            // Check scheduler status
            await this.checkSchedulerStatus();

            // Load initial tab content
            await this.loadDashboard();
            await this.loadJobs();
            await this.loadHistory();
            await this.loadSettings();

            // Watch for tab changes
            this.$watch('currentTab', (value) => {
                this.onTabChange(value);
            });

            // Start polling for updates (every 10 seconds)
            setInterval(() => {
                this.checkSchedulerStatus();
                if (this.currentTab === 'dashboard') {
                    this.refreshDashboard();
                } else if (this.currentTab === 'history') {
                    this.refreshHistory();
                }
            }, 10000);
        },

        // Scheduler status check
        async checkSchedulerStatus() {
            try {
                const response = await fetch('/api/dashboard/overview');
                const data = await response.json();
                this.schedulerRunning = data.scheduler_running;
            } catch (error) {
                console.error('Failed to check scheduler status:', error);
            }
        },

        // Tab change handler
        onTabChange(tab) {
            // Refresh content when switching tabs
            if (tab === 'dashboard') {
                this.refreshDashboard();
            } else if (tab === 'jobs') {
                this.refreshJobs();
            } else if (tab === 'history') {
                this.refreshHistory();
            } else if (tab === 'settings') {
                this.refreshSettings();
            }
        },

        // Load component content
        async loadDashboard() {
            this.dashboardHtml = '<div class="text-center py-8 text-gray-500">Loading dashboard...</div>';
            try {
                this.dashboardHtml = await renderDashboard();
            } catch (error) {
                this.dashboardHtml = '<div class="text-center py-8 text-red-500">Failed to load dashboard</div>';
                console.error('Dashboard load error:', error);
            }
        },

        async loadJobs() {
            this.jobsHtml = '<div class="text-center py-8 text-gray-500">Loading jobs...</div>';
            try {
                this.jobsHtml = await renderJobs();
            } catch (error) {
                this.jobsHtml = '<div class="text-center py-8 text-red-500">Failed to load jobs</div>';
                console.error('Jobs load error:', error);
            }
        },

        async loadHistory() {
            this.historyHtml = '<div class="text-center py-8 text-gray-500">Loading history...</div>';
            try {
                this.historyHtml = await renderHistory();
            } catch (error) {
                this.historyHtml = '<div class="text-center py-8 text-red-500">Failed to load history</div>';
                console.error('History load error:', error);
            }
        },

        async loadSettings() {
            this.settingsHtml = '<div class="text-center py-8 text-gray-500">Loading settings...</div>';
            try {
                this.settingsHtml = await renderSettings();
            } catch (error) {
                this.settingsHtml = '<div class="text-center py-8 text-red-500">Failed to load settings</div>';
                console.error('Settings load error:', error);
            }
        },

        // Refresh methods
        async refreshDashboard() {
            await this.loadDashboard();
        },

        async refreshJobs() {
            await this.loadJobs();
        },

        async refreshHistory() {
            await this.loadHistory();
        },

        async refreshSettings() {
            await this.loadSettings();
        },

        // Toast notifications
        showToast(message, type = 'info') {
            this.toast.message = message;
            this.toast.type = type;
            this.toast.show = true;

            // Auto-hide after 3 seconds
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        },

        // Utility: API call wrapper
        async apiCall(url, options = {}) {
            try {
                const response = await fetch(url, {
                    ...options,
                    headers: {
                        'Content-Type': 'application/json',
                        ...options.headers
                    }
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'API request failed');
                }

                return await response.json();
            } catch (error) {
                console.error('API call failed:', error);
                this.showToast(error.message || 'Request failed', 'error');
                throw error;
            }
        }
    };
}

// Utility functions
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function formatRelativeTime(dateString) {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' minutes ago';
    if (seconds < 86400) return Math.floor(seconds / 3600) + ' hours ago';
    if (seconds < 604800) return Math.floor(seconds / 86400) + ' days ago';

    return formatDate(dateString);
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function getStatusBadgeClass(status) {
    switch (status) {
        case 'success':
            return 'badge-success';
        case 'failed':
            return 'badge-error';
        case 'running':
            return 'badge-info';
        default:
            return 'badge-gray';
    }
}

function getSourceTypeLabel(type) {
    return type === 'local' ? 'Local' : 'SSH';
}

function getCompressionLabel(format) {
    const labels = {
        'zip': 'ZIP',
        'tar.gz': 'TAR.GZ',
        'tar.bz2': 'TAR.BZ2',
        'tar.xz': 'TAR.XZ',
        'none': 'None'
    };
    return labels[format] || format;
}
