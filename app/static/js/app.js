/**
 * HabitFlow Frontend Controller (Single-Owner Authenticated + Multi-Device Sync)
 */

function getMetaContent(name) {
    const el = document.querySelector(`meta[name="${name}"]`);
    return el ? el.getAttribute('content') || '' : '';
}

function getOwnerTodayIso() {
    return getMetaContent('owner-today') || new Date().toISOString().slice(0, 10);
}

const initialDateParts = getOwnerTodayIso().split('-').map(Number);

const state = {
    activeView: 'dashboard',
    habits: [],
    tasks: [],
    dashboard: null,
    calendarYear: initialDateParts[0] || new Date().getFullYear(),
    calendarMonth: initialDateParts[1] || (new Date().getMonth() + 1),
    calendarData: null,
    statsSummary: null,
    statsPeriod: 'weekly',
    csrfToken: getMetaContent('csrf-token'),
};

const VIEW_TITLES = {
    dashboard: 'Фокус на сегодня',
    habits: 'Трекер привычек',
    calendar: 'Календарь выполнения за месяц',
    tasks: 'Ежедневный планировщик задач',
    stats: 'Статистика личной продуктивности',
};

const PRIORITY_LABELS = {
    high: 'Высокий',
    medium: 'Средний',
    low: 'Низкий',
};

const STATUS_LABELS = {
    todo: 'К выполнению',
    in_progress: 'В работе',
    done: 'Выполнено',
};

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function showToast(message, isError = false) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${isError ? 'error' : ''}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3200);
}

async function apiRequest(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }

    const config = {
        credentials: 'same-origin',
        ...options,
        headers,
    };

    const response = await fetch(url, config);
    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Сессия истекла. Выполняется переход на страницу входа...');
    }

    if (response.status === 204) {
        return null;
    }

    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        data = null;
    }

    if (!response.ok) {
        const errMessage = (data && data.detail) ? data.detail : `Ошибка запроса (${response.status})`;
        throw new Error(errMessage);
    }
    return data;
}

function formatCurrentDateHeader() {
    const iso = getOwnerTodayIso();
    const [y, m, d] = iso.split('-').map(Number);
    const dateObj = (y && m && d) ? new Date(y, m - 1, d) : new Date();
    const formatted = dateObj.toLocaleDateString('ru-RU', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });
    const el = document.getElementById('currentDateLabel');
    if (el) {
        el.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
    }
}

async function handleLogout() {
    try {
        await apiRequest('/api/auth/logout', { method: 'POST' });
    } catch (_) {
        // Redirect even if network hiccups
    }
    window.location.href = '/login';
}

