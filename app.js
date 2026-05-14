document.addEventListener('DOMContentLoaded', () => {
    const searchBtn = document.getElementById('search-btn');
    const keywordInput = document.getElementById('keyword-input');
    const includeRelated = document.getElementById('include-related');
    
    const progressState = document.getElementById('progress-state');
    const progressText = document.getElementById('progress-text');
    const searchLoader = document.getElementById('search-loader');
    
    const resultsSection = document.getElementById('results-section');
    const resultsBody = document.getElementById('results-body');
    const resultsCount = document.getElementById('results-count');
    
    const saveDriveBtn = document.getElementById('save-drive-btn');

    // Login Elements
    const loginOverlay = document.getElementById('login-overlay');
    const appContainer = document.getElementById('app-container');
    const loginBtn = document.getElementById('login-btn');
    const loginPassword = document.getElementById('login-password');
    const loginError = document.getElementById('login-error');
    const loginLoader = document.getElementById('login-loader');

    let appPassword = sessionStorage.getItem('ytpro_password') || '';
    let currentFilepath = '';
    let currentData = [];
    let currentSort = { column: null, direction: 'desc' };

    // Initial check
    if (appPassword) {
        verifyPassword(appPassword);
    }

    loginBtn.addEventListener('click', async () => {
        const pwd = loginPassword.value.trim();
        if (!pwd) return;
        await verifyPassword(pwd);
    });

    loginPassword.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            const pwd = loginPassword.value.trim();
            if (pwd) await verifyPassword(pwd);
        }
    });

    async function verifyPassword(pwd) {
        loginBtn.disabled = true;
        loginLoader.classList.remove('hidden');
        loginBtn.querySelector('.btn-text').textContent = '確認中...';
        loginError.classList.add('hidden');

        try {
            const res = await fetch('/api/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pwd })
            });
            
            if (res.ok) {
                // Success
                appPassword = pwd;
                sessionStorage.setItem('ytpro_password', pwd);
                loginOverlay.classList.add('hidden');
                appContainer.classList.remove('hidden');
            } else {
                // Failed
                loginError.classList.remove('hidden');
                sessionStorage.removeItem('ytpro_password');
                appPassword = '';
            }
        } catch (e) {
            console.error(e);
            loginError.textContent = '通信エラーが発生しました';
            loginError.classList.remove('hidden');
        } finally {
            loginBtn.disabled = false;
            loginLoader.classList.add('hidden');
            loginBtn.querySelector('.btn-text').textContent = 'ログイン';
        }
    }

    searchBtn.addEventListener('click', async () => {
        const keyword = keywordInput.value.trim();
        if (!keyword) return;

        // Reset UI
        resultsSection.classList.add('hidden');
        searchBtn.disabled = true;
        searchLoader.classList.remove('hidden');
        document.querySelector('.btn-text').textContent = '処理中...';
        
        progressState.classList.remove('hidden');
        
        try {
            let finalKeywords = keyword;
            
            // 1. Suggest API (Optional)
            if (includeRelated.checked) {
                progressText.textContent = '関連キーワードを抽出中...';
                const suggestRes = await fetch('/api/suggest', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'x-app-password': appPassword
                    },
                    body: JSON.stringify({ keyword })
                });
                const suggestData = await suggestRes.json();
                if (suggestData.suggestions && suggestData.suggestions.length > 0) {
                    finalKeywords = `${keyword},${suggestData.suggestions.slice(0, 4).join(',')}`;
                }
            }

            // 2. Extract API
            progressText.textContent = 'YouTubeから動画データを抽出中...';
            const extractRes = await fetch('/api/extract', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'x-app-password': appPassword
                },
                body: JSON.stringify({ 
                    keywords: finalKeywords,
                    date_filter: document.getElementById('date-filter').value
                })
            });
            
            if (!extractRes.ok) throw new Error('Data extraction failed');
            
            const extractData = await extractRes.json();
            currentFilepath = extractData.filepath;
            currentData = extractData.data;
            
            // Populate Table
            resetSortIcons();
            renderTable(currentData);
            
            // Show Results
            progressState.classList.add('hidden');
            resultsSection.classList.remove('hidden');
            
        } catch (error) {
            console.error(error);
            progressText.textContent = 'エラーが発生しました';
            alert('処理中にエラーが発生しました。詳細はコンソールを確認してください。');
        } finally {
            searchBtn.disabled = false;
            searchLoader.classList.add('hidden');
            document.querySelector('.btn-text').textContent = 'リサーチ開始';
        }
    });

    saveDriveBtn.addEventListener('click', () => {
        if (!currentFilepath) return;
        
        // Trigger file download with password
        window.location.href = `/api/download?filepath=${encodeURIComponent(currentFilepath)}&pw=${encodeURIComponent(appPassword)}`;
    });

    function renderTable(data) {
        resultsBody.innerHTML = '';
        resultsCount.textContent = `${data.length}件`;
        
        data.forEach(row => {
            const tr = document.createElement('tr');
            
            const prioClass = `prio-${row['Priority'] ? row['Priority'].toLowerCase() : 'c'}`;
            
            tr.innerHTML = `
                <td><span class="prio-badge ${prioClass}">${row['Priority'] || '-'}</span></td>
                <td class="title-cell" title="${row['Title']}">${row['Title']}</td>
                <td>${row['Channel Name']}</td>
                <td>${Number(row['Views']).toLocaleString()}</td>
                <td>${row['V/S Ratio']}</td>
                <td><a href="${row['URL']}" target="_blank" class="link-btn">見る ↗</a></td>
            `;
            resultsBody.appendChild(tr);
        });
    }

    // Sorting Logic
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            if (!currentData || currentData.length === 0) return;
            
            // Toggle direction
            if (currentSort.column === column) {
                currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
            } else {
                currentSort.column = column;
                currentSort.direction = 'desc'; // Default to desc
            }
            
            // Update icons
            resetSortIcons();
            th.querySelector('.sort-icon').textContent = currentSort.direction === 'asc' ? '▲' : '▼';
            
            // Sort data
            currentData.sort((a, b) => {
                let valA, valB;
                if (column === 'priority') {
                    const priorityWeight = { 'S': 4, 'A': 3, 'B': 2, 'C': 1 };
                    valA = priorityWeight[a['Priority'] || 'C'];
                    valB = priorityWeight[b['Priority'] || 'C'];
                } else if (column === 'views') {
                    valA = Number(a['Views'] || 0);
                    valB = Number(b['Views'] || 0);
                } else if (column === 'vs_ratio') {
                    valA = Number(a['V/S Ratio'] || 0);
                    valB = Number(b['V/S Ratio'] || 0);
                }
                
                if (valA < valB) return currentSort.direction === 'asc' ? -1 : 1;
                if (valA > valB) return currentSort.direction === 'asc' ? 1 : -1;
                return 0;
            });
            
            renderTable(currentData);
        });
    });

    function resetSortIcons() {
        document.querySelectorAll('.sort-icon').forEach(icon => {
            icon.textContent = '↕';
        });
    }
});
