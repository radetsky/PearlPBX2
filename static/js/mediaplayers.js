// Глобальна змінна для відстеження поточного аудіо
let currentAudio = null;
let currentPlayer = null;

// Функція для зупинки поточного аудіо
function stopCurrentAudio() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        if (currentPlayer) {
            const btn = currentPlayer.querySelector('button');
            if (btn) btn.textContent = '▶';
            btn.classList.remove('playing');
            resetProgress(currentPlayer);
        }
    }
}

// Скидання прогресу
function resetProgress(player) {
    const progressBar = player.querySelector('.progress-bar, .wave-progress, .material-progress-bar');
    const timeInfo = player.querySelector('.time-info, .duration, .current-time');

    if (progressBar) progressBar.style.width = '0%';
    if (timeInfo) {
        if (timeInfo.classList.contains('current-time')) {
            timeInfo.textContent = '0:00';
        } else {
            timeInfo.textContent = timeInfo.textContent.includes('/') ?
                '0:00 / ' + timeInfo.textContent.split(' / ')[1] : '0:00';
        }
    }
}

// Форматування часу
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Simple Player
function togglePlay(btn) {
    const player = btn.closest('.simple-player');
    const audioSrc = player.dataset.audio;

    if (currentAudio && currentPlayer === player && !currentAudio.paused) {
        currentAudio.pause();
        btn.textContent = '▶';
        return;
    }

    stopCurrentAudio();

    currentAudio = new Audio(audioSrc);
    currentPlayer = player;

    currentAudio.addEventListener('loadedmetadata', () => {
        const timeInfo = player.querySelector('.time-info');
        timeInfo.textContent = `0:00 / ${formatTime(currentAudio.duration)}`;
    });

    currentAudio.addEventListener('timeupdate', () => {
        const progress = (currentAudio.currentTime / currentAudio.duration) * 100;
        const progressBar = player.querySelector('.progress-bar');
        const timeInfo = player.querySelector('.time-info');

        progressBar.style.width = progress + '%';
        timeInfo.textContent = `${formatTime(currentAudio.currentTime)} / ${formatTime(currentAudio.duration)}`;
    });

    currentAudio.addEventListener('ended', () => {
        btn.textContent = '▶';
        resetProgress(player);
    });

    currentAudio.play();
    btn.textContent = '⏸';
}

function setProgress(event, container) {
    if (!currentAudio) return;

    const rect = container.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    currentAudio.currentTime = percent * currentAudio.duration;
}

// Compact Player
function toggleCompactPlay(player) {
    const btn = player.querySelector('.compact-btn');
    const audioSrc = player.dataset.audio;

    if (currentAudio && currentPlayer === player && !currentAudio.paused) {
        currentAudio.pause();
        btn.textContent = '▶';
        return;
    }

    stopCurrentAudio();

    currentAudio = new Audio(audioSrc);
    currentPlayer = player;

    currentAudio.addEventListener('ended', () => {
        btn.textContent = '▶';
    });

    currentAudio.play();
    btn.textContent = '⏸';
}

// Wave Player
function toggleWavePlay(btn) {
    const player = btn.closest('.wave-player');
    const audioSrc = player.dataset.audio;

    if (currentAudio && currentPlayer === player && !currentAudio.paused) {
        currentAudio.pause();
        btn.textContent = '▶';
        btn.classList.remove('playing');
        return;
    }

    stopCurrentAudio();

    currentAudio = new Audio(audioSrc);
    currentPlayer = player;

    currentAudio.addEventListener('loadedmetadata', () => {
        const duration = player.querySelector('.duration');
        duration.textContent = formatTime(currentAudio.duration);
    });

    currentAudio.addEventListener('timeupdate', () => {
        const progress = (currentAudio.currentTime / currentAudio.duration) * 100;
        const progressBar = player.querySelector('.wave-progress');
        const duration = player.querySelector('.duration');

        progressBar.style.width = progress + '%';
        duration.textContent = formatTime(currentAudio.currentTime);
    });

    currentAudio.addEventListener('ended', () => {
        btn.textContent = '▶';
        btn.classList.remove('playing');
        resetProgress(player);
    });

    currentAudio.play();
    btn.textContent = '⏸';
    btn.classList.add('playing');
}

function setWaveProgress(event, container) {
    if (!currentAudio) return;

    const rect = container.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    currentAudio.currentTime = percent * currentAudio.duration;
}

// Material Player
function toggleMaterialPlay(btn) {
    const player = btn.closest('.material-player');
    const audioSrc = player.dataset.audio;

    if (currentAudio && currentPlayer === player && !currentAudio.paused) {
        currentAudio.pause();
        btn.textContent = '▶';
        return;
    }

    stopCurrentAudio();

    currentAudio = new Audio(audioSrc);
    currentPlayer = player;

    currentAudio.addEventListener('loadedmetadata', () => {
        const totalTime = player.querySelector('.total-time');
        totalTime.textContent = formatTime(currentAudio.duration);
    });

    currentAudio.addEventListener('timeupdate', () => {
        const progress = (currentAudio.currentTime / currentAudio.duration) * 100;
        const progressBar = player.querySelector('.material-progress-bar');
        const currentTime = player.querySelector('.current-time');

        progressBar.style.width = progress + '%';
        currentTime.textContent = formatTime(currentAudio.currentTime);
    });

    currentAudio.addEventListener('ended', () => {
        btn.textContent = '▶';
        resetProgress(player);
    });

    currentAudio.play();
    btn.textContent = '⏸';
}

function setMaterialProgress(event, container) {
    if (!currentAudio) return;

    const rect = container.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    currentAudio.currentTime = percent * currentAudio.duration;
}