/* ======================== НАВИГАЦИЯ ======================== */
function switchView(viewName) {
    state.activeView = viewName;
    document.querySelectorAll('.nav-item, .mobile-nav-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });
    document.querySelectorAll('.view-section').forEach((sec) => {
        sec.classList.toggle('active', sec.id === `view-${viewName}`);
    });
    const titleEl = document.getElementById('pageTitle');
    if (titleEl && VIEW_TITLES[viewName]) {
        titleEl.textContent = VIEW_TITLES[viewName];
    }

    if (viewName === 'dashboard') loadDashboard();
    if (viewName === 'habits') loadHabits();
    if (viewName === 'calendar') loadCalendar();
    if (viewName === 'tasks') loadTasks();
    if (viewName === 'stats') loadStats();
}

/* ======================== 1. ГЛАВНАЯ ПАНЕЛЬ (СЕГОДНЯ) ======================== */
async function loadDashboard() {
    try {
        const data = await apiRequest('/api/stats/dashboard');
        state.dashboard = data;
        renderDashboard(data);
    } catch (err) {
        showToast(err.message, true);
    }
}

function renderDashboard(data) {
    document.getElementById('kpiHabitsToday').textContent = `${data.habits_completed_today} / ${data.habits_total_today}`;
    document.getElementById('kpiHabitsProgressBar').style.width = `${data.habits_progress_percent}%`;
    document.getElementById('kpiHabitsPercent').textContent = `${data.habits_progress_percent}% выполнено за день`;
    document.getElementById('kpiMaxStreak').textContent = `${data.active_streaks_max} дн.`;

    const openTasksCount = data.tasks_today.filter((t) => t.status !== 'done').length;
    document.getElementById('kpiTasksFocus').textContent = `${openTasksCount}`;
    document.getElementById('kpiTasksOverdueFoot').textContent = `Просрочено: ${data.tasks_overdue.length} · Закрыто сегодня: ${data.tasks_done_today_count}`;
    document.getElementById('kpiProductivityScore').textContent = `${data.productivity_score} / 100`;

    // Рендер привычек на сегодня
    const habitsBox = document.getElementById('dashboardHabitsList');
    if (!data.habits_today.length) {
        habitsBox.innerHTML = `
            <div class="empty-state">
                У вас пока нет активных привычек.<br>
                Нажмите <strong>«+ Добавить»</strong> или кнопку <strong>«⚡ Демо-данные»</strong> сверху.
            </div>`;
    } else {
        habitsBox.innerHTML = data.habits_today.map((h) => `
            <div class="habit-row ${h.completed_today ? 'completed' : ''}">
                <div class="habit-left">
                    <button class="check-btn ${h.completed_today ? 'checked' : ''}"
                            onclick="handleToggleHabitToday(${h.id}, '${data.today}')"
                            title="Отметить за сегодня">
                        ${h.completed_today ? '✓' : ''}
                    </button>
                    <div class="item-info">
                        <div class="item-title">
                            <span>${escapeHtml(h.icon)}</span>
                            <span>${escapeHtml(h.name)}</span>
                        </div>
                        ${h.description ? `<div class="item-desc">${escapeHtml(h.description)}</div>` : ''}
                    </div>
                </div>
                <div class="streak-pill" title="Текущая непрерывная серия">
                    🔥 ${h.current_streak} дн.
                </div>
            </div>
        `).join('');
    }

    // Блок просроченных задач
    const overdueBanner = document.getElementById('dashboardOverdueBlock');
    if (data.tasks_overdue.length > 0) {
        overdueBanner.classList.remove('hidden');
        overdueBanner.innerHTML = `
            <div class="overdue-banner-title">⚠️ Просроченные задачи (${data.tasks_overdue.length})</div>
            <div class="item-list">
                ${data.tasks_overdue.map((t) => renderTaskRowHtml(t)).join('')}
            </div>
        `;
    } else {
        overdueBanner.classList.add('hidden');
        overdueBanner.innerHTML = '';
    }

    // Задачи на сегодня и ближайшие
    const tasksBox = document.getElementById('dashboardTasksList');
    const combinedTasks = [...data.tasks_today, ...data.tasks_upcoming];
    if (!combinedTasks.length) {
        tasksBox.innerHTML = `<div class="empty-state">На сегодня задач нет. Добавьте главную цель дня!</div>`;
    } else {
        tasksBox.innerHTML = combinedTasks.map((t) => renderTaskRowHtml(t)).join('');
    }
}

function renderTaskRowHtml(task) {
    const isDone = task.status === 'done';
    const dueBadge = task.due_date
        ? `<span class="badge ${task.is_overdue ? 'badge-overdue' : 'badge-status'}">📅 ${task.due_date}</span>`
        : '';

    return `
        <div class="task-row ${isDone ? 'done' : ''}">
            <div class="task-left">
                <button class="check-btn ${isDone ? 'checked' : ''}"
                        onclick="handleQuickToggleTask(${task.id}, '${isDone ? 'todo' : 'done'}')"
                        title="Переключить выполнение">
                    ${isDone ? '✓' : ''}
                </button>
                <div class="item-info">
                    <div class="item-title">
                        <span class="item-title-text">${escapeHtml(task.title)}</span>
                        <span class="badge badge-${task.priority}">${PRIORITY_LABELS[task.priority] || task.priority}</span>
                        <span class="badge badge-status">${STATUS_LABELS[task.status] || task.status}</span>
                        ${dueBadge}
                    </div>
                    ${task.description ? `<div class="item-desc">${escapeHtml(task.description)}</div>` : ''}
                </div>
            </div>
            <div class="icon-actions">
                <button class="icon-btn" onclick="openEditTaskModal(${task.id})" title="Редактировать" aria-label="Редактировать">✎</button>
                <button class="icon-btn danger" onclick="handleDeleteTask(${task.id})" title="Удалить" aria-label="Удалить">🗑</button>
            </div>
        </div>
    `;
}

/* ======================== 2. РАЗДЕЛ ПРИВЫЧЕК ======================== */
async function loadHabits() {
    try {
        const habits = await apiRequest('/api/habits');
        state.habits = habits;
        renderHabitsSection(habits);
    } catch (err) {
        showToast(err.message, true);
    }
}

function renderHabitsSection(habits) {
    const container = document.getElementById('habitsFullList');
    if (!habits.length) {
        container.innerHTML = `<div class="empty-state">Список привычек пуст. Создайте первую привычку!</div>`;
        return;
    }

    const todayIso = getOwnerTodayIso();

    container.innerHTML = habits.map((h) => `
        <div class="habit-card" style="border-top-color: ${escapeHtml(h.color)}">
            <div class="habit-card-top">
                <div>
                    <div class="habit-card-title">
                        <span>${escapeHtml(h.icon)}</span>
                        <span>${escapeHtml(h.name)}</span>
                    </div>
                    ${h.description ? `<div class="item-desc">${escapeHtml(h.description)}</div>` : ''}
                </div>
                <span class="streak-pill">🔥 ${h.current_streak} дн.</span>
            </div>

            <div class="habit-stats-row">
                <div>
                    <div class="mini-stat-val">${h.current_streak}</div>
                    <div class="mini-stat-lbl">Текущая серия</div>
                </div>
                <div>
                    <div class="mini-stat-val">${h.best_streak}</div>
                    <div class="mini-stat-lbl">Рекорд дней</div>
                </div>
                <div>
                    <div class="mini-stat-val">${h.total_completions}</div>
                    <div class="mini-stat-lbl">Всего отметок</div>
                </div>
            </div>

            <div class="habit-card-actions">
                <button class="btn btn-sm ${h.completed_today ? 'btn-secondary' : 'btn-primary'}"
                        onclick="handleToggleHabitToday(${h.id}, '${todayIso}')">
                    ${h.completed_today ? '✓ Выполнено сегодня' : 'Отметить сегодня'}
                </button>
                <div class="icon-actions">
                    <button class="icon-btn" onclick="openEditHabitModal(${h.id})" title="Редактировать" aria-label="Редактировать">✎</button>
                    <button class="icon-btn danger" onclick="handleDeleteHabit(${h.id})" title="Удалить" aria-label="Удалить">🗑</button>
                </div>
            </div>
        </div>
    `).join('');
}

async function handleToggleHabitToday(habitId, targetDate) {
    try {
        const res = await apiRequest(`/api/habits/${habitId}/toggle`, {
            method: 'POST',
            body: JSON.stringify({ completed_date: targetDate }),
        });
        showToast(res.completed ? `Отмечено! Серия: ${res.current_streak} дн.` : 'Отметка снята');
        refreshActiveView();
    } catch (err) {
        showToast(err.message, true);
    }
}

async function handleDeleteHabit(habitId) {
    if (!confirm('Удалить эту привычку и всю историю её выполнения?')) return;
    try {
        await apiRequest(`/api/habits/${habitId}`, { method: 'DELETE' });
        showToast('Привычка удалена');
        refreshActiveView();
    } catch (err) {
        showToast(err.message, true);
    }
}

/* ======================== 3. КАЛЕНДАРЬ ПРИВЫЧЕК ЗА МЕСЯЦ ======================== */
async function loadCalendar() {
    try {
        const data = await apiRequest(
            `/api/stats/calendar?year=${state.calendarYear}&month=${state.calendarMonth}`
        );
        state.calendarData = data;
        renderCalendar(data);
    } catch (err) {
        showToast(err.message, true);
    }
}

function getHeatClass(rate) {
    if (rate <= 0) return 'heat-0';
    if (rate < 35) return 'heat-1';
    if (rate < 65) return 'heat-2';
    if (rate < 95) return 'heat-3';
    return 'heat-4';
}

function renderCalendar(data) {
    document.getElementById('calendarMonthTitle').textContent = `${data.month_name} ${data.year}`;
    document.getElementById('calendarMonthSummary').textContent =
        `Среднее выполнение за месяц: ${data.month_completion_rate}% · Всего отметок: ${data.total_checkins_in_month}`;

    const grid = document.getElementById('monthlyHeatmapGrid');
    const cells = [];

    for (let i = 0; i < data.first_weekday; i++) {
        cells.push(`<div class="cal-day-cell empty"></div>`);
    }

    for (const day of data.days) {
        const heatClass = getHeatClass(day.completion_rate);
        cells.push(`
            <div class="cal-day-cell ${heatClass} ${day.is_today ? 'today' : ''}" title="${day.date}: ${day.completed_count}/${day.total_active_habits} (${day.completion_rate}%)">
                <div class="cal-day-num">${day.day_number}</div>
                <div class="cal-day-meta">
                    ${day.total_active_habits > 0 ? `<span class="cal-ratio">${day.completed_count}/${day.total_active_habits}</span><span class="cal-pct"> (${day.completion_rate}%)</span>` : '—'}
                </div>
            </div>
        `);
    }
    grid.innerHTML = cells.join('');

    const matrixBox = document.getElementById('habitMonthMatrix');
    if (!data.habits.length) {
        matrixBox.innerHTML = `<div class="empty-state">Добавьте привычки, чтобы отмечать их в календаре месяца.</div>`;
        return;
    }

    const dayHeaders = data.days.map((d) => `<th>${d.day_number}</th>`).join('');
    const rows = data.habits.map((habit) => {
        const dayCells = data.days.map((d) => {
            const isDone = d.completed_habit_ids.includes(habit.id);
            return `
                <td>
                    <button class="matrix-dot ${isDone ? 'done' : ''}"
                            ${d.is_future ? 'disabled' : ''}
                            onclick="handleToggleHabitToday(${habit.id}, '${d.date}')"
                            title="${escapeHtml(habit.name)} — ${d.date}">
                        ✓
                    </button>
                </td>
            `;
        }).join('');

        return `
            <tr>
                <td class="habit-col">${escapeHtml(habit.icon)} ${escapeHtml(habit.name)}</td>
                ${dayCells}
            </tr>
        `;
    }).join('');

    matrixBox.innerHTML = `
        <table class="habit-matrix-table">
            <thead>
                <tr>
                    <th class="habit-col">Привычка</th>
                    ${dayHeaders}
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

/* ======================== 4. ПЛАНИРОВЩИК ЗАДАЧ ======================== */
async function loadTasks() {
    try {
        const statusFilter = document.getElementById('filterTaskStatus').value;
        const priorityFilter = document.getElementById('filterTaskPriority').value;
        const params = new URLSearchParams();
        if (statusFilter) params.set('status', statusFilter);
        if (priorityFilter) params.set('priority', priorityFilter);

        const query = params.toString() ? `?${params.toString()}` : '';
        const tasks = await apiRequest(`/api/tasks${query}`);
        state.tasks = tasks;
        renderTasksList(tasks);
    } catch (err) {
        showToast(err.message, true);
    }
}

function renderTasksList(tasks) {
    const container = document.getElementById('tasksFullList');
    if (!tasks.length) {
        container.innerHTML = `<div class="empty-state">Задачи по выбранным фильтрам не найдены.</div>`;
        return;
    }
    container.innerHTML = tasks.map((t) => renderTaskRowHtml(t)).join('');
}

async function handleQuickToggleTask(taskId, newStatus) {
    try {
        await apiRequest(`/api/tasks/${taskId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: newStatus }),
        });
        showToast(newStatus === 'done' ? 'Задача выполнена!' : 'Задача возвращена в список');
        refreshActiveView();
    } catch (err) {
        showToast(err.message, true);
    }
}

