// Settings component
async function renderSettings() {
    try {
        // Fetch AWS settings and app info
        const [awsSettings, appInfo] = await Promise.all([
            fetch('/api/settings/aws').then(r => r.json()),
            fetch('/api/settings/about').then(r => r.json())
        ]);

        return `
            <div class="space-y-6">
                <h1 class="page-header">Settings</h1>

                <!-- AWS Settings Card -->
                <div class="card">
                    <h2 class="card-header">AWS S3 Configuration</h2>

                    <form onsubmit="saveAWSSettings(event)" class="space-y-4">
                        <div>
                            <label class="form-label">AWS Access Key ID *</label>
                            <input type="text" class="form-input" name="access_key"
                                   placeholder="Leave blank to keep existing"
                                   autocomplete="off">
                            <p class="text-xs text-gray-500 mt-1">Current: ${awsSettings.access_key_hint || 'Not set'}</p>
                        </div>

                        <div>
                            <label class="form-label">AWS Secret Access Key *</label>
                            <input type="password" class="form-input" name="secret_key"
                                   placeholder="Leave blank to keep existing"
                                   autocomplete="new-password">
                            <p class="text-xs text-gray-500 mt-1">Current: ${awsSettings.secret_key_hint || 'Not set'}</p>
                        </div>

                        <div>
                            <label class="form-label">S3 Bucket Name *</label>
                            <input type="text" class="form-input" name="bucket_name"
                                   value="${escapeHtml(awsSettings.bucket_name || '')}"
                                   required>
                        </div>

                        <div>
                            <label class="form-label">AWS Region *</label>
                            <select class="form-select" name="region" required>
                                <option value="us-east-1" ${awsSettings.region === 'us-east-1' ? 'selected' : ''}>US East (N. Virginia) - us-east-1</option>
                                <option value="us-east-2" ${awsSettings.region === 'us-east-2' ? 'selected' : ''}>US East (Ohio) - us-east-2</option>
                                <option value="us-west-1" ${awsSettings.region === 'us-west-1' ? 'selected' : ''}>US West (N. California) - us-west-1</option>
                                <option value="us-west-2" ${awsSettings.region === 'us-west-2' ? 'selected' : ''}>US West (Oregon) - us-west-2</option>
                                <option value="eu-west-1" ${awsSettings.region === 'eu-west-1' ? 'selected' : ''}>EU (Ireland) - eu-west-1</option>
                                <option value="eu-central-1" ${awsSettings.region === 'eu-central-1' ? 'selected' : ''}>EU (Frankfurt) - eu-central-1</option>
                                <option value="ap-southeast-1" ${awsSettings.region === 'ap-southeast-1' ? 'selected' : ''}>Asia Pacific (Singapore) - ap-southeast-1</option>
                                <option value="ap-northeast-1" ${awsSettings.region === 'ap-northeast-1' ? 'selected' : ''}>Asia Pacific (Tokyo) - ap-northeast-1</option>
                            </select>
                        </div>

                        <div class="flex gap-3">
                            <button type="submit" class="btn-primary">
                                Save AWS Settings
                            </button>
                            <button type="button" onclick="testAWSConnection()" class="btn-secondary">
                                Test Connection
                            </button>
                        </div>
                    </form>

                    <div id="awsTestResult" class="mt-4"></div>
                </div>

                <!-- Change Password Card -->
                <div class="card">
                    <h2 class="card-header">Change Password</h2>

                    <form onsubmit="changePassword(event)" class="space-y-4">
                        <div>
                            <label class="form-label">Current Password *</label>
                            <input type="password" class="form-input" name="current_password" required autocomplete="current-password">
                        </div>

                        <div>
                            <label class="form-label">New Password *</label>
                            <input type="password" class="form-input" name="new_password" required autocomplete="new-password">
                            <p class="text-xs text-gray-500 mt-1">Minimum 8 characters, with uppercase, lowercase, and digit</p>
                        </div>

                        <div>
                            <label class="form-label">Confirm New Password *</label>
                            <input type="password" class="form-input" name="confirm_password" required autocomplete="new-password">
                        </div>

                        <button type="submit" class="btn-primary">
                            Change Password
                        </button>
                    </form>
                </div>

                <!-- About Card -->
                <div class="card">
                    <h2 class="card-header">About Mackuper</h2>

                    <div class="space-y-3 text-sm">
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <span class="text-gray-500">Version:</span>
                                <span class="ml-2 font-medium">${appInfo.version || '1.0.0'}</span>
                            </div>
                            <div>
                                <span class="text-gray-500">Python Version:</span>
                                <span class="ml-2 font-medium">${appInfo.python_version || 'N/A'}</span>
                            </div>
                            <div>
                                <span class="text-gray-500">Database:</span>
                                <span class="ml-2 font-medium">SQLite</span>
                            </div>
                            <div>
                                <span class="text-gray-500">Scheduler:</span>
                                <span class="ml-2 font-medium">APScheduler</span>
                            </div>
                        </div>

                        <div class="pt-4 border-t border-gray-200">
                            <p class="text-gray-600">
                                Mackuper is a Docker-based backup solution for backing up local and remote (SSH)
                                files/directories to AWS S3. Designed for simplicity, reliability, and resource efficiency.
                            </p>
                        </div>

                        <div class="pt-2">
                            <p class="text-xs text-gray-500">
                                © 2025 Mackuper. Open source backup tool.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Settings render error:', error);
        return `
            <div class="alert alert-error">
                Failed to load settings. Please refresh the page.
            </div>
        `;
    }
}

async function saveAWSSettings(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const data = {
        bucket_name: formData.get('bucket_name'),
        region: formData.get('region')
    };

    // Only include credentials if provided
    const accessKey = formData.get('access_key');
    const secretKey = formData.get('secret_key');

    if (accessKey && accessKey.trim()) {
        data.access_key = accessKey;
    }
    if (secretKey && secretKey.trim()) {
        data.secret_key = secretKey;
    }

    try {
        const response = await fetch('/api/settings/aws', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save AWS settings');
        }

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast('AWS settings saved successfully', 'success');
        app.refreshSettings();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function testAWSConnection() {
    const resultDiv = document.getElementById('awsTestResult');
    resultDiv.innerHTML = '<div class="alert alert-info">Testing connection...</div>';

    try {
        const response = await fetch('/api/settings/aws/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})  // Send empty JSON object
        });

        // Check if response is JSON before parsing
        const contentType = response.headers.get('content-type');

        if (!contentType || !contentType.includes('application/json')) {
            // Server returned non-JSON response (likely HTML error page)
            const text = await response.text();
            console.error('Non-JSON response:', text);

            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    <strong>✗ Test failed</strong><br>
                    Server error (${response.status}). Please check server logs for details.<br>
                    <details class="mt-2">
                        <summary class="cursor-pointer text-xs hover:text-gray-700">Show raw response</summary>
                        <pre class="text-xs mt-1 p-2 bg-gray-100 rounded overflow-auto max-h-40">${escapeHtml(text.substring(0, 500))}</pre>
                    </details>
                </div>
            `;
            return;
        }

        // Parse JSON response
        let result;
        try {
            result = await response.json();
        } catch (parseError) {
            console.error('JSON parse error:', parseError);
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    <strong>✗ Test failed</strong><br>
                    Invalid JSON response from server. Please check server logs.
                </div>
            `;
            return;
        }

        // Display result based on response status
        if (response.ok) {
            resultDiv.innerHTML = `
                <div class="alert alert-success">
                    <strong>✓ Connection successful!</strong><br>
                    ${result.message || 'AWS S3 connection is working correctly.'}
                </div>
            `;
        } else {
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    <strong>✗ Connection failed</strong><br>
                    ${result.error || 'Unable to connect to AWS S3. Please check your credentials.'}
                </div>
            `;
        }
    } catch (error) {
        console.error('Network error:', error);
        resultDiv.innerHTML = `
            <div class="alert alert-error">
                <strong>✗ Test failed</strong><br>
                Network error: ${error.message}<br>
                <span class="text-xs text-gray-600">Check your internet connection and try again.</span>
            </div>
        `;
    }
}

async function changePassword(event) {
    event.preventDefault();
    const formData = new FormData(event.target);

    const newPassword = formData.get('new_password');
    const confirmPassword = formData.get('confirm_password');

    // Validate passwords match
    if (newPassword !== confirmPassword) {
        alert('New passwords do not match');
        return;
    }

    const data = {
        current_password: formData.get('current_password'),
        new_password: newPassword
    };

    try {
        const response = await fetch('/api/settings/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to change password');
        }

        const app = Alpine.$data(document.querySelector('[x-data]'));
        app.showToast('Password changed successfully', 'success');

        // Reset form
        event.target.reset();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}
