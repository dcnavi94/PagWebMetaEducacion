let adminSchedule = [];
const scheduleDays = { 1:'Lunes', 2:'Martes', 3:'Miércoles', 4:'Jueves', 5:'Viernes', 6:'Sábado' };

function getScheduleMode() {
    const studentRadio = document.getElementById('scheduleModeStudent');
    return (studentRadio && studentRadio.checked) ? 'student' : 'group';
}

function onScheduleModeChange() {
    const mode = getScheduleMode();
    const studentContainer = document.getElementById('scheduleStudentSelectContainer');
    const groupContainer = document.getElementById('scheduleGroupSelectContainer');
    const label = document.getElementById('scheduleModalTargetLabel');
    
    if (mode === 'student') {
        if (studentContainer) studentContainer.style.display = 'block';
        if (groupContainer) groupContainer.style.display = 'none';
        if (label) label.textContent = 'Alumno';
    } else {
        if (studentContainer) studentContainer.style.display = 'none';
        if (groupContainer) groupContainer.style.display = 'block';
        if (label) label.textContent = 'Grupo';
    }
    
    initializeScheduleAdmin();
    loadAdminSchedule();
}

function scheduleStudentOptions() {
    return [...allStudents]
        .sort((a, b) => (a.full_name || a.username).localeCompare(b.full_name || b.username))
        .map(student => `<option value="${libraryEsc(student.username)}">${libraryEsc(student.full_name || student.username)} · ${libraryEsc(student.username)}</option>`)
        .join('');
}

function scheduleGroupOptions() {
    return [...(allGroupSummaries || [])]
        .sort((a, b) => (a.grupo || '').localeCompare(b.grupo || ''))
        .map(group => `<option value="${group.group_id}">${libraryEsc(group.grupo)} — ${libraryEsc(group.carrera || 'Sin carrera')}</option>`)
        .join('');
}

