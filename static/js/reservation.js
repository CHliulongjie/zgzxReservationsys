// 全局变量
let currentUser = null;
let currentSystem = 'badminton';
let currentDate = new Date();
let selectedField = null;
let selectedSession = null;
let systems = [];

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查登录状态
    checkLoginStatus();

    // 初始化时间显示
    updateTime();
    setInterval(updateTime, 1000);

    // 加载系统信息
    loadSystems();

    // 绑定事件
    document.getElementById('systemTabs').addEventListener('click', function(e) {
        if (e.target.classList.contains('system-tab')) {
            const system = e.target.dataset.system;
            switchSystem(system);
        }
    });
});

// 检查登录状态
async function checkLoginStatus() {
    try {
        // 获取当前用户信息
        const response = await fetch('/api/user/info');
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.username) {
                currentUser = data.username;
                document.getElementById('username').textContent = currentUser;
                document.getElementById('displayUsername').textContent = currentUser;

            // 检查今日预约状态
            checkTodayReservation();
        } else {
                window.location.href = '/';
            }
        } else if (response.status === 401) {
            // 未登录，跳转到登录页
            window.location.href = '/';
        } else {
            // 其他错误，也跳转到登录页
            window.location.href = '/';
        }
    } catch (error) {
        console.error('检查登录状态失败:', error);
        window.location.href = '/';
    }
}

// 加载系统信息
async function loadSystems() {
    try {
        const response = await fetch('/api/system/info');
        if (response.ok) {
            const data = await response.json();
            systems = data.systems;

            // 生成系统标签页
            generateSystemTabs();

            // 加载当前系统内容
            loadSystemContent();
        }
    } catch (error) {
        showAlert('加载系统信息失败', 'danger');
    }
}

// 生成系统标签页
function generateSystemTabs() {
    const tabsContainer = document.getElementById('systemTabs');
    let html = '';

    const systemOrder = ['badminton', 'pingpong', 'basketball', 'football', 'movie', 'other'];

    systemOrder.forEach(systemId => {
        const system = systems[systemId];
        if (system) {
            const active = systemId === currentSystem ? 'active' : '';
            const enabled = system.enabled ? '' : 'disabled';
            const icon = getSystemIcon(systemId);

            html += `
                <button class="system-tab ${active} ${enabled}" 
                        data-system="${systemId}"
                        ${!system.enabled ? 'disabled' : ''}>
                    <i class="fas ${icon}"></i> ${system.name}
                    ${!system.enabled ? ' (未开放)' : ''}
                </button>
            `;
        }
    });

    tabsContainer.innerHTML = html;
}

// 获取系统图标
function getSystemIcon(systemId) {
    const icons = {
        badminton: 'fa-table-tennis',
        pingpong: 'fa-table-tennis-paddle-ball',
        basketball: 'fa-basketball',
        football: 'fa-futbol',
        movie: 'fa-film',
        other: 'fa-calendar-plus'
    };
    return icons[systemId] || 'fa-calendar';
}

// 切换系统
function switchSystem(systemId) {
    if (!systems[systemId]?.enabled) {
        showAlert('该系统暂未开放', 'warning');
        return;
    }

    currentSystem = systemId;

    // 更新标签页
    document.querySelectorAll('.system-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.system === systemId) {
            tab.classList.add('active');
        }
    });

    // 加载系统内容
    loadSystemContent();
}

