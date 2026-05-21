// Lecture playback — walks chapter manifest events: audio, show_diagram, pause, topic_start.

(() => {
    const params = new URLSearchParams(location.search);
    const chapterId = params.get("chapter");

    if (!chapterId) {
        showChapterList();
        return;
    }
    showPlayer(chapterId);
})();

// ---------------------------------------------------------------------------
// Chapter list (when no ?chapter= present)
// ---------------------------------------------------------------------------

async function showChapterList() {
    document.getElementById("chapter-list").classList.remove("hidden");
    const r = await fetch("/lecture-api/chapters");
    const chapters = await r.json();
    const ul = document.getElementById("chapters-ul");
    if (chapters.length === 0) {
        ul.innerHTML = "<li>No chapters yet. Run ingest-book first.</li>";
        return;
    }
    chapters.forEach(c => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = c.has_manifest
            ? `/?chapter=${encodeURIComponent(c.id)}`
            : "#";
        a.innerHTML = `
            <span class="ch-idx">${c.idx ?? "?"}.</span>
            <span class="ch-title">${escapeHtml(c.title || c.id)}</span>
            <span class="ch-status ${c.has_manifest ? "" : "disabled"}">
                ${c.has_manifest ? "ready" : "no audio yet"}
            </span>
        `;
        if (!c.has_manifest) {
            a.onclick = e => { e.preventDefault(); alert("Chapter manifest missing — re-run ingest without --skip-tts."); };
        }
        li.appendChild(a);
        ul.appendChild(li);
    });
}

// ---------------------------------------------------------------------------
// Player (when ?chapter= is set)
// ---------------------------------------------------------------------------

async function showPlayer(chapterId) {
    document.getElementById("player").classList.remove("hidden");

    const r = await fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`);
    if (!r.ok) {
        document.getElementById("chapter-title").textContent = `Error: ${r.status}`;
        const msg = await r.text();
        document.getElementById("progress").textContent = msg.slice(0, 200);
        return;
    }
    const data = await r.json();

    const els = {
        chapterTitle: document.getElementById("chapter-title"),
        chapterIdx: document.getElementById("chapter-index"),
        topicLabel: document.getElementById("topic-label"),
        boardImg: document.getElementById("board-img"),
        boardEmpty: document.getElementById("board-empty"),
        caption: document.getElementById("diagram-caption"),
        playBtn: document.getElementById("play-btn"),
        progress: document.getElementById("progress"),
        audio: document.getElementById("audio"),
        topicCard: document.getElementById("topic-card"),
        topicCardSection: document.getElementById("topic-card-section"),
        topicCardTitle: document.getElementById("topic-card-title"),
    };

    els.chapterTitle.textContent = data.title;
    els.chapterIdx.textContent = data.chapter_index != null ? `Ch. ${data.chapter_index}` : "";
    els.playBtn.disabled = false;

    const events = data.events;
    const diagrams = data.diagrams;
    const topics = data.topics;

    const totalAudios = events.filter(e => e.type === "audio").length;

    const state = {
        cursor: 0,
        audioIdx: 0,
        currentTopicName: null,
        playing: false,
        aborted: false,
    };

    function updateProgress() {
        const top = state.currentTopicName ? ` · ${state.currentTopicName}` : "";
        els.progress.textContent = `Fragment ${state.audioIdx} of ${totalAudios}${top}`;
    }

    function showDiagram(diagramId) {
        const d = diagrams[diagramId];
        if (!d || !d.url) return;
        hideTopicCard();
        els.boardImg.src = d.url;
        els.boardImg.style.display = "block";
        els.boardEmpty.style.display = "none";
        els.caption.textContent = d.description;
    }

    function clearBoard() {
        els.boardImg.style.display = "none";
        hideTopicCard();
        els.boardEmpty.style.display = "block";
        els.caption.textContent = "";
    }

    function showTopicCard(section, title) {
        els.boardImg.style.display = "none";
        els.boardEmpty.style.display = "none";
        els.caption.textContent = "";
        // Restart the chalk-write animation by re-mounting the elements.
        els.topicCardSection.textContent = section || "";
        els.topicCardTitle.textContent = title || "";
        els.topicCard.classList.remove("visible");
        // Force reflow so the animation replays for each new topic.
        void els.topicCard.offsetWidth;
        els.topicCard.classList.add("visible");
    }

    function hideTopicCard() {
        els.topicCard.classList.remove("visible");
    }

    function setTopic(topicId) {
        const t = topics[topicId];
        state.currentTopicName = t ? t.name : null;
        if (t) {
            els.topicLabel.textContent = `${t.section}  ·  ${t.name}`;
            // Write the section on the chalkboard until the first diagram fires.
            showTopicCard(t.section, t.name);
        } else {
            els.topicLabel.textContent = topicId;
            showTopicCard("", topicId);
        }
    }

    function playAudio(url) {
        return new Promise((resolve) => {
            els.audio.src = url;
            const onEnd = () => { cleanup(); resolve(); };
            const onErr = (e) => { console.warn("audio error", url, e); cleanup(); resolve(); };
            const cleanup = () => {
                els.audio.removeEventListener("ended", onEnd);
                els.audio.removeEventListener("error", onErr);
            };
            els.audio.addEventListener("ended", onEnd);
            els.audio.addEventListener("error", onErr);
            els.audio.play().catch(onErr);
        });
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    async function runOne(ev) {
        switch (ev.type) {
            case "topic_start":
                setTopic(ev.topic_id);
                return;
            case "show_diagram":
                showDiagram(ev.diagram_id);
                return;
            case "pause":
                await sleep(ev.duration_ms);
                return;
            case "audio":
                state.audioIdx++;
                updateProgress();
                await playAudio(ev.url);
                return;
        }
    }

    async function start() {
        if (state.playing) return;
        state.playing = true;
        state.aborted = false;
        els.playBtn.textContent = "❚❚  Pause";
        clearBoard();
        while (state.cursor < events.length && !state.aborted) {
            await runOne(events[state.cursor]);
            state.cursor++;
        }
        state.playing = false;
        els.playBtn.textContent = state.cursor >= events.length ? "↻  Restart" : "▶  Play";
        if (state.cursor >= events.length) {
            els.progress.textContent = "Done.";
        }
    }

    function pause() {
        state.aborted = true;
        state.playing = false;
        els.audio.pause();
        els.playBtn.textContent = "▶  Resume";
    }

    els.playBtn.addEventListener("click", () => {
        if (state.playing) {
            pause();
        } else {
            if (state.cursor >= events.length) {
                state.cursor = 0;
                state.audioIdx = 0;
            }
            start();
        }
    });

    updateProgress();
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
