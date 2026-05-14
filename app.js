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

    let currentFilepath = '';
    let currentData = [];
    let currentSort = { column: null, direction: 'desc' };

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
                    headers: { 'Content-Type': 'application/json' },
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keywords: finalKeywords })
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
        
        // Trigger file download
        window.location.href = `/api/download?filepath=${encodeURIComponent(currentFilepath)}`;
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
