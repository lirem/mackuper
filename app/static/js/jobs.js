// Cron expression validator — mirrors APScheduler 3.10.4 CronTrigger.from_crontab() grammar.
// Source: apscheduler/triggers/cron/fields.py + expressions.py
// Update this function if APScheduler is upgraded.
function validateCronExpression(expr) {
    if (!expr || !expr.trim()) return 'Cron expression is required';

    const fields = expr.trim().split(/\s+/);
    if (fields.length !== 5) {
        return `Wrong number of fields; got ${fields.length}, expected 5`;
    }

    const FIELD_DEFS = [
        { name: 'minute',      min: 0,  max: 59, names: null },
        { name: 'hour',        min: 0,  max: 23, names: null },
        { name: 'day',         min: 1,  max: 31, names: null, allowLast: true },
        { name: 'month',       min: 1,  max: 12, names: {jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12} },
        { name: 'day_of_week', min: 0,  max: 6,  names: {mon:0,tue:1,wed:2,thu:3,fri:4,sat:5,sun:6} },
    ];

    for (let i = 0; i < 5; i++) {
        const error = validateCronField(fields[i], FIELD_DEFS[i]);
        if (error) return `Field "${FIELD_DEFS[i].name}": ${error}`;
    }
    return null;
}

function parseCronValue(token, field) {
    const lower = token.toLowerCase();
    if (field.names && lower in field.names) return field.names[lower];
    if (/^\d+$/.test(token)) return parseInt(token, 10);
    return NaN;
}

function validateCronField(fieldStr, field) {
    const tokens = fieldStr.split(',');
    for (const token of tokens) {
        const error = validateCronToken(token.trim(), field);
        if (error) return error;
    }
    return null;
}

function validateCronToken(token, field) {
    // AllExpression: * or */N
    if (token === '*') return null;
    if (/^\*\/(\d+)$/.test(token)) {
        const step = parseInt(token.slice(2), 10);
        if (step === 0) return 'Increment must be higher than 0';
        const rangeSize = field.max - field.min;
        if (step > rangeSize) return `Step value (${step}) is higher than the total range (${rangeSize})`;
        return null;
    }

    // last keyword (day field only)
    if (token.toLowerCase() === 'last') {
        if (!field.allowLast) return `Unrecognized expression "${token}"`;
        return null;
    }

    // RangeExpression: N, N-M, N/step, N-M/step
    let base = token, step = null;
    const slashIdx = token.indexOf('/');
    if (slashIdx !== -1) {
        base = token.slice(0, slashIdx);
        const stepStr = token.slice(slashIdx + 1);
        if (!/^\d+$/.test(stepStr)) return `Unrecognized expression "${token}"`;
        step = parseInt(stepStr, 10);
        if (step === 0) return 'Increment must be higher than 0';
    }

    // Parse base: N or N-M
    const dashIdx = base.indexOf('-');
    let first, last;
    if (dashIdx !== -1) {
        const firstStr = base.slice(0, dashIdx);
        const lastStr = base.slice(dashIdx + 1);
        first = parseCronValue(firstStr, field);
        last = parseCronValue(lastStr, field);
        if (isNaN(first)) return `Unrecognized expression "${firstStr}"`;
        if (isNaN(last)) return `Unrecognized expression "${lastStr}"`;
        // Reject numeric-to-name ranges (e.g. "0-mon"), but name-to-numeric (e.g. "mon-5") is valid
        const firstIsName = !!(field.names && firstStr.toLowerCase() in field.names);
        const lastIsName = !!(field.names && lastStr.toLowerCase() in field.names);
        if (!firstIsName && lastIsName) return `Cannot mix named and numeric values in range "${token}"`;
    } else {
        first = parseCronValue(base, field);
        last = null;
        if (isNaN(first)) return `Unrecognized expression "${base}"`;
    }

    // Validate range bounds
    if (first < field.min) return `Value ${first} is lower than the minimum value (${field.min})`;
    if (last !== null) {
        if (last > field.max) return `Value ${last} is higher than the maximum value (${field.max})`;
        if (first > last) return `The minimum value in a range must not be higher than the maximum`;
    } else {
        if (first > field.max) return `Value ${first} is higher than the maximum value (${field.max})`;
    }

    // Validate step against range (N-M/step uses last-first, N/step uses max-first)
    if (step !== null) {
        const rangeSize = last !== null ? (last - first) : (field.max - first);
        if (step > rangeSize) return `Step value (${step}) is higher than the total range of the expression (${rangeSize})`;
    }

    return null;
}

