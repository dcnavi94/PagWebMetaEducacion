let libraryResources = [];
let libraryBooks = [];
let libraryLoans = [];

const libraryHeaders = () => ({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
});

const libraryEsc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

async function libraryFetch(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        headers: { ...libraryHeaders(), ...(options.headers || {}) }
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'No se pudo completar la operación');
    }
    return response.status === 204 ? null : response.json();
}

async function loadLibraryAdmin() {
    try {
        [libraryResources, libraryBooks, libraryLoans] = await Promise.all([
            libraryFetch('/admin/library/resources'),
            libraryFetch('/admin/library/books'),
            libraryFetch('/admin/library/loans')
        ]);
        renderLibraryResources();
        renderLibraryBooks();
        renderLibraryLoans();
    } catch (error) {
        showToast(error.message, true);
    }
}

function renderLibraryResources() {
    const tbody = document.getElementById('libraryResourcesTable');
    if (!tbody) return;
    tbody.innerHTML = libraryResources.length ? libraryResources.map(item => `
        <tr>
            <td><div class="fw-bold">${libraryEsc(item.title)}</div><small class="text-muted">${libraryEsc(item.author || '')}</small></td>
            <td><span class="badge bg-primary-subtle text-primary">${item.resource_type === 'file' ? 'Archivo' : 'Enlace'}</span></td>
            <td>${libraryEsc(item.category || 'General')}</td>
            <td><span class="badge ${item.is_active ? 'bg-success' : 'bg-secondary'}">${item.is_active ? 'Activo' : 'Oculto'}</span></td>
            <td class="text-nowrap">
                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openLibraryResourceModal(${item.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger rounded-pill" onclick="deleteLibraryItem('resources',${item.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>`).join('') : '<tr><td colspan="5" class="text-center py-4 text-muted">No hay recursos virtuales.</td></tr>';
}

function renderLibraryBooks() {
    const tbody = document.getElementById('libraryBooksTable');
    if (!tbody) return;
    tbody.innerHTML = libraryBooks.length ? libraryBooks.map(item => `
        <tr>
            <td><div class="fw-bold">${libraryEsc(item.title)}</div><small class="text-muted">${libraryEsc(item.author || 'Sin autor')}</small></td>
            <td>${libraryEsc(item.isbn || '—')}</td>
            <td>${libraryEsc(item.shelf_location || '—')}</td>
            <td><span class="fw-bold ${item.available_copies ? 'text-success' : 'text-danger'}">${item.available_copies}</span> / ${item.total_copies}</td>
            <td><span class="badge ${item.is_active ? 'bg-success' : 'bg-secondary'}">${item.is_active ? 'Activo' : 'Inactivo'}</span></td>
            <td class="text-nowrap">
                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openLibraryBookModal(${item.id})"><i class="bi bi-pencil"></i></button>
                <button class="btn btn-sm btn-outline-danger rounded-pill" onclick="deleteLibraryItem('books',${item.id})"><i class="bi bi-trash"></i></button>
            </td>
        </tr>`).join('') : '<tr><td colspan="6" class="text-center py-4 text-muted">No hay libros registrados.</td></tr>';
}

const libraryStatusMap = {
    'pendiente': 'Pendiente',
    'aprobado': 'Aprobado',
    'prestado': 'Prestado',
    'devuelto': 'Devuelto',
    'rechazado': 'Rechazado'
};

function renderLibraryLoans() {
    const tbody = document.getElementById('libraryLoansTable');
    if (!tbody) return;
    const displayStatuses = ['Pendiente', 'Aprobado', 'Prestado', 'Devuelto', 'Rechazado'];
    tbody.innerHTML = libraryLoans.length ? libraryLoans.map(item => {
        const currentStatus = (item.status || '').toLowerCase();
        return `
        <tr>
            <td><div class="fw-bold">${libraryEsc(item.student_name || item.student_username)}</div><small>${libraryEsc(item.student_username)}</small></td>
            <td>${libraryEsc(item.book?.title || 'Libro')}</td>
            <td>${new Date(item.requested_at).toLocaleDateString('es-MX')}</td>
            <td><input type="date" class="form-control form-control-sm" id="libraryDue${item.id}" value="${item.due_at ? item.due_at.slice(0,10) : ''}"></td>
            <td><span class="badge bg-light text-dark border">${libraryEsc(libraryStatusMap[currentStatus] || item.status)}</span></td>
            <td>
                <div class="d-flex gap-1">
                    <select class="form-select form-select-sm" id="libraryStatus${item.id}">
                        ${displayStatuses.map(label => {
                            const val = Object.keys(libraryStatusMap).find(key => libraryStatusMap[key] === label);
                            return `<option value="${val}" ${val === currentStatus ? 'selected' : ''}>${label}</option>`;
                        }).join('')}
                    </select>
                    <button class="btn btn-sm btn-primary" onclick="updateLibraryLoan(${item.id})"><i class="bi bi-check-lg"></i></button>
                </div>
            </td>
        </tr>`;
    }).join('') : '<tr><td colspan="6" class="text-center py-4 text-muted">No hay solicitudes.</td></tr>';
}

