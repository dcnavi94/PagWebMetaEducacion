let labMaterials = [];
let labRequests = [];

async function labFetch(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: {
            'Authorization': `Bearer ${token}`,
            ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        }
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'No se pudo completar la operación');
    }
    return response.status === 204 ? null : response.json();
}

async function loadLabAdmin() {
    try {
        [labMaterials, labRequests] = await Promise.all([
            labFetch('/admin/laboratory/materials'),
            labFetch('/admin/laboratory/requests')
        ]);
        renderLabMaterials();
        renderLabRequests();
    } catch (error) { showToast(error.message, true); }
}

function renderLabMaterials() {
    const tbody = document.getElementById('labMaterialsTable');
    if (!tbody) return;
    tbody.innerHTML = labMaterials.length ? labMaterials.map(item => `
        <tr>
            <td><div class="fw-bold">${libraryEsc(item.name)}</div><small class="text-muted">${libraryEsc(item.description || '')}</small></td>
            <td>${libraryEsc(item.code || '—')}</td>
            <td>${libraryEsc(item.category || 'General')}</td>
            <td>${libraryEsc(item.storage_location || '—')}</td>
            <td><span class="fw-bold ${item.available_units ? 'text-success' : 'text-danger'}">${item.available_units}</span> / ${item.total_units}</td>
            <td class="text-nowrap">
                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openLabMaterialModal(${item.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger rounded-pill" onclick="deleteLabMaterial(${item.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>`).join('') : '<tr><td colspan="6" class="text-center py-4 text-muted">No hay material registrado.</td></tr>';
}

const labStatusMap = {
    'pendiente': 'Pendiente',
    'aprobado': 'Aprobado',
    'prestado': 'Prestado',
    'devuelto': 'Devuelto',
    'rechazado': 'Rechazado'
};

function renderLabRequests() {
    const tbody = document.getElementById('labRequestsTable');
    if (!tbody) return;
    const displayStatuses = ['Pendiente', 'Aprobado', 'Prestado', 'Devuelto', 'Rechazado'];
    tbody.innerHTML = labRequests.length ? labRequests.map(item => {
        const currentStatus = (item.status || '').toLowerCase();
        return `
        <tr>
            <td><div class="fw-bold">${libraryEsc(item.student_name || item.student_username)}</div><small>${libraryEsc(item.student_username)}</small></td>
            <td>${libraryEsc(item.material?.name || 'Material')}</td>
            <td class="fw-bold">${item.quantity}</td>
            <td>${libraryEsc(item.project_name || '—')}</td>
            <td><input type="date" class="form-control form-control-sm" id="labDue${item.id}" value="${item.due_at ? item.due_at.slice(0,10) : ''}"></td>
            <td><span class="badge bg-light text-dark border">${libraryEsc(labStatusMap[currentStatus] || item.status)}</span></td>
            <td>
                <div class="d-flex gap-1">
                    <select class="form-select form-select-sm" id="labStatus${item.id}">
                        ${displayStatuses.map(label => {
                            const val = Object.keys(labStatusMap).find(key => labStatusMap[key] === label);
                            return `<option value="${val}" ${val === currentStatus ? 'selected' : ''}>${label}</option>`;
                        }).join('')}
                    </select>
                    <button class="btn btn-sm btn-primary" onclick="updateLabRequest(${item.id})"><i class="bi bi-check-lg"></i></button>
                </div>
            </td>
        </tr>`;
    }).join('') : '<tr><td colspan="7" class="text-center py-4 text-muted">No hay solicitudes.</td></tr>';
}

function labField(label, id, value = '', cols = 6, type = 'text') {
    return `<div class="col-md-${cols}"><label class="form-label">${label}</label><input type="${type}" min="0" class="form-control" id="${id}" value="${libraryEsc(value)}"></div>`;
}

function openLabMaterialModal(id = null) {
    const item = labMaterials.find(row => row.id === id) || {};
    document.getElementById('labMaterialId').value = id || '';
    document.getElementById('labMaterialModalTitle').textContent = id ? 'Editar material' : 'Nuevo material';
    document.getElementById('labMaterialFields').innerHTML = `
        ${labField('Nombre','labName',item.name,8)}
        ${labField('Código','labCode',item.code,4)}
        ${labField('Categoría','labCategory',item.category,6)}
        ${labField('Ubicación','labLocation',item.storage_location,6)}
        ${labField('URL de imagen','labImage',item.image_url,12)}
        ${labField('Unidades totales','labTotal',item.total_units ?? 1,6,'number')}
        ${labField('Unidades disponibles','labAvailable',item.available_units ?? item.total_units ?? 1,6,'number')}
        <div class="col-12"><label class="form-label">Descripción</label><textarea class="form-control" id="labDescription" rows="3">${libraryEsc(item.description || '')}</textarea></div>
        <div class="col-12"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="labActive" ${item.is_active !== false ? 'checked' : ''}><label class="form-check-label">Visible para alumnos</label></div></div>`;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('labMaterialModal')).show();
}

async function saveLabMaterial() {
    const id = document.getElementById('labMaterialId').value;
    const payload = {
        name: document.getElementById('labName').value.trim(),
        code: document.getElementById('labCode').value.trim() || null,
        category: document.getElementById('labCategory').value.trim() || null,
        storage_location: document.getElementById('labLocation').value.trim() || null,
        image_url: document.getElementById('labImage').value.trim() || null,
        total_units: Number(document.getElementById('labTotal').value),
        available_units: Number(document.getElementById('labAvailable').value),
        description: document.getElementById('labDescription').value.trim() || null,
        is_active: document.getElementById('labActive').checked
    };
    if (!payload.name) { showToast('El nombre es obligatorio', true); return; }
    try {
        await labFetch(`/admin/laboratory/materials${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('labMaterialModal')).hide();
        showToast('Material guardado');
        await loadLabAdmin();
    } catch (error) { showToast(error.message, true); }
}

async function deleteLabMaterial(id) {
    if (!confirm('¿Eliminar este material?')) return;
    try {
        await labFetch(`/admin/laboratory/materials/${id}`, { method: 'DELETE' });
        showToast('Material eliminado');
        await loadLabAdmin();
    } catch (error) { showToast(error.message, true); }
}

async function updateLabRequest(id) {
    const status = document.getElementById(`labStatus${id}`).value;
    const due = document.getElementById(`labDue${id}`).value;
    try {
        await labFetch(`/admin/laboratory/requests/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ status, due_at: due ? `${due}T23:59:00` : null })
        });
        showToast('Solicitud actualizada');
        await loadLabAdmin();
    } catch (error) { showToast(error.message, true); }
}
