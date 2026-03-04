/**
 * Auto-Bead Bug Reporter
 * Captures DOM and console logs, submits to backend to create beads.
 */

(function() {
    'use strict';
    
    // Store console logs
    const consoleLogs = [];
    
    // Intercept console methods
    const originalConsole = {
        log: console.log,
        warn: console.warn,
        error: console.error,
        info: console.info,
        debug: console.debug
    };
    
    function captureConsole() {
        ['log', 'warn', 'error', 'info', 'debug'].forEach(method => {
            console[method] = function(...args) {
                const entry = {
                    level: method,
                    timestamp: new Date().toISOString(),
                    messages: args.map(arg => {
                        try {
                            if (arg instanceof Error) {
                                return { type: 'error', message: arg.message, stack: arg.stack };
                            }
                            if (typeof arg === 'object') {
                                return { type: 'object', content: JSON.stringify(arg, null, 2) };
                            }
                            return { type: 'string', content: String(arg) };
                        } catch (e) {
                            return { type: 'string', content: String(arg) };
                        }
                    })
                };
                consoleLogs.push(entry);
                originalConsole[method].apply(console, args);
            };
        });
    }
    
    function captureDOM() {
        return document.documentElement.outerHTML;
    }
    
    function getPageContext() {
        return {
            url: window.location.href,
            title: document.title,
            referrer: document.referrer,
            userAgent: navigator.userAgent,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            screen: {
                width: screen.width,
                height: screen.height,
                colorDepth: screen.colorDepth
            },
            timestamp: new Date().toISOString()
        };
    }
    
    function createBugDialog() {
        // Remove existing dialog if present
        const existing = document.getElementById('auto-bead-dialog');
        if (existing) existing.remove();
        
        const dialog = document.createElement('div');
        dialog.id = 'auto-bead-dialog';
        dialog.innerHTML = `
            <style>
                #auto-bead-dialog {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0, 0, 0, 0.7);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                #auto-bead-dialog-content {
                    background: #1e293b;
                    border-radius: 12px;
                    padding: 24px;
                    width: 90%;
                    max-width: 500px;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                }
                #auto-bead-dialog h2 {
                    margin: 0 0 16px 0;
                    color: #f8fafc;
                    font-size: 20px;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                #auto-bead-dialog label {
                    display: block;
                    color: #94a3b8;
                    margin-bottom: 6px;
                    font-size: 14px;
                }
                #auto-bead-dialog textarea {
                    width: 100%;
                    padding: 12px;
                    background: #0f172a;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    color: #f8fafc;
                    font-size: 14px;
                    resize: vertical;
                    min-height: 100px;
                    box-sizing: border-box;
                    font-family: inherit;
                }
                #auto-bead-dialog textarea:focus {
                    outline: none;
                    border-color: #3b82f6;
                }
                #auto-bead-dialog .info {
                    background: #0f172a;
                    border-radius: 8px;
                    padding: 12px;
                    margin-bottom: 16px;
                    font-size: 12px;
                    color: #64748b;
                }
                #auto-bead-dialog .buttons {
                    display: flex;
                    gap: 12px;
                    margin-top: 16px;
                }
                #auto-bead-dialog button {
                    flex: 1;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    border: none;
                    transition: all 0.2s;
                }
                #auto-bead-dialog .btn-submit {
                    background: #3b82f6;
                    color: white;
                }
                #auto-bead-dialog .btn-submit:hover {
                    background: #2563eb;
                }
                #auto-bead-dialog .btn-submit:disabled {
                    background: #475569;
                    cursor: not-allowed;
                }
                #auto-bead-dialog .btn-cancel {
                    background: #334155;
                    color: #94a3b8;
                }
                #auto-bead-dialog .btn-cancel:hover {
                    background: #475569;
                }
                #auto-bead-dialog .spinner {
                    display: inline-block;
                    width: 16px;
                    height: 16px;
                    border: 2px solid #fff;
                    border-top-color: transparent;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                    margin-right: 8px;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                #auto-bead-dialog .success-message {
                    background: #065f46;
                    color: #6ee7b7;
                    padding: 12px;
                    border-radius: 8px;
                    text-align: center;
                }
                #auto-bead-dialog .error-message {
                    background: #7f1d1d;
                    color: #fca5a5;
                    padding: 12px;
                    border-radius: 8px;
                    text-align: center;
                }
            </style>
            <div id="auto-bead-dialog-content">
                <h2>
                    <svg width="24" height="24" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M5.985,3.778l-0.576,-2.149l0.966,-0.258l0.496,1.849c0.72394,-0.29406 1.53406,-0.29406 2.258,0l0.496,-1.85l0.966,0.26l-0.576,2.148c0.605,0.548 0.985,1.34 0.985,2.222h1.616l0.548,-2.044l0.966,0.259l-0.747,2.785h-2.383v1.5h3v1h-3v1.5h2.383l0.747,2.785l-0.966,0.26l-0.548,-2.045h-1.786c-0.42331,1.19948 -1.55702,2.00162 -2.829,2.00162c-1.27198,0 -2.40569,-0.80214 -2.829,-2.00162h-1.789l-0.547,2.044l-0.966,-0.259l0.746,-2.785h2.384v-1.5h-3v-1h3v-1.5h-2.384l-0.746,-2.785l0.966,-0.26l0.547,2.045h1.617c0,-0.882 0.38,-1.674 0.985,-2.222M8,4c-0.53068,-0.0008 -1.03985,0.20966 -1.41509,0.58491c-0.37525,0.37525 -0.5857,0.88442 -0.58491,1.41509v5c0,0.13867 0.01333,0.272 0.04,0.4c0.20447,1.00696 1.13869,1.69515 2.161,1.59188c1.0223,-0.10326 1.80003,-0.96438 1.799,-1.99188v-5c0.0008,-0.53068 -0.20966,-1.03985 -0.58491,-1.41509c-0.37525,-0.37525 -0.88442,-0.5857 -1.41509,-0.58491M8.5,11.5h-1v-5h1z"/>
                    </svg>
                    Report a Bug
                </h2>
                <div class="info">
                    <strong>Captured automatically:</strong><br>
                    • Full page DOM snapshot<br>
                    • JavaScript console logs<br>
                    • Browser context (URL, viewport, user agent)
                </div>
                <div id="auto-bead-form">
                    <label for="bug-description">What's wrong?</label>
                    <textarea id="bug-description" placeholder="Describe the bug or issue you encountered..."></textarea>
                    <div class="buttons">
                        <button type="button" class="btn-cancel" onclick="window._autoBeadClose()">Cancel</button>
                        <button type="button" class="btn-submit" onclick="window._autoBeadSubmit()">Submit Bug Report</button>
                    </div>
                </div>
                <div id="auto-bead-success" style="display: none;">
                    <div class="success-message">
                        <strong>Bug reported successfully!</strong><br>
                        <span id="bead-id"></span>
                    </div>
                    <div class="buttons">
                        <button type="button" class="btn-cancel" onclick="window._autoBeadClose()">Close</button>
                    </div>
                </div>
                <div id="auto-bead-error" style="display: none;">
                    <div class="error-message">
                        <strong>Failed to report bug</strong><br>
                        <span id="error-message"></span>
                    </div>
                    <div class="buttons">
                        <button type="button" class="btn-cancel" onclick="window._autoBeadClose()">Close</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        // Setup global functions
        window._autoBeadClose = function() {
            dialog.remove();
        };
        
        window._autoBeadSubmit = async function() {
            const description = document.getElementById('bug-description').value.trim();
            if (!description) {
                alert('Please describe the bug');
                return;
            }
            
            const submitBtn = dialog.querySelector('.btn-submit');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span>Submitting...';
            
            try {
                // Capture DOM and console
                const domSnapshot = captureDOM();
                const context = getPageContext();
                
                // Make API call
                const response = await fetch('/api/bug-report', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        description: description,
                        dom_snapshot: domSnapshot,
                        console_logs: consoleLogs.slice(0, 100), // Limit to 100 entries
                        context: context
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('auto-bead-form').style.display = 'none';
                    document.getElementById('bead-id').textContent = 'Bead: ' + result.bead_id;
                    document.getElementById('auto-bead-success').style.display = 'block';
                } else {
                    document.getElementById('auto-bead-form').style.display = 'none';
                    document.getElementById('error-message').textContent = result.message || 'Unknown error';
                    document.getElementById('auto-bead-error').style.display = 'block';
                }
            } catch (error) {
                document.getElementById('auto-bead-form').style.display = 'none';
                document.getElementById('error-message').textContent = error.message;
                document.getElementById('auto-bead-error').style.display = 'block';
            }
        };
    }
    
    // Initialize
    function init() {
        captureConsole();
        console.log('[Auto-Bead] Bug reporter initialized');
        
        // Create bug button
        const button = document.createElement('button');
        button.id = 'auto-bead-button';
        button.innerHTML = `<svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor"><path d="M5.985,3.778l-0.576,-2.149l0.966,-0.258l0.496,1.849c0.72394,-0.29406 1.53406,-0.29406 2.258,0l0.496,-1.85l0.966,0.26l-0.576,2.148c0.605,0.548 0.985,1.34 0.985,2.222h1.616l0.548,-2.044l0.966,0.259l-0.747,2.785h-2.383v1.5h3v1h-3v1.5h2.383l0.747,2.785l-0.966,0.26l-0.548,-2.045h-1.786c-0.42331,1.19948 -1.55702,2.00162 -2.829,2.00162c-1.27198,0 -2.40569,-0.80214 -2.829,-2.00162h-1.789l-0.547,2.044l-0.966,-0.259l0.746,-2.785h2.384v-1.5h-3v-1h3v-1.5h-2.384l-0.746,-2.785l0.966,-0.26l0.547,2.045h1.617c0,-0.882 0.38,-1.674 0.985,-2.222M8,4c-0.53068,-0.0008 -1.03985,0.20966 -1.41509,0.58491c-0.37525,0.37525 -0.5857,0.88442 -0.58491,1.41509v5c0,0.13867 0.01333,0.272 0.04,0.4c0.20447,1.00696 1.13869,1.69515 2.161,1.59188c1.0223,-0.10326 1.80003,-0.96438 1.799,-1.99188v-5c0.0008,-0.53068 -0.20966,-1.03985 -0.58491,-1.41509c-0.37525,-0.37525 -0.88442,-0.5857 -1.41509,-0.58491M8.5,11.5h-1v-5h1z"/></svg>`;
        button.setAttribute('title', 'Report a bug');
        
        // Style the button
        button.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: #dc2626;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
            z-index: 999998;
            transition: transform 0.2s, box-shadow 0.2s;
            color: white;
        `;
        
        button.onmouseenter = function() {
            this.style.transform = 'scale(1.1)';
            this.style.boxShadow = '0 6px 16px rgba(220, 38, 38, 0.5)';
        };
        
        button.onmouseleave = function() {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 4px 12px rgba(220, 38, 38, 0.4)';
        };
        
        button.onclick = createBugDialog;
        
        document.body.appendChild(button);
    }
    
    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();