// 加载系统内容
async function loadSystemContent() {
    const contentContainer = document.getElementById('systemContent');

    // 显示加载中
    contentContainer.innerHTML = `
        <div class="loading-spinner">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">加载中...</span>
            </div>
            <p class="mt-2">正在加载${systems[currentSystem]?.name || currentSystem}...</p>
        </div>
    `;

    try {
        if (['badminton', 'pingpong', 'basketball', 'football'].includes(currentSystem)) {
            await loadSportsSystem();
        } else {
            await loadSessionSystem();
        }
    } catch (error) {
        contentContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 加载失败: ${error.message}
            </div>
        `;
    }
}

// 加载球类系统
async function loadSportsSystem() {
    const contentContainer = document.getElementById('systemContent');

    try {
        // 获取系统配置
        const configResponse = await fetch(`/api/system/${currentSystem}/config`);
        if (!configResponse.ok) throw new Error('获取配置失败');

        const config = await configResponse.json();

        // 获取预约数据
        const reservationsResponse = await fetch(`/api/reservation/sports/${currentSystem}`);
        if (!reservationsResponse.ok) throw new Error('获取数据失败');

        const data = await reservationsResponse.json();

        // 生成内容
        contentContainer.innerHTML = generateSportsContent(config, data);

        // 绑定事件
        bindSportsEvents();

    } catch (error) {
        throw error;
    }
}

// 生成球类系统内容
function generateSportsContent(config, data) {
    const today = new Date().toISOString().split('T')[0];
    const currentDateStr = currentDate.toISOString().split('T')[0];
    const todayDate = new Date();
    todayDate.setHours(0, 0, 0, 0);
    const selectedDate = new Date(currentDate);
    selectedDate.setHours(0, 0, 0, 0);
    
    // 检查选择的日期是否是过去日期（不包括当天）
    const isPastDate = selectedDate.getTime() < todayDate.getTime();
    // 检查是否开启了仅可预约当日
    const onlyToday = config.only_today || false;
    const isToday = currentDateStr === today;
    
    // 如果开启了仅可预约当日，且选择的不是今天，则不允许预约
    const canReserve = !isPastDate && (!onlyToday || isToday);
    
    let fieldsHtml = '';

    // 生成场地卡片
    for (let i = 1; i <= config.fields; i++) {
        const fieldName = `场地${i}`;
        const reservation = getFieldReservation(data.reservations, currentDateStr, fieldName);
        const isReserved = !!reservation;
        const reservedByMe = reservation === currentUser;

        fieldsHtml += `
            <div class="col-md-4 mb-3">
                <div class="field-card ${isReserved ? 'booked' : 'available'}">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="mb-0">${fieldName}</h5>
                        <span class="status-badge ${isReserved ? 'badge-danger' : (canReserve ? 'badge-success' : 'badge-warning')}">
                            ${isReserved ? (reservedByMe ? '您已预约' : '已预约') : (canReserve ? '可预约' : (isPastDate ? '已过期' : '不可预约'))}
                        </span>
                    </div>
                    
                    ${isReserved ? `
                        <p class="mb-3"><strong>预约人:</strong> ${reservation}</p>
                        ${reservedByMe ? `
                            <button class="btn btn-danger w-100" onclick="cancelReservation('${currentDateStr}', '${fieldName}')">
                                <i class="fas fa-times"></i> 取消预约
                            </button>
                        ` : ''}
                    ` : `
                        <p class="mb-3"><strong>状态:</strong> ${canReserve ? '空闲' : (isPastDate ? '该日期已过期' : (onlyToday ? '仅可预约当日场地' : '不可用'))}</p>
                        <button class="btn btn-primary w-100" onclick="bookField('${fieldName}')" ${!canReserve ? 'disabled' : ''}>
                            <i class="fas fa-calendar-plus"></i> ${canReserve ? '立即预约' : '不可预约'}
                        </button>
                    `}
                </div>
            </div>
        `;
    }

    // 格式化weekdays显示
    let weekdaysDisplay = '';
    if (Array.isArray(config.weekdays)) {
        weekdaysDisplay = config.weekdays.join('、');
    } else if (typeof config.weekdays === 'object') {
        const weekdayList = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
        weekdaysDisplay = weekdayList.filter(day => config.weekdays[day]).join('、');
    } else {
        weekdaysDisplay = '周一至周四';
    }

    return `
        <div class="system-card">
            <div class="system-header" style="background: ${getSystemColor(currentSystem)};">
                <h4><i class="fas ${getSystemIcon(currentSystem)}"></i> ${config.name}</h4>
                <p class="mb-0">${config.fields}个场地 | ${weekdaysDisplay} | ${config.start_time}~${config.end_time}</p>
            </div>
            <div class="card-body">
                <div class="date-selector">
                    <div class="d-flex align-items-center">
                        <button class="btn btn-outline-secondary me-2" onclick="changeDate(-1)">
                            <i class="fas fa-chevron-left"></i>
                        </button>
                        <h5 class="mb-0" id="currentDateDisplay">${formatDate(currentDate)}</h5>
                        <button class="btn btn-outline-secondary ms-2" onclick="changeDate(1)">
                            <i class="fas fa-chevron-right"></i>
                        </button>
                        <button class="btn btn-outline-primary ms-auto" onclick="refreshData()">
                            <i class="fas fa-sync-alt"></i> 刷新
                        </button>
                    </div>
                    ${onlyToday ? '<div class="alert alert-info mt-2 mb-0"><i class="fas fa-info-circle"></i> 该系统仅允许预约当日场地</div>' : ''}
                </div>
                
                <div class="row" id="fieldsContainer">
                    ${fieldsHtml}
                </div>
                
                <div class="mt-4">
                    <h5>本周预约情况</h5>
                    <div class="table-responsive">
                        <table class="table table-bordered">
<thead>
                                <tr>
                                    <th>日期</th>
                                    ${Array.from({length: config.fields}, (_, i) => `<th>场地${i+1}</th>`).join('')}
                                </tr>
                            </thead>
                            <tbody id="scheduleTable">
                                <!-- 周表格将通过JavaScript动态生成 -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// 获取场地预约信息
function getFieldReservation(reservations, date, field) {
    for (const reservation of reservations) {
        if (reservation.date === date && reservation.fields[field]) {
            return reservation.fields[field];
        }
    }
    return null;
}

// 预约场地
function bookField(fieldName) {
    selectedField = fieldName;

    const modal = new bootstrap.Modal(document.getElementById('bookingModal'));
    const modalTitle = document.getElementById('bookingModalTitle');
    const bookingInfo = document.getElementById('bookingInfo');

    modalTitle.textContent = `预约${systems[currentSystem].name} - ${fieldName}`;
    bookingInfo.innerHTML = `
        <p><strong>场地:</strong> ${fieldName}</p>
        <p><strong>日期:</strong> ${formatDate(currentDate)}</p>
        <p><strong>时间:</strong> ${currentDate.toLocaleDateString('zh-CN', {weekday: 'long'})}</p>
        <p><strong>预约人:</strong> ${currentUser}</p>
    `;

    modal.show();
}

// 确认预约
async function confirmBooking() {
    try {
        const dateStr = currentDate.toISOString().split('T')[0];

        const response = await fetch(`/api/reservation/sports/${currentSystem}/book`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                date: dateStr,
                field: selectedField
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('预约成功', 'success');
            bootstrap.Modal.getInstance(document.getElementById('bookingModal')).hide();
            loadSystemContent();
            checkTodayReservation();
        } else {
            showAlert(data.error || '预约失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误: ' + error.message, 'danger');
    }
}

// 取消预约（球类）
async function cancelReservation(date, field) {
    if (!confirm(`确定要取消 ${field} 的预约吗？`)) {
        return;
    }

    try {
        const response = await fetch(`/api/reservation/sports/${currentSystem}/cancel`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                date: date,
                field: field
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('取消预约成功', 'success');
            loadSystemContent();
            checkTodayReservation();
        } else {
            showAlert(data.error || '取消失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误: ' + error.message, 'danger');
    }
}

// 取消预约（电影/其他）
async function cancelSessionReservation(system, sessionId, sessionName) {
    if (!confirm(`确定要取消「${sessionName}」的预约吗？`)) {
        return;
    }

    try {
        const response = await fetch(`/api/reservation/session/${system}/cancel`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('取消预约成功', 'success');
            // 刷新"我的预约"列表
            showMyReservations();
            // 如果当前正在查看该系统，也刷新内容
            if (currentSystem === system) {
                loadSystemContent();
            }
            checkTodayReservation();
        } else {
            showAlert(data.error || '取消失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误: ' + error.message, 'danger');
    }
}

// 加载会话系统（电影/其他）
async function loadSessionSystem() {
    const contentContainer = document.getElementById('systemContent');

    try {
        // 获取系统配置
        const configResponse = await fetch(`/api/system/${currentSystem}/config`);
        if (!configResponse.ok) throw new Error('获取配置失败');

        const config = await configResponse.json();

        // 获取项目数据
        const sessionsResponse = await fetch(`/api/reservation/session/${currentSystem}`);
        if (!sessionsResponse.ok) throw new Error('获取数据失败');

        const data = await sessionsResponse.json();
        const items = currentSystem === 'movie' ? data.sessions : data.items;

        // 生成内容
        contentContainer.innerHTML = generateSessionContent(config, items);

    } catch (error) {
        throw error;
    }
}

// 生成会话系统内容
function generateSessionContent(config, items) {
    let itemsHtml = '';

    if (items.length === 0) {
        itemsHtml = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> 当前没有可预约的项目
            </div>
        `;
    } else {
        items.forEach(item => {
            const startTime = new Date(item.start_time);
            const endTime = new Date(item.end_time);
            const now = new Date();
            const isAvailable = now >= startTime && now <= endTime;

            itemsHtml += `
                <div class="session-card">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="mb-0">${item.name}</h5>
                        <span class="status-badge ${isAvailable ? 'badge-success' : 'badge-danger'}">
                            ${isAvailable ? '可预约' : '不可预约'}
                        </span>
                    </div>
                    
                    <p class="mb-2"><strong>介绍:</strong> ${item.description || '无'}</p>
                    <p class="mb-2"><strong>人数限制:</strong> ${item.capacity || '不限'}</p>
                    <p class="mb-2"><strong>开始时间:</strong> ${formatDateTime(startTime)}</p>
                    <p class="mb-3"><strong>结束时间:</strong> ${formatDateTime(endTime)}</p>
                    
                    <button class="btn btn-primary" onclick="bookSession('${item.id}')" ${!isAvailable ? 'disabled' : ''}>
                        <i class="fas fa-calendar-plus"></i> 预约
                    </button>
                </div>
            `;
        });
    }

    return `
        <div class="system-card">
            <div class="system-header" style="background: ${getSystemColor(currentSystem)};">
                <h4><i class="fas ${getSystemIcon(currentSystem)}"></i> ${config.name}</h4>
            </div>
            <div class="card-body">
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i> 每人可以预约多个项目，但需注意时间安排
                </div>
                
                ${itemsHtml}
            </div>
        </div>
    `;
}

// 预约会话项目
async function bookSession(sessionId) {
    selectedSession = sessionId;

    try {
        const response = await fetch(`/api/reservation/session/${currentSystem}/book`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('预约成功', 'success');
            loadSystemContent();
        } else {
            showAlert(data.error || '预约失败', 'danger');
        }
    } catch (error) {
        showAlert('网络错误: ' + error.message, 'danger');
    }
}

// 检查今日预约状态
async function checkTodayReservation() {
    try {
        const response = await fetch('/api/user/reservations');
        if (response.ok) {
            const data = await response.json();
            const today = new Date().toISOString().split('T')[0];

            // 检查是否有今天的预约
            const hasTodayReservation = data.reservations.some(res => {
                return res.date === today || (res.date && res.date.startsWith(today));
            });

            document.getElementById('reservationStatus').textContent =
                hasTodayReservation ? '今日已预约' : '今日尚未预约';
        }
    } catch (error) {
        console.error('检查预约状态失败:', error);
    }
}

// 显示我的预约
async function showMyReservations() {
    try {
        const response = await fetch('/api/user/reservations');
        if (response.ok) {
            const data = await response.json();
            const content = document.getElementById('myReservationsContent');

            if (data.reservations.length === 0) {
                content.innerHTML = `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle"></i> 您还没有任何预约
                    </div>
                `;
            } else {
                let html = '<div class="list-group">';

                data.reservations.forEach(res => {
                    // 球类预约：显示场地和日期
                    // 电影/其他预约：在系统名后加括号显示项目名
                    let titleHtml = `<h6 class="mb-1">${res.system_name}</h6>`;
                    let infoHtml = '';
                    let cancelBtnHtml = '';

                    if (res.type === 'session') {
                        // 电影/其他预约
                        if (res.session_name) {
                            titleHtml = `<h6 class="mb-1">${res.system_name}（${res.session_name}）</h6>`;
                        }
                        cancelBtnHtml = `
                            <button class="btn btn-sm btn-danger" onclick="cancelSessionReservation('${res.system}', '${res.session_id}', '${(res.session_name || '').replace(/'/g, "\\'")}')">
                                取消
                            </button>
                        `;
                    } else {
                        // 球类预约
                        if (res.field) {
                            infoHtml += `<p class="mb-1 text-muted">场地: ${res.field}</p>`;
                        }
                        if (res.date) {
                            infoHtml += `<p class="mb-0 text-muted">日期: ${res.date}</p>`;
                        }
                        if (res.field) {
                            cancelBtnHtml = `
                                <button class="btn btn-sm btn-danger" onclick="cancelReservation('${res.date}', '${res.field}')">
                                    取消
                                </button>
                            `;
                        }
                    }

                    html += `
                        <div class="list-group-item">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    ${titleHtml}
                                    ${infoHtml}
                                </div>
                                ${cancelBtnHtml}
                            </div>
                        </div>
                    `;
                });

                html += '</div>';
                content.innerHTML = html;
            }

            // 复用已有实例，避免重复创建导致 backdrop 残留
            const modalEl = document.getElementById('myReservationsModal');
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        }
    } catch (error) {
        showAlert('获取预约列表失败', 'danger');
    }
}

// 退出登录
function logout() {
    if (confirm('确定要退出登录吗？')) {
        fetch('/api/logout').then(() => {
            window.location.href = '/';
        });
    }
}

// 更改日期
function changeDate(delta) {
    const newDate = new Date(currentDate);
    newDate.setDate(newDate.getDate() + delta);
    
    // 检查新日期不能是过去的日期（不包括当天）
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    newDate.setHours(0, 0, 0, 0);
    
    // 只允许当天及未来的日期
    if (newDate.getTime() >= today.getTime()) {
        currentDate = newDate;
        document.getElementById('currentDateDisplay').textContent = formatDate(currentDate);
        loadSystemContent();
    } else {
        showAlert('不能查看过去的日期', 'warning');
    }
}

// 刷新数据
function refreshData() {
    loadSystemContent();
    showAlert('数据已刷新', 'info');
}

// 更新时间显示
function updateTime() {
    const now = new Date();
    document.getElementById('currentTime').textContent = now.toLocaleTimeString('zh-CN');
    document.getElementById('currentDate').textContent = now.toLocaleDateString('zh-CN');
}

// 格式化日期
function formatDate(date) {
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return `${date.getMonth() + 1}月${date.getDate()}日 ${weekdays[date.getDay()]}`;
}

// 格式化日期时间
function formatDateTime(date) {
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 获取系统颜色
function getSystemColor(systemId) {
    const colors = {
        badminton: '#3498db',
        pingpong: '#2ecc71',
        basketball: '#1abc9c',
        football: '#f39c12',
        movie: '#9b59b6',
        other: '#7f8c8d'
    };
    return colors[systemId] || '#3498db';
}

// 显示消息提示
function showAlert(message, type = 'info', duration = 5000) {
    const alertContainer = document.getElementById('alertContainer');
    const alertId = 'alert-' + Date.now();

    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
            <i class="fas fa-${getAlertIcon(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    alertContainer.innerHTML += alertHtml;

    if (duration > 0) {
        setTimeout(() => {
            const alert = document.getElementById(alertId);
            if (alert) {
                alert.remove();
            }
        }, duration);
    }
}

// 获取提示图标
function getAlertIcon(type) {
    switch(type) {
        case 'success': return 'check-circle';
        case 'warning': return 'exclamation-triangle';
        case 'danger': return 'times-circle';
        default: return 'info-circle';
    }
}

// 绑定球类系统事件
function bindSportsEvents() {
    // 这里可以添加更多事件绑定
}

// 绑定事件到场地卡片
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('book-field-btn')) {
        const field = e.target.dataset.field;
        bookField(field);
    }
});