async function handleDeleteTask(taskId) {
    if (!confirm('Удалить эту задачу?')) return;
    try {
        await apiRequest(`/api/tasks/${taskId}`, { method: 'DELETE' });
        showToast('Задача удалена');
        refreshActiveView();
    } catch (err) {
        showToast(err.message, true);
    }
}

/* ======================== 5. СТАТИСТИКА (НЕДЕЛЯ И МЕСЯЦ) ======================== */
async function loadStats() {
    try {
        const summary = await apiRequest('/api/stats/summary');
        state.statsSummary = summary;
        renderStats(summary);
    } catch (err) {
        showToast(err.message, true);
    }
}

function renderStats(summary) {
    const periodData = state.statsPeriod === 'weekly' ? summary.weekly : summary.monthly;
    const periodLabel = state.statsPeriod === 'weekly' ? '7 дней' : '30 дней';

    document.getElementById('statsKpiGrid').innerHTML = `
        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Выполнение привычек (${periodLabel})</span>
                <span class="kpi-icon">🔥</span>
            </div>
            <div class="kpi-value">${periodData.habit_completion_rate}%</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${periodData.habit_completion_rate}%"></div>
            </div>
            <div class="kpi-foot">Отметок: ${periodData.total_habit_checkins} из ${periodData.possible_habit_checkins}</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Закрыто задач (${periodLabel})</span>
                <span class="kpi-icon">✅</span>
            </div>
            <div class="kpi-value">${periodData.tasks_completed}</div>
            <div class="kpi-foot">Из них высокого приоритета: ${periodData.high_priority_done}</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Лидер стабильности</span>
                <span class="kpi-icon">🏆</span>
            </div>
            <div class="kpi-value" style="font-size: 18px;">${escapeHtml(periodData.best_habit_name || 'Нет данных')}</div>
            <div class="kpi-foot">Лучшая серия: ${periodData.best_habit_streak} дн.</div>
        </div>

        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Индекс продуктивности</span>
                <span class="kpi-icon">📊</span>
            </div>
            <div class="kpi-value">${summary.productivity_score} / 100</div>
            <div class="kpi-foot">В ожидании задач: ${periodData.tasks_pending}</div>
        </div>
    `;

    const chart = document.getElementById('dailyTrendChart');
    chart.innerHTML = periodData.daily_trend.map((pt) => `
        <div class="trend-col" title="${pt.date}: ${pt.habits_completed}/${pt.habits_total} привычек (${pt.habit_rate}%), задач закрыто: ${pt.tasks_completed}">
            <div class="trend-bar-wrap">
                <div class="trend-bar" style="height: ${Math.max(pt.habit_rate, 4)}%"></div>
            </div>
            <span class="trend-lbl">${pt.label}</span>
        </div>
    `).join('');

    const leaderboard = document.getElementById('streaksLeaderboard');
    if (!summary.top_streaks.length) {
        leaderboard.innerHTML = `<div class="empty-state">Пока нет активных привычек.</div>`;
    } else {
        leaderboard.innerHTML = summary.top_streaks.map((h) => `
            <div class="habit-row">
                <div class="habit-left">
                    <span>${escapeHtml(h.icon)}</span>
                    <div class="item-info">
                        <div class="item-title">${escapeHtml(h.name)}</div>
                        <div class="item-desc">Всего выполнений: ${h.total_completions} · Рекорд: ${h.best_streak} дн.</div>
                    </div>
                </div>
                <span class="streak-pill">🔥 ${h.current_streak} дн.</span>
            </div>
        `).join('');
    }

    const breakdown = document.getElementById('tasksBreakdownBox');
    breakdown.innerHTML = `
        <div class="subsection-title">Распределение всех задач</div>
        <div class="breakdown-grid">
            <div class="breakdown-item">
                <div class="mini-stat-val">${summary.tasks_by_status.todo || 0}</div>
                <div class="mini-stat-lbl">К выполнению</div>
            </div>
            <div class="breakdown-item">
                <div class="mini-stat-val">${summary.tasks_by_status.in_progress || 0}</div>
                <div class="mini-stat-lbl">В работе</div>
            </div>
            <div class="breakdown-item">
                <div class="mini-stat-val">${summary.tasks_by_status.done || 0}</div>
                <div class="mini-stat-lbl">Готово</div>
            </div>
        </div>
    `;
}