function onCronInput(input) {
    const error = validateCronExpression(input.value);
    const errorEl = document.getElementById('cronError');
    const saveBtn = document.getElementById('saveJobBtn');

    input.classList.toggle('form-input--error', !!error);
    if (errorEl) { errorEl.textContent = error || ''; errorEl.style.display = error ? '' : 'none'; }
    if (saveBtn) saveBtn.disabled = !!error;
}

// Jobs management component
let jobsState = {
    jobs: [],
    showModal: false,
    editingJob: null,
    formData: getEmptyJobForm()
};

function getEmptyJobForm() {
    return {
        name: '',
        description: '',
        enabled: true,
        source_type: 'local',
        source_config: {
            paths: [],
            exclude_patterns: [],
            hostname: '',
            port: 22,
            username: '',
            password: '',
            private_key: ''
        },
        compression_format: 'tar.gz',
        schedule_cron: '0 2 * * *',
        retention_s3_days: 30,
        retention_local_days: 7,
        store_local: false
    };
}

async function renderJobs() {
    try {
        // Fetch jobs
        const response = await fetch('/api/jobs');
        jobsState.jobs = await response.json();

        return `
            <div class="space-y-6">
                <!-- Header with Create Button -->
                <div class="flex justify-between items-center">
                    <h1 class="text-2xl font-bold text-gray-900">Backup Jobs</h1>
                    <button onclick="openJobModal()"
                            class="btn-primary">
                        Create New Job
                    </button>
                </div>

                <!-- Jobs List -->
                ${jobsState.jobs.length === 0 ? `
                    <div class="card">
                        <div class="empty-state">
                            <p class="empty-state-text">No backup jobs created yet</p>
                            <p class="empty-state-subtext">Create your first backup job to get started</p>
                            <button onclick="openJobModal()" class="mt-4 btn-primary btn-sm">
                                Create First Job
                            </button>
                        </div>
                    </div>
                ` : `
                    <div class="grid grid-cols-1 gap-4">
                        ${jobsState.jobs.map(job => renderJobCard(job)).join('')}
                    </div>
                `}

                <!-- Job Modal -->
                <div id="jobModal" class="modal-overlay hidden">
                    <div class="modal-content">
                        <div id="jobModalContent"></div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Jobs render error:', error);
        return `
            <div class="alert alert-error">
                Failed to load jobs. Please refresh the page.
            </div>
        `;
    }
}

function renderJobCard(job) {
    const paths = job.source_config?.paths || [];
    const pathsDisplay = paths.length > 0 ? paths.join(', ') : 'No paths configured';

    return `
        <div class="card">
            <div class="flex justify-between items-start">
                <div class="flex-1">
                    <div class="flex items-center gap-3 mb-2">
                        <h3 class="text-lg font-semibold">${escapeHtml(job.name)}</h3>
                        <span class="badge ${job.enabled ? 'badge-success' : 'badge-gray'}">
                            ${job.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                        <span class="badge badge-info">
                            ${getSourceTypeLabel(job.source_type)}
                        </span>
                    </div>
                    ${job.description ? `<p class="text-gray-600 text-sm mb-3">${escapeHtml(job.description)}</p>` : ''}

                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                            <span class="text-gray-500">Schedule:</span>
                            <p class="font-mono text-gray-900">${escapeHtml(job.schedule_cron)}</p>
                        </div>
                        <div>
                            <span class="text-gray-500">Compression:</span>
                            <p class="text-gray-900">${getCompressionLabel(job.compression_format)}</p>
                        </div>
                        <div>
                            <span class="text-gray-500">S3 Retention:</span>
                            <p class="text-gray-900">${job.retention_s3_days} days</p>
                        </div>
                        <div>
                            <span class="text-gray-500">Paths:</span>
                            <p class="text-gray-900 truncate" title="${escapeHtml(pathsDisplay)}">${escapeHtml(pathsDisplay)}</p>
                        </div>
                    </div>
                    ${job.source_config?.exclude_patterns?.length > 0 ? `<div class="mt-3 text-sm"><span class="text-gray-500">Excludes:</span><p class="text-gray-900 truncate" title="${escapeHtml(job.source_config.exclude_patterns.join(', '))}">${escapeHtml(job.source_config.exclude_patterns.join(', '))}</p></div>` : ''}
                </div>

                <div class="flex flex-col gap-2 ml-4">
                    <button onclick="runJobNow(${job.id})"
                            class="btn-success btn-sm whitespace-nowrap">
                        Run Now
                    </button>
                    <button onclick="toggleJob(${job.id}, ${!job.enabled})"
                            class="btn-secondary btn-sm">
                        ${job.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button onclick="editJob(${job.id})"
                            class="btn-secondary btn-sm">
                        Edit
                    </button>
                    <button onclick="deleteJob(${job.id}, '${escapeHtml(job.name)}')"
                            class="btn-danger btn-sm">
                        Delete
                    </button>
                </div>
            </div>
        </div>
    `;
}

function openJobModal(job = null) {
    jobsState.editingJob = job;
    jobsState.formData = job ? { ...job } : getEmptyJobForm();

    const modal = document.getElementById('jobModal');
    const content = document.getElementById('jobModalContent');
    content.innerHTML = renderJobForm();

    // Wire cron live validator
    const cronInputEl = document.getElementById('cronInput');
    if (cronInputEl) {
        cronInputEl.addEventListener('input', function() { onCronInput(this); });
        onCronInput(cronInputEl); // validate initial value immediately
    }

    modal.classList.remove('hidden');
}

function closeJobModal() {
    document.getElementById('jobModal').classList.add('hidden');
    jobsState.editingJob = null;
    jobsState.formData = getEmptyJobForm();
}

function renderJobForm() {
    const isEdit = jobsState.editingJob !== null;
    const formData = jobsState.formData;

    return `
        <h2 class="text-xl font-bold mb-4">${isEdit ? 'Edit' : 'Create'} Backup Job</h2>

        <form onsubmit="saveJob(event)" class="space-y-4">
            <!-- Basic Info -->
            <div>
                <label class="form-label">Job Name *</label>
                <input type="text" class="form-input" name="name" value="${escapeHtml(formData.name)}" required>
            </div>

            <div>
                <label class="form-label">Description</label>
                <input type="text" class="form-input" name="description" value="${escapeHtml(formData.description || '')}">
            </div>

            <!-- Source Type -->
            <div>
                <label class="form-label">Source Type *</label>
                <select class="form-select" name="source_type" onchange="updateSourceType(this.value)">
                    <option value="local" ${formData.source_type === 'local' ? 'selected' : ''}>Local</option>
                    <option value="ssh" ${formData.source_type === 'ssh' ? 'selected' : ''}>SSH</option>
                </select>
            </div>

            <!-- Source Configuration -->
            <div id="sourceConfig">
                ${formData.source_type === 'local' ? renderLocalSourceForm(formData) : renderSSHSourceForm(formData)}
            </div>

            <!-- Compression -->
            <div>
                <label class="form-label">Compression Format *</label>
                <select class="form-select" name="compression_format">
                    <option value="zip" ${formData.compression_format === 'zip' ? 'selected' : ''}>ZIP</option>
                    <option value="tar.gz" ${formData.compression_format === 'tar.gz' ? 'selected' : ''}>TAR.GZ</option>
                    <option value="tar.bz2" ${formData.compression_format === 'tar.bz2' ? 'selected' : ''}>TAR.BZ2</option>
                    <option value="tar.xz" ${formData.compression_format === 'tar.xz' ? 'selected' : ''}>TAR.XZ</option>
                    <option value="none" ${formData.compression_format === 'none' ? 'selected' : ''}>None</option>
                </select>
            </div>

            <!-- Schedule -->
            <div>
                <label class="form-label">Schedule (Cron) *</label>
                <input type="text" id="cronInput" class="form-input" name="schedule_cron"
                       value="${escapeHtml(formData.schedule_cron)}" required>
                <p class="cron-help">Examples: "0 2 * * *" (daily 2 AM), "0 */6 * * *" (every 6 hours)</p>
                <p id="cronError" class="text-xs text-red-500 mt-1" style="display:none;"></p>
            </div>

            <!-- Retention -->
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="form-label">S3 Retention (days) *</label>
                    <input type="number" class="form-input" name="retention_s3_days" value="${formData.retention_s3_days}" min="1" required>
                </div>
                <div>
                    <label class="form-label">Local Retention (days)</label>
                    <input type="number" class="form-input" name="retention_local_days" value="${formData.retention_local_days}" min="0">
                </div>
            </div>

            <!-- Store Local -->
            <div class="flex items-center">
                <input type="checkbox" id="store_local" name="store_local" ${formData.store_local ? 'checked' : ''} class="mr-2">
                <label for="store_local" class="text-sm text-gray-700">Store backup locally in addition to S3</label>
            </div>

            <!-- Enabled -->
            <div class="flex items-center">
                <input type="checkbox" id="enabled" name="enabled" ${formData.enabled ? 'checked' : ''} class="mr-2">
                <label for="enabled" class="text-sm text-gray-700">Enable job immediately</label>
            </div>

            <!-- Actions -->
            <div class="flex gap-3 pt-4">
                <button type="submit" id="saveJobBtn" class="btn-primary flex-1">
                    ${isEdit ? 'Update' : 'Create'} Job
                </button>
                <button type="button" onclick="closeJobModal()" class="btn-secondary flex-1">
                    Cancel
                </button>
            </div>
        </form>
    `;
}

function renderLocalSourceForm(formData) {
    const paths = formData.source_config?.paths || [];
    const excludePatterns = formData.source_config?.exclude_patterns || [];
    return `
        <div>
            <label class="form-label">Paths to Backup (one per line) *</label>
            <textarea class="form-input" name="paths" rows="4" required>${paths.join('\n')}</textarea>
            <p class="text-xs text-gray-500 mt-1">Example: /path/to/backup</p>
        </div>
        <div class="mt-4">
            <label class="form-label">Exclude Patterns (one per line)</label>
            <textarea class="form-input" name="exclude_patterns" rows="3">${excludePatterns.join('\n')}</textarea>
            <p class="text-xs text-gray-500 mt-1">Glob patterns to exclude files/directories. Examples: *.pyc, node_modules, __pycache__, .venv</p>
        </div>
    `;
}

function renderSSHSourceForm(formData) {
    const paths = formData.source_config?.paths || [];
    const config = formData.source_config || {};

    return `
        <div class="space-y-4 border-l-4 border-blue-200 pl-4">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="form-label">Hostname *</label>
                    <input type="text" class="form-input" name="ssh_hostname" value="${escapeHtml(config.hostname || '')}" required>
                </div>
                <div>
                    <label class="form-label">Port *</label>
                    <input type="number" class="form-input" name="ssh_port" value="${config.port || 22}" required>
                </div>
            </div>

            <div>
                <label class="form-label">Username *</label>
                <input type="text" class="form-input" name="ssh_username" value="${escapeHtml(config.username || '')}" required>
            </div>

            <div>
                <label class="form-label">Password</label>
                <input type="password" class="form-input" name="ssh_password" placeholder="Leave blank to keep existing">
                <p class="text-xs text-gray-500 mt-1">Password or private key required</p>
            </div>

            <div>
                <label class="form-label">Private Key</label>
                <textarea class="form-input" name="ssh_private_key" rows="3" placeholder="-----BEGIN RSA PRIVATE KEY-----"></textarea>
            </div>

            <div>
                <label class="form-label">Remote Paths (one per line) *</label>
                <textarea class="form-input" name="paths" rows="4" required>${paths.join('\n')}</textarea>
                <p class="text-xs text-gray-500 mt-1">Example: /home/user/data</p>
            </div>
        </div>
    `;
}

function updateSourceType(type) {
    jobsState.formData.source_type = type;
    document.getElementById('sourceConfig').innerHTML =
        type === 'local' ? renderLocalSourceForm(jobsState.formData) : renderSSHSourceForm(jobsState.formData);
}

async function saveJob(event) {
    event.preventDefault();

    // Safety guard: block submission if cron is invalid (button should already be disabled)
    const cronInputEl = document.getElementById('cronInput');
    if (cronInputEl) {
        const cronError = validateCronExpression(cronInputEl.value);
        if (cronError) return;
    }

    const formData = new FormData(event.target);
    const isEdit = jobsState.editingJob !== null;

    // Build source_config
    const sourceConfig = {
        paths: formData.get('paths').split('\n').map(p => p.trim()).filter(p => p)
    };

    const sourceType = formData.get('source_type');
    if (sourceType === 'local') {
        const excludePatternsInput = formData.get('exclude_patterns') || '';
        sourceConfig.exclude_patterns = excludePatternsInput.split('\n').map(p => p.trim()).filter(p => p);
    }

    if (sourceType === 'ssh') {
        sourceConfig.hostname = formData.get('ssh_hostname');
        sourceConfig.port = parseInt(formData.get('ssh_port'));
        sourceConfig.username = formData.get('ssh_username');
        sourceConfig.password = formData.get('ssh_password');
        sourceConfig.private_key = formData.get('ssh_private_key');
    }

    const jobData = {
        name: formData.get('name'),
        description: formData.get('description'),
        enabled: formData.get('enabled') === 'on',
        source_type: sourceType,
        source_config: sourceConfig,
        compression_format: formData.get('compression_format'),
        schedule_cron: formData.get('schedule_cron'),
        retention_s3_days: parseInt(formData.get('retention_s3_days')),
        retention_local_days: parseInt(formData.get('retention_local_days')),
        store_local: formData.get('store_local') === 'on'
    };

    try {
        const url = isEdit ? `/api/jobs/${jobsState.editingJob.id}` : '/api/jobs';
        const method = isEdit ? 'PUT' : 'POST';
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(jobData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save job');
        }

        // Show success message
        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(isEdit ? 'Job updated successfully' : 'Job created successfully', 'success');

        // Close modal and refresh
        closeJobModal();
        app.refreshJobs();
    } catch (error) {
        const appRoot = document.querySelector('[x-data]');
        const app = appRoot ? Alpine.$data(appRoot) : null;
        if (app) {
            app.showToast(error.message, 'error');
        } else {
            alert('Error: ' + error.message);
        }
    }
}

async function runJobNow(jobId) {
    if (!confirm('Run this backup job now?')) return;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const response = await fetch(`/api/jobs/${jobId}/run`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        });
        const result = await response.json();

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(result.message || 'Backup started', 'success');

        setTimeout(() => app.refreshJobs(), 1000);
    } catch (error) {
        alert('Failed to run job: ' + error.message);
    }
}

async function toggleJob(jobId, enable) {
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const response = await fetch(`/api/jobs/${jobId}/toggle`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        });
        const result = await response.json();

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(result.message || (enable ? 'Job enabled' : 'Job disabled'), 'success');
        app.refreshJobs();
    } catch (error) {
        alert('Failed to toggle job: ' + error.message);
    }
}

async function editJob(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();
        openJobModal(job);
    } catch (error) {
        alert('Failed to load job: ' + error.message);
    }
}

async function deleteJob(jobId, jobName) {
    if (!confirm(`Delete job "${jobName}"? This will also delete all associated backup history.`)) return;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrfToken }
        });
        const result = await response.json();

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast(result.message || 'Job deleted', 'success');
        app.refreshJobs();
    } catch (error) {
        alert('Failed to delete job: ' + error.message);
    }
}

// Close modal on background click
document.addEventListener('click', (e) => {
    if (e.target.id === 'jobModal') {
        closeJobModal();
    }
});
