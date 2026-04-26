document.addEventListener('DOMContentLoaded', () => {
    const input       = document.getElementById('query-input');
    const btn         = document.getElementById('search-btn');
    const loader      = document.getElementById('loader');
    const results     = document.getElementById('results');
    const llmOutput   = document.getElementById('llm-output');
    const codeSnippets = document.getElementById('code-snippets');

    const subtitleEl = document.getElementById('subtitle-text');
    const phrases = [
        'Universal Local Code Intelligence Engine.',
        'Ask anything. Trace everything.',
        'Your codebase. Fully understood.',
        'Semantic search. Zero cloud.',
    ];
    let phraseIdx = 0, charIdx = 0, deleting = false;

    const cursorEl = document.createElement('span');
    cursorEl.id = 'subtitle-cursor';
    subtitleEl.insertAdjacentElement('afterend', cursorEl);

    function typewriter() {
        const current = phrases[phraseIdx];
        if (!deleting) {
            charIdx++;
            subtitleEl.textContent = current.slice(0, charIdx);
            if (charIdx === current.length) {
                deleting = true;
                setTimeout(typewriter, 2200);
                return;
            }
            setTimeout(typewriter, 48);
        } else {
            charIdx--;
            subtitleEl.textContent = current.slice(0, charIdx);
            if (charIdx === 0) {
                deleting = false;
                phraseIdx = (phraseIdx + 1) % phrases.length;
                setTimeout(typewriter, 400);
                return;
            }
            setTimeout(typewriter, 28);
        }
    }
    setTimeout(typewriter, 600);

    function revealWords(container) {
        const html = container.innerHTML;

        function wrapTextNodes(node, delay) {
            if (node.nodeType === Node.TEXT_NODE) {
                const words = node.textContent.split(/(\s+)/);
                const frag = document.createDocumentFragment();
                words.forEach((w, i) => {
                    if (/^\s+$/.test(w)) {
                        frag.appendChild(document.createTextNode(w));
                    } else {
                        const s = document.createElement('span');
                        s.textContent = w;
                        s.style.animationDelay = (delay.val * 30) + 'ms';
                        delay.val++;
                        frag.appendChild(s);
                    }
                });
                node.replaceWith(frag);
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                [...node.childNodes].forEach(child => wrapTextNodes(child, delay));
            }
        }
        container.classList.add('word-reveal');
        const delay = { val: 0 };
        [...container.childNodes].forEach(child => wrapTextNodes(child, delay));
    }

    function animateCards() {
        const cards = codeSnippets.querySelectorAll('.snippet-card');
        cards.forEach((card, i) => {
            card.style.animationDelay = (i * 80) + 'ms';
            // trigger reflow then add class
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    card.classList.add('card-visible');
                });
            });
        });
    }

    const search = async () => {
        const query = input.value.trim();
        if (!query) return;

        // reset state
        results.classList.add('hidden');
        loader.classList.remove('hidden');
        llmOutput.innerHTML = '';
        codeSnippets.innerHTML = '';

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query }),
            });

            const data = await response.json();

            if (data.success && data.results.length > 0) {
                llmOutput.innerHTML = marked.parse(data.explanation || 'No explanation synthesized.');
                revealWords(llmOutput);

                data.results.forEach((r) => {
                    const card = document.createElement('div');
                    card.className = 'snippet-card';
                    card.innerHTML = `
                        <div class="snippet-meta">
                            <span class="snippet-file">${r.file} &bull; ${r.name}</span>
                            <span class="snippet-score">Score: ${r.score.toFixed(3)}</span>
                        </div>
                        <div class="snippet-code">
                            <pre><code>${r.code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>
                        </div>
                    `;
                    codeSnippets.appendChild(card);
                });

                loader.classList.add('hidden');
                results.classList.remove('hidden');

                animateCards();

            } else {
                loader.classList.add('hidden');
                alert(data.error || 'No results found. Did you run the codemind index command?');
            }
        } catch (e) {
            loader.classList.add('hidden');
            alert('Error connecting to CodeMind API.');
        }
    };

    btn.addEventListener('click', search);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') search();
    });
});
