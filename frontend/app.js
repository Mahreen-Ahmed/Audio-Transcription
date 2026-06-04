document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');
    const dropZone = document.getElementById('drop-zone');
    const jobsContainer = document.getElementById('jobs-container');

    // Drag and drop event listeners
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);
    fileInput.addEventListener('change', handleFilesSelect, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    function handleFilesSelect(e) {
        const files = e.target.files;
        handleFiles(files);
    }

    function handleFiles(files) {
        ([...files]).forEach(uploadFile);
    }

    async function uploadFile(file) {
        // Create a temporary ID for the UI before we get the real job ID
        const tempId = 'temp-' + Math.random().toString(36).substring(7);
        createJobCard(tempId, file.name);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/v1/transcriptions', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Upload failed');
            
            const data = await response.json();
            
            // Update the UI card with the real job ID
            updateJobCardId(tempId, data.job_id);
            
            // Start polling for this job
            pollJobStatus(data.job_id);
            
        } catch (error) {
            console.error('Error uploading file:', error);
            updateJobCardStatus(tempId, 'failed', 'Upload failed');
        }
    }

    async function pollJobStatus(jobId) {
        try {
            const response = await fetch(`/api/v1/transcriptions/${jobId}`);
            if (!response.ok) throw new Error('Failed to fetch status');
            
            const data = await response.json();
            
            updateJobCardStatus(jobId, data.status, data.transcript, data.duration_seconds);

            if (data.status === 'pending' || data.status === 'processing') {
                // Poll again in 3 seconds
                setTimeout(() => pollJobStatus(jobId), 3000);
            }
        } catch (error) {
            console.error('Error polling job:', error);
            // Optionally could retry or mark failed
        }
    }

    function createJobCard(id, filename) {
        const card = document.createElement('div');
        card.className = 'job-card glass-panel';
        card.id = `job-${id}`;
        
        card.innerHTML = `
            <div class="job-header">
                <div class="job-info">
                    <div class="job-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
                    </div>
                    <span class="job-filename">${filename}</span>
                </div>
                <span class="job-status-badge status-pending" id="badge-${id}">
                    PENDING
                </span>
            </div>
            <div class="job-body" id="body-${id}" style="display: none;">
                <!-- Transcript will appear here -->
            </div>
        `;
        
        // Add new jobs at the top
        jobsContainer.insertBefore(card, jobsContainer.firstChild);
    }

    function updateJobCardId(oldId, newId) {
        const card = document.getElementById(`job-${oldId}`);
        if (card) {
            card.id = `job-${newId}`;
            card.querySelector(`#badge-${oldId}`).id = `badge-${newId}`;
            card.querySelector(`#body-${oldId}`).id = `body-${newId}`;
        }
    }

    function updateJobCardStatus(id, status, transcript = null, duration = null) {
        const card = document.getElementById(`job-${id}`);
        if (!card) return;

        const badge = card.querySelector(`#badge-${id}`);
        const body = card.querySelector(`#body-${id}`);

        // Update badge class and text
        badge.className = `job-status-badge status-${status}`;
        
        if (status === 'processing') {
            badge.innerHTML = `PROCESSING <span class="processing-indicator"><span></span><span></span><span></span></span>`;
        } else {
            badge.textContent = status.toUpperCase();
        }

        // Handle completed state
        if (status === 'completed' && transcript) {
            body.style.display = 'block';
            body.innerHTML = `
                <textarea class="transcript-area" readonly>${transcript}</textarea>
                <div class="transcript-meta">
                    ${duration ? `<span>⏱️ ${duration.toFixed(2)}s audio</span>` : ''}
                    <span>✅ Transcribed</span>
                </div>
            `;
        } else if (status === 'failed') {
            body.style.display = 'block';
            body.innerHTML = `
                <div style="color: var(--error); padding: 1rem; background: rgba(239, 68, 68, 0.1); border-radius: 8px;">
                    Transcription failed. Please try again.
                </div>
            `;
        }
    }
});