function initializeScheduleAdmin() {
    const mode = getScheduleMode();
    const mainStudentSelect = document.getElementById('scheduleStudentSelect');
    const mainGroupSelect = document.getElementById('scheduleGroupSelect');
    const modalSelect = document.getElementById('scheduleModalStudent');
    
    if (mode === 'student') {
        const previousStudent = mainStudentSelect?.value || '';
        const studentOptions = `<option value="">Selecciona un alumno...</option>${scheduleStudentOptions()}`;
        if (mainStudentSelect) { mainStudentSelect.innerHTML = studentOptions; mainStudentSelect.value = previousStudent; }
        if (modalSelect) modalSelect.innerHTML = studentOptions;
    } else {
        const previousGroup = mainGroupSelect?.value || '';
        if (!allGroupSummaries || allGroupSummaries.length === 0) {
            fetch('/admin/groups', {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            .then(res => res.json())
            .then(groups => {
                allGroupSummaries = groups;
                const groupOptions = `<option value="">Selecciona un grupo...</option>${scheduleGroupOptions()}`;
                if (mainGroupSelect) { mainGroupSelect.innerHTML = groupOptions; mainGroupSelect.value = previousGroup; }
                if (modalSelect) modalSelect.innerHTML = groupOptions;
            })
            .catch(err => console.error('Error loading groups for schedules:', err));
        } else {
            const groupOptions = `<option value="">Selecciona un grupo...</option>${scheduleGroupOptions()}`;
            if (mainGroupSelect) { mainGroupSelect.innerHTML = groupOptions; mainGroupSelect.value = previousGroup; }
            if (modalSelect) modalSelect.innerHTML = groupOptions;
        }
    }
}

async function scheduleFetch(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token}`,
            ...(options.body ? { 'Content-Type':'application/json' } : {})
        }
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'No se pudo completar la operación');
    }
    return response.status === 204 ? null : response.json();
}

async function loadAdminSchedule() {
    const mode = getScheduleMode();
    const tbody = document.getElementById('adminScheduleTable');
    
    if (mode === 'student') {
        const username = document.getElementById('scheduleStudentSelect')?.value;
        if (!username) {
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-5 text-muted">Selecciona un alumno para consultar su horario.</td></tr>';
            return;
        }
        try {
            adminSchedule = await scheduleFetch(`/admin/students/${encodeURIComponent(username)}/schedule`);
            renderAdminSchedule();
        } catch (error) { showToast(error.message, true); }
    } else {
        const groupId = document.getElementById('scheduleGroupSelect')?.value;
        if (!groupId) {
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-5 text-muted">Selecciona un grupo para consultar su horario.</td></tr>';
            return;
        }
        try {
            adminSchedule = await scheduleFetch(`/admin/groups/${encodeURIComponent(groupId)}/schedule`);
            renderAdminSchedule();
        } catch (error) { showToast(error.message, true); }
    }
}

function renderAdminSchedule() {
    const tbody = document.getElementById('adminScheduleTable');
    tbody.innerHTML = adminSchedule.length ? adminSchedule.map(item => `
        <tr>
            <td><span class="badge bg-primary-subtle text-primary">${scheduleDays[item.weekday]}</span></td>
            <td class="fw-bold">${item.start_time} - ${item.end_time}</td>
            <td><div class="fw-bold">${libraryEsc(item.subject_name)}</div>${item.notes ? `<small class="text-muted">${libraryEsc(item.notes)}</small>` : ''}</td>
            <td>${libraryEsc(item.classroom || '—')}</td>
            <td>${libraryEsc(item.teacher_name || '—')}</td>
            <td class="text-nowrap">
                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openScheduleEntryModal(${item.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger rounded-pill" onclick="deleteScheduleEntry(${item.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>`).join('') : '<tr><td colspan="6" class="text-center py-5 text-muted">Este horario todavía no tiene clases registradas.</td></tr>';
}

function openScheduleEntryModal(id = null) {
    initializeScheduleAdmin();
    const mode = getScheduleMode();
    const item = adminSchedule.find(row => row.id === id) || {};
    
    let selectedValue = '';
    if (mode === 'student') {
        selectedValue = document.getElementById('scheduleStudentSelect')?.value || '';
    } else {
        selectedValue = document.getElementById('scheduleGroupSelect')?.value || '';
    }
    
    document.getElementById('scheduleEntryId').value = id || '';
    document.getElementById('scheduleEntryModalTitle').textContent = id ? 'Editar clase' : 'Agregar clase';
    document.getElementById('scheduleModalStudent').value = selectedValue;
    document.getElementById('scheduleModalStudent').disabled = Boolean(id);
    document.getElementById('scheduleWeekday').value = item.weekday || 1;
    document.getElementById('scheduleSubject').value = item.subject_name || '';
    document.getElementById('scheduleStart').value = item.start_time || '';
    document.getElementById('scheduleEnd').value = item.end_time || '';
    document.getElementById('scheduleClassroom').value = item.classroom || '';
    document.getElementById('scheduleTeacher').value = item.teacher_name || '';
    document.getElementById('scheduleColor').value = item.color || 'blue';
    document.getElementById('scheduleNotes').value = item.notes || '';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('scheduleEntryModal')).show();
}

async function saveScheduleEntry() {
    const id = document.getElementById('scheduleEntryId').value;
    const targetValue = document.getElementById('scheduleModalStudent').value;
    const mode = getScheduleMode();
    
    const payload = {
        weekday: Number(document.getElementById('scheduleWeekday').value),
        subject_name: document.getElementById('scheduleSubject').value.trim(),
        start_time: document.getElementById('scheduleStart').value,
        end_time: document.getElementById('scheduleEnd').value,
        classroom: document.getElementById('scheduleClassroom').value.trim() || null,
        teacher_name: document.getElementById('scheduleTeacher').value.trim() || null,
        color: document.getElementById('scheduleColor').value,
        notes: document.getElementById('scheduleNotes').value.trim() || null
    };
    
    if (!targetValue || !payload.subject_name || !payload.start_time || !payload.end_time) {
        showToast(mode === 'student' ? 'Completa alumno, materia y horas' : 'Completa grupo, materia y horas', true); 
        return;
    }
    
    try {
        let path = '';
        if (mode === 'student') {
            path = `/admin/students/${encodeURIComponent(targetValue)}/schedule${id ? `/${id}` : ''}`;
        } else {
            path = `/admin/groups/${encodeURIComponent(targetValue)}/schedule${id ? `/${id}` : ''}`;
        }
        
        await scheduleFetch(path, {
            method: id ? 'PUT' : 'POST',
            body: JSON.stringify(payload)
        });
        
        bootstrap.Modal.getOrCreateInstance(document.getElementById('scheduleEntryModal')).hide();
        
        if (mode === 'student') {
            document.getElementById('scheduleStudentSelect').value = targetValue;
        } else {
            document.getElementById('scheduleGroupSelect').value = targetValue;
        }
        
        showToast('Clase guardada correctamente');
        await loadAdminSchedule();
    } catch (error) { showToast(error.message, true); }
}

async function deleteScheduleEntry(id) {
    const mode = getScheduleMode();
    let targetValue = '';
    if (mode === 'student') {
        targetValue = document.getElementById('scheduleStudentSelect').value;
    } else {
        targetValue = document.getElementById('scheduleGroupSelect').value;
    }
    
    if (!targetValue || !confirm('¿Eliminar esta clase del horario?')) return;
    
    try {
        let path = '';
        if (mode === 'student') {
            path = `/admin/students/${encodeURIComponent(targetValue)}/schedule/${id}`;
        } else {
            path = `/admin/groups/${encodeURIComponent(targetValue)}/schedule/${id}`;
        }
        await scheduleFetch(path, { method:'DELETE' });
        showToast('Clase eliminada');
        await loadAdminSchedule();
    } catch (error) { showToast(error.message, true); }
}