/* ======================== МОДАЛЬНЫЕ ОКНА И ФОРМЫ ======================== */
function closeAllModals() {
    document.querySelectorAll('.modal-backdrop').forEach((m) => m.classList.add('hidden'));
    document.querySelectorAll('.form-error').forEach((e) => {
        e.classList.add('hidden');
        e.textContent = '';
    });
}

function openCreateHabitModal() {
    document.getElementById('habitForm').reset();
    document.getElementById('habitIdInput').value = '';
    document.getElementById('habitModalTitle').textContent = 'Новая привычка';
    document.getElementById('habitModal').classList.remove('hidden');
}

async function openEditHabitModal(habitId) {
    try {
        const habit = await apiRequest(`/api/habits/${habitId}`);
        document.getElementById('habitIdInput').value = habit.id;
        document.getElementById('habitNameInput').value = habit.name;
        document.getElementById('habitDescInput').value = habit.description || '';
        document.getElementById('habitIconInput').value = habit.icon || '✨';
        document.getElementById('habitColorInput').value = habit.color || '#4F46E5';
        document.getElementById('habitTargetInput').value = habit.target_days_per_week || 7;
        document.getElementById('habitModalTitle').textContent = 'Редактировать привычку';
        document.getElementById('habitModal').classList.remove('hidden');
    } catch (err) {
        showToast(err.message, true);
    }
}