function openLibraryResourceModal(id = null) {
    const item = libraryResources.find(row => row.id === id) || {};
    document.getElementById('libraryEditType').value = 'resources';
    document.getElementById('libraryEditId').value = id || '';
    document.getElementById('libraryEditModalTitle').textContent = id ? 'Editar recurso virtual' : 'Nuevo recurso virtual';
    document.getElementById('libraryEditFields').innerHTML = `
        ${libraryInput('Título','libTitle',item.title,true,8)}
        <div class="col-md-4"><label class="form-label">Tipo</label><select class="form-select" id="libResourceType"><option value="link" ${item.resource_type !== 'file' ? 'selected' : ''}>Enlace</option><option value="file" ${item.resource_type === 'file' ? 'selected' : ''}>Archivo</option></select></div>
        ${libraryInput('URL o ruta del archivo','libUrl',item.url,false,12)}
        <div class="col-12"><label class="form-label">Subir archivo</label><input type="file" class="form-control" id="libUploadFile" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.csv"><small class="text-muted">Al seleccionar un archivo se cargará y completará la ruta automáticamente.</small></div>
        ${libraryInput('Autor','libAuthor',item.author,false,6)}
        ${libraryInput('Categoría','libCategory',item.category,false,6)}
        <div class="col-12"><label class="form-label">Descripción</label><textarea class="form-control" id="libDescription" rows="3">${libraryEsc(item.description || '')}</textarea></div>
        ${libraryActive(item.is_active !== false)}
    `;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('libraryEditModal')).show();
}

function openLibraryBookModal(id = null) {
    const item = libraryBooks.find(row => row.id === id) || {};
    document.getElementById('libraryEditType').value = 'books';
    document.getElementById('libraryEditId').value = id || '';
    document.getElementById('libraryEditModalTitle').textContent = id ? 'Editar libro físico' : 'Nuevo libro físico';
    document.getElementById('libraryEditFields').innerHTML = `
        ${libraryInput('Título','libTitle',item.title,true,8)}
        ${libraryInput('Autor','libAuthor',item.author,false,4)}
        ${libraryInput('ISBN','libIsbn',item.isbn,false,4)}
        ${libraryInput('Categoría','libCategory',item.category,false,4)}
        ${libraryInput('Ubicación / estante','libShelf',item.shelf_location,false,4)}
        ${libraryInput('URL de portada','libCover',item.cover_url,false,12)}
        ${libraryInput('Ejemplares totales','libTotal',item.total_copies ?? 1,true,6,'number')}
        ${libraryInput('Ejemplares disponibles','libAvailable',item.available_copies ?? item.total_copies ?? 1,true,6,'number')}
        <div class="col-12"><label class="form-label">Descripción</label><textarea class="form-control" id="libDescription" rows="3">${libraryEsc(item.description || '')}</textarea></div>
        ${libraryActive(item.is_active !== false)}
    `;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('libraryEditModal')).show();
}

function libraryInput(label, id, value = '', required = false, cols = 6, type = 'text') {
    return `<div class="col-md-${cols}"><label class="form-label">${label}</label><input type="${type}" min="0" class="form-control" id="${id}" value="${libraryEsc(value)}" ${required ? 'required' : ''}></div>`;
}

function libraryActive(checked) {
    return `<div class="col-12"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="libActive" ${checked ? 'checked' : ''}><label class="form-check-label" for="libActive">Visible para alumnos</label></div></div>`;
}

async function saveLibraryItem() {
    const type = document.getElementById('libraryEditType').value;
    const id = document.getElementById('libraryEditId').value;
    const title = document.getElementById('libTitle').value.trim();
    if (!title) { showToast('El título es obligatorio', true); return; }
    let payload;
    if (type === 'resources') {
        let url = document.getElementById('libUrl').value.trim();
        const upload = document.getElementById('libUploadFile')?.files?.[0];
        if (upload) {
            const form = new FormData();
            form.append('file', upload);
            const response = await fetch('/admin/library/upload', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: form
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                showToast(error.detail || 'No se pudo subir el archivo', true);
                return;
            }
            const uploaded = await response.json();
            url = uploaded.url;
            document.getElementById('libResourceType').value = 'file';
        }
        if (!url) { showToast('La URL o ruta es obligatoria', true); return; }
        payload = {
            title, url,
            resource_type: document.getElementById('libResourceType').value,
            author: document.getElementById('libAuthor').value.trim() || null,
            category: document.getElementById('libCategory').value.trim() || null,
            description: document.getElementById('libDescription').value.trim() || null,
            is_active: document.getElementById('libActive').checked
        };
    } else {
        payload = {
            title,
            author: document.getElementById('libAuthor').value.trim() || null,
            isbn: document.getElementById('libIsbn').value.trim() || null,
            category: document.getElementById('libCategory').value.trim() || null,
            shelf_location: document.getElementById('libShelf').value.trim() || null,
            cover_url: document.getElementById('libCover').value.trim() || null,
            total_copies: Number(document.getElementById('libTotal').value),
            available_copies: Number(document.getElementById('libAvailable').value),
            description: document.getElementById('libDescription').value.trim() || null,
            is_active: document.getElementById('libActive').checked
        };
    }
    try {
        await libraryFetch(`/admin/library/${type}${id ? `/${id}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
        bootstrap.Modal.getOrCreateInstance(document.getElementById('libraryEditModal')).hide();
        showToast('Registro guardado correctamente');
        await loadLibraryAdmin();
    } catch (error) { showToast(error.message, true); }
}

async function deleteLibraryItem(type, id) {
    if (!confirm('¿Eliminar este registro de biblioteca?')) return;
    try {
        await libraryFetch(`/admin/library/${type}/${id}`, { method: 'DELETE' });
        showToast('Registro eliminado');
        await loadLibraryAdmin();
    } catch (error) { showToast(error.message, true); }
}

async function updateLibraryLoan(id) {
    const status = document.getElementById(`libraryStatus${id}`).value;
    const dueValue = document.getElementById(`libraryDue${id}`).value;
    try {
        await libraryFetch(`/admin/library/loans/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ status, due_at: dueValue ? `${dueValue}T23:59:00` : null })
        });
        showToast('Solicitud actualizada');
        await loadLibraryAdmin();
    } catch (error) { showToast(error.message, true); }
}
