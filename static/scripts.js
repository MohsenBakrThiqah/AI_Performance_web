document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Form submission handling with loading indicators
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                    Processing...
                `;
            }

            // Special handling for Postman analysis form
            if (this.id === 'analyzeForm') {
                localStorage.setItem('analysisInProgress', 'true');
            }
        });
    });

    // Tab persistence
    const tabEls = document.querySelectorAll('button[data-bs-toggle="tab"]');
    tabEls.forEach(tabEl => {
        tabEl.addEventListener('click', function() {
            localStorage.setItem('activeTab', this.getAttribute('data-bs-target'));
        });
    });

    const activeTab = localStorage.getItem('activeTab');
    if (activeTab) {
        const tab = new bootstrap.Tab(document.querySelector(`[data-bs-target="${activeTab}"]`));
        tab.show();
    }

    // Postman Analysis Specific Functionality
    const analyzeForm = document.getElementById('analyzeForm');
    const claudeButton = document.getElementById('claudeButton');

    // Enable Claude button if analysis results are shown
    if (document.querySelector('#analysisAccordion') && claudeButton) {
        claudeButton.disabled = false;
    }

    // Handle Claude button click
    if (claudeButton) {
        claudeButton.addEventListener('click', function(e) {
            if (this.disabled) return;

            const fileInput = document.querySelector('#analyzeForm input[type="file"]');
            if (!fileInput || !fileInput.files.length) {
                alert('Please analyze a Postman collection first');
                return;
            }

            // Create FormData with the analyzed file
            const formData = new FormData();
            formData.append('postman_file', fileInput.files[0]);

            // Show loading state
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Generating...';
            this.disabled = true;

            // Make AJAX request to generate JMX with Claude
            fetch('/generate_jmx_with_claude', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => { throw err; });
                }
                return response.blob();
            })
            .then(blob => {
                // Create download link
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `claude_${fileInput.files[0].name.replace('.json', '.jmx')}`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
            })
            .catch(error => {
                console.error('Error:', error);
                alert(error.error || 'Failed to generate JMX file');
            })
            .finally(() => {
                this.innerHTML = '<i class="bi bi-robot"></i> Generate with Claude AI';
                this.disabled = false;
            });
        });
    }

    // Dynamic form field handling for findings
    const findingsContainer = document.getElementById('findingsContainer');
    if (findingsContainer) {
        // Add new finding field
        document.getElementById('addFindingBtn').addEventListener('click', function() {
            const findingCount = document.querySelectorAll('.finding-field').length + 1;
            const newField = document.createElement('div');
            newField.className = 'mb-3 finding-field';
            newField.innerHTML = `
                <label for="finding_${findingCount}" class="form-label">Finding ${findingCount}</label>
                <div class="input-group">
                    <input type="text" class="form-control" id="finding_${findingCount}" name="finding_${findingCount}">
                    <button type="button" class="btn btn-outline-danger remove-finding" data-bs-toggle="tooltip" title="Remove finding">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
            findingsContainer.appendChild(newField);

            // Initialize tooltip for new button
            new bootstrap.Tooltip(newField.querySelector('.remove-finding'));
        });

        // Remove finding field
        findingsContainer.addEventListener('click', function(e) {
            if (e.target.classList.contains('remove-finding') || e.target.closest('.remove-finding')) {
                const fieldToRemove = e.target.closest('.finding-field');
                if (fieldToRemove) {
                    fieldToRemove.remove();
                    // Renumber remaining fields
                    const remainingFields = document.querySelectorAll('.finding-field');
                    remainingFields.forEach((field, index) => {
                        const label = field.querySelector('label');
                        const input = field.querySelector('input');
                        const newNum = index + 1;
                        label.textContent = `Finding ${newNum}`;
                        label.htmlFor = `finding_${newNum}`;
                        input.id = `finding_${newNum}`;
                        input.name = `finding_${newNum}`;
                    });
                }
            }
        });
    }

    // File upload preview and validation
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            const file = this.files[0];
            if (!file) return;

            const feedbackEl = document.createElement('div');
            feedbackEl.className = 'mt-2 small';

            // Check file size
            const maxSize = this.getAttribute('data-max-size') || 16777216; // Default 16MB
            if (file.size > maxSize) {
                feedbackEl.className += ' text-danger';
                feedbackEl.textContent = `File too large (max ${formatFileSize(maxSize)})`;
                this.value = '';
            } else {
                feedbackEl.className += ' text-success';
                feedbackEl.textContent = `Selected: ${file.name} (${formatFileSize(file.size)})`;
            }

            // Remove any existing feedback
            const existingFeedback = this.nextElementSibling;
            if (existingFeedback && existingFeedback.classList.contains('file-feedback')) {
                existingFeedback.remove();
            }

            feedbackEl.classList.add('file-feedback');
            this.parentNode.insertBefore(feedbackEl, this.nextElementSibling);
        });
    });

    // Correlation results expand/collapse
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('toggle-correlation-details')) {
            e.preventDefault();
            const detailsEl = e.target.closest('.correlation-result').querySelector('.correlation-details');
            detailsEl.classList.toggle('d-none');
            e.target.textContent = detailsEl.classList.contains('d-none') ? 'Show Details' : 'Hide Details';
        }
    });

    // Auto-format URLs in correlation results
    const urlElements = document.querySelectorAll('.url-display');
    urlElements.forEach(el => {
        const url = el.textContent.trim();
        if (url) {
            el.innerHTML = '';
            const a = document.createElement('a');
            a.href = url;
            a.textContent = url;
            a.target = '_blank';
            el.appendChild(a);
        }
    });

    // JSON syntax highlighting
    document.querySelectorAll('.json-display').forEach(el => {
        try {
            const json = JSON.parse(el.textContent);
            el.textContent = '';
            el.appendChild(syntaxHighlight(json));
        } catch (e) {
            console.error('Error parsing JSON:', e);
        }
    });

    // Responsive table handling
    const tables = document.querySelectorAll('.table-responsive table');
    tables.forEach(table => {
        makeTableResponsive(table);
    });

    // Chaos Experiments dynamic fields (Report Generator)
    (function initChaosExperiments(){
        const select = document.getElementById('chaos_experiments_count');
        const container = document.getElementById('chaosExperimentsContainer');
        const generateBtn = document.getElementById('generateChaosBtn');
        if(!select || !container || !generateBtn) return; // Not on this page

        function buildExperiment(index){
            return `\n<div class="chaos-exp-card">\n  <h5>Experiment #${index}</h5>\n  <div class=\"mb-3\">\n    <label class=\"form-label\" for=\"chaos_experiment_${index}_title\">Title <span class=\"text-danger\">*</span></label>\n    <input type=\"text\" class=\"form-control\" id=\"chaos_experiment_${index}_title\" name=\"chaos_experiment_${index}_title\" required />\n  </div>\n  <div class=\"mb-3\">\n    <label class=\"form-label\" for=\"chaos_experiment_${index}_status\">Status <span class=\"text-danger\">*</span></label>\n    <select class=\"form-select\" id=\"chaos_experiment_${index}_status\" name=\"chaos_experiment_${index}_status\" required>\n      <option value=\"\">Select...</option>\n      <option value=\"Passed\">Passed</option>\n      <option value=\"Partially Passed\">Partially Passed</option>\n      <option value=\"Failed\">Failed</option>\n    </select>\n  </div>\n  <div class=\"mb-3\">\n    <label class=\"form-label\" for=\"chaos_experiment_${index}_description\">Description <span class=\"text-danger\">*</span></label>\n    <textarea class=\"form-control\" rows=\"4\" id=\"chaos_experiment_${index}_description\" name=\"chaos_experiment_${index}_description\" required></textarea>\n  </div>\n</div>`;
        }
        function render(){
            const count = parseInt(select.value || '0', 10);
            container.innerHTML='';
            if(count > 0){
                container.classList.remove('d-none');
                for(let i=1;i<=count;i++) container.insertAdjacentHTML('beforeend', buildExperiment(i));
                const collapseEl = document.getElementById('chaosExperimentsWrapper');
                if (collapseEl) bootstrap.Collapse.getOrCreateInstance(collapseEl, {toggle:false}).show();
            } else {
                container.classList.add('d-none');
            }
        }
        generateBtn.addEventListener('click', render);
    })();
});

// Helper functions
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const val = (bytes / Math.pow(k, i)).toFixed(2);
    return `${val} ${sizes[i]}`;
}

function syntaxHighlight(json) {
    if (typeof json !== 'string') {
        json = JSON.stringify(json, null, 2);
    }
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const regex = /(\"(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\\"])*\"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g;
    return json.replace(regex, function (match) {
        let cls = 'text-dark';
        if (/^\"/.test(match)) {
            if (/\:$/.test(match)) {
                cls = 'text-primary';
            } else {
                cls = 'text-success';
            }
        } else if (/true|false/.test(match)) {
            cls = 'text-info';
        } else if (/null/.test(match)) {
            cls = 'text-warning';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

function makeTableResponsive(table) {
    const headers = [].slice.call(table.querySelectorAll('th'));
    const rows = [].slice.call(table.querySelectorAll('tbody tr'));

    rows.forEach(row => {
        const cells = [].slice.call(row.querySelectorAll('td'));
        cells.forEach((cell, i) => {
            const headerText = headers[i] ? headers[i].textContent : '';
            cell.setAttribute('data-label', headerText);
        });
    });
}