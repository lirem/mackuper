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

        // Component HTML storage (jobs and settings still use HTML string approach)
        jobsHtml: '',
        settingsHtml: '',

        // Component data storage (data-driven approach)
        dashboardData: {
            overview: {
                total_jobs: 0,
                active_jobs: 0,
                last_backup: null,
                scheduler_running: false
            },
            recentActivity: [],
            statistics: {
                total_backups: 0,
                success_rate: 0,
                total_size: 0
            }
        },
        historyData: {
            records: [],
            jobs: [],
            filters: { status: '', job_id: '', days: 7 },
            pagination: { page: 1, limit: 20, total: 0, pages: 0 }
        },

        // Modal state
        historyModalOpen: false,
        historyModalContent: '',
        currentHistoryId: null,

        // Refresh timestamps
        lastDashboardRefresh: Date.now(),
        lastHistoryRefresh: Date.now(),
        isRefreshing: false,

        // Initialization
        async init() {
            // Restore tab from URL hash
            const hash = window.location.hash.substring(1); // Remove '#' prefix
            const validTabs = ['dashboard', 'jobs', 'history', 'settings'];
            if (hash && validTabs.includes(hash)) {
                this.currentTab = hash;
            }

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

            // Listen for browser back/forward navigation
            window.addEventListener('hashchange', () => {
                const newHash = window.location.hash.substring(1);
                if (newHash && validTabs.includes(newHash)) {
                    this.currentTab = newHash;
                } else if (!newHash) {
                    this.currentTab = 'dashboard';
                }
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
            // Update URL hash to persist tab state
            const currentHash = window.location.hash.substring(1);
            if (currentHash !== tab) {
                window.location.hash = tab;
            }

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
            try {
                await renderDashboard();
            } catch (error) {
                console.error('Dashboard load error:', error);
                this.showToast('Failed to load dashboard', 'error');
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
            try {
                await renderHistory();
            } catch (error) {
                console.error('History load error:', error);
                this.showToast('Failed to load history', 'error');
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
            this.isRefreshing = true;
            await this.loadDashboard();
            this.lastDashboardRefresh = Date.now();
            this.isRefreshing = false;
        },

        async refreshJobs() {
            await this.loadJobs();
        },

        async refreshHistory() {
            this.isRefreshing = true;
            await this.loadHistory();
            this.lastHistoryRefresh = Date.now();
            this.isRefreshing = false;
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
        case 'cancelling':
            return 'badge-warning';
        case 'cancelled':
            return 'badge-gray';
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