function openCreateTaskModal() {
    document.getElementById('taskForm').reset();
    document.getElementById('taskIdInput').value = '';
    document.getElementById('taskDueDateInput').value = getOwnerTodayIso();
    document.getElementById('taskModalTitle').textContent = 'Новая задача';
    document.getElementById('taskModal').classList.remove('hidden');
}

async function openEditTaskModal(taskId) {
    try {
        const task = await apiRequest(`/api/tasks/${taskId}`);
        document.getElementById('taskIdInput').value = task.id;
        document.getElementById('taskTitleInput').value = task.title;
        document.getElementById('taskDescInput').value = task.description || '';
        document.getElementById('taskDueDateInput').value = task.due_date || '';
        document.getElementById('taskPriorityInput').value = task.priority;
        document.getElementById('taskStatusInput').value = task.status;
        document.getElementById('taskCategoryInput').value = task.category || 'Общее';
        document.getElementById('taskModalTitle').textContent = 'Редактировать задачу';
        document.getElementById('taskModal').classList.remove('hidden');
    } catch (err) {
        showToast(err.message, true);
    }
}

function refreshActiveView() {
    switchView(state.activeView);
}

/* ======================== ИНИЦИАЛИЗАЦИЯ СОБЫТИЙ ======================== */
document.addEventListener('DOMContentLoaded', () => {
    formatCurrentDateHeader();

    // Навигация по вкладкам (десктоп + мобильный таб-бар)
    document.querySelectorAll('.nav-item, .mobile-nav-btn').forEach((btn) => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Открытие модалок
    document.getElementById('quickAddHabitBtn').addEventListener('click', openCreateHabitModal);
    document.getElementById('quickAddTaskBtn').addEventListener('click', openCreateTaskModal);
    document.querySelectorAll('[data-open-habit-modal]').forEach((b) => b.addEventListener('click', openCreateHabitModal));
    document.querySelectorAll('[data-open-task-modal]').forEach((b) => b.addEventListener('click', openCreateTaskModal));
    document.getElementById('openProModalBtn').addEventListener('click', () => {
        document.getElementById('proModal').classList.remove('hidden');
    });

    // Закрытие модалок по кнопке и клику на фон
    document.querySelectorAll('[data-close-modals]').forEach((b) => b.addEventListener('click', closeAllModals));
    document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
        backdrop.addEventListener('click', (e) => {
            if (e.target === backdrop) closeAllModals();
        });
    });

    // Ручная и автоматическая синхронизация между ноутбуком и телефоном
    const triggerSync = () => {
        refreshActiveView();
        showToast('Синхронизировано с сервером');
    };
    const syncBtn = document.getElementById('syncNowBtn');
    const mobileSyncBtn = document.getElementById('mobileSyncBtn');
    if (syncBtn) syncBtn.addEventListener('click', triggerSync);
    if (mobileSyncBtn) mobileSyncBtn.addEventListener('click', triggerSync);

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            refreshActiveView();
        }
    });

    // Выход владельца
    const desktopLogout = document.getElementById('desktopLogoutBtn');
    const mobileLogout = document.getElementById('mobileLogoutBtn');
    if (desktopLogout) desktopLogout.addEventListener('click', handleLogout);
    if (mobileLogout) mobileLogout.addEventListener('click', handleLogout);

    // Демо-данные
    document.getElementById('seedDemoBtn').addEventListener('click', async () => {
        try {
            const res = await apiRequest('/api/stats/seed', { method: 'POST' });
            showToast(res.message);
            refreshActiveView();
        } catch (err) {
            showToast(err.message, true);
        }
    });

    // Сабмит формы привычки
    document.getElementById('habitForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errBox = document.getElementById('habitFormError');
        errBox.classList.add('hidden');

        const habitId = document.getElementById('habitIdInput').value;
        const name = document.getElementById('habitNameInput').value.trim();
        if (!name) {
            errBox.textContent = 'Пожалуйста, укажите название привычки';
            errBox.classList.remove('hidden');
            return;
        }

        const payload = {
            name,
            description: document.getElementById('habitDescInput').value.trim() || null,
            icon: document.getElementById('habitIconInput').value,
            color: document.getElementById('habitColorInput').value,
            target_days_per_week: Number(document.getElementById('habitTargetInput').value) || 7,
        };

        try {
            if (habitId) {
                await apiRequest(`/api/habits/${habitId}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
                showToast('Привычка обновлена');
            } else {
                await apiRequest('/api/habits', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                showToast('Привычка создана');
            }
            closeAllModals();
            refreshActiveView();
        } catch (err) {
            errBox.textContent = err.message;
            errBox.classList.remove('hidden');
        }
    });

    // Сабмит формы задачи
    document.getElementById('taskForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errBox = document.getElementById('taskFormError');
        errBox.classList.add('hidden');

        const taskId = document.getElementById('taskIdInput').value;
        const title = document.getElementById('taskTitleInput').value.trim();
        if (!title) {
            errBox.textContent = 'Пожалуйста, введите название задачи';
            errBox.classList.remove('hidden');
            return;
        }

        const dueVal = document.getElementById('taskDueDateInput').value;
        const payload = {
            title,
            description: document.getElementById('taskDescInput').value.trim() || null,
            due_date: dueVal ? dueVal : null,
            priority: document.getElementById('taskPriorityInput').value,
            status: document.getElementById('taskStatusInput').value,
            category: document.getElementById('taskCategoryInput').value.trim() || 'Общее',
        };

        try {
            if (taskId) {
                await apiRequest(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
                showToast('Задача обновлена');
            } else {
                await apiRequest('/api/tasks', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                showToast('Задача добавлена');
            }
            closeAllModals();
            refreshActiveView();
        } catch (err) {
            errBox.textContent = err.message;
            errBox.classList.remove('hidden');
        }
    });

    // Сабмит формы HabitFlow Pro Waitlist
    document.getElementById('proWaitlistForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errBox = document.getElementById('proFormError');
        errBox.classList.add('hidden');

        const contact = document.getElementById('proContactInput').value.trim();
        if (contact.length < 3) {
            errBox.textContent = 'Укажите минимум 3 символа';
            errBox.classList.remove('hidden');
            return;
        }

        try {
            const res = await apiRequest('/api/stats/waitlist', {
                method: 'POST',
                body: JSON.stringify({
                    contact,
                    desired_feature: document.getElementById('proFeatureSelect').value,
                }),
            });
            closeAllModals();
            showToast(res.message);
        } catch (err) {
            errBox.textContent = err.message;
            errBox.classList.remove('hidden');
        }
    });

    // Управление календарём
    document.getElementById('calPrevMonthBtn').addEventListener('click', () => {
        state.calendarMonth -= 1;
        if (state.calendarMonth < 1) {
            state.calendarMonth = 12;
            state.calendarYear -= 1;
        }
        loadCalendar();
    });

    document.getElementById('calNextMonthBtn').addEventListener('click', () => {
        state.calendarMonth += 1;
        if (state.calendarMonth > 12) {
            state.calendarMonth = 1;
            state.calendarYear += 1;
        }
        loadCalendar();
    });

    document.getElementById('calCurrentMonthBtn').addEventListener('click', () => {
        const parts = getOwnerTodayIso().split('-').map(Number);
        state.calendarYear = parts[0] || new Date().getFullYear();
        state.calendarMonth = parts[1] || (new Date().getMonth() + 1);
        loadCalendar();
    });

    // Фильтры задач
    document.getElementById('filterTaskStatus').addEventListener('change', loadTasks);
    document.getElementById('filterTaskPriority').addEventListener('change', loadTasks);

    // Переключатель периода статистики (7 / 30 дней)
    document.querySelectorAll('[data-stats-period]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.statsPeriod = btn.dataset.statsPeriod;
            document.querySelectorAll('[data-stats-period]').forEach((b) => {
                b.classList.toggle('active', b === btn);
            });
            if (state.statsSummary) {
                renderStats(state.statsSummary);
            } else {
                loadStats();
            }
        });
    });

    // Первичная загрузка главной панели
    loadDashboard();
});
