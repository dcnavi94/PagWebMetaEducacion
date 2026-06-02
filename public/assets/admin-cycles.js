/* Ciclos escolares */
        let allCycles = [];

        async function loadCiclosView() {
            const tbody = document.getElementById('ciclosTableBody');
            if (!tbody) return;
                tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Cargando ciclos...</td></tr>';
            try {
                const res = await fetch('/admin/school-cycles/all', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                allCycles = await res.json();
            } catch {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-danger"><i class="bi bi-wifi-off me-2"></i>Error al cargar ciclos</td></tr>';
                return;
            }

            const active = allCycles.find(c => c.is_active);
            document.getElementById('ciclosTotalCount').textContent = allCycles.length;
            document.getElementById('ciclosActivePeriod').textContent = active?.period || '—';
            document.getElementById('ciclosActiveStudents').textContent = active?.students_affected ?? 0;

            if (!allCycles.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">Sin ciclos registrados. Usa "Nuevo Ciclo" para crear uno.</td></tr>';
                return;
            }

            const fmt = d => d ? d.slice(0,10) : '—';
            const money = v => `$${(v || 0).toLocaleString('es-MX', {minimumFractionDigits:2})}`;

            tbody.innerHTML = allCycles.map(c => `
                <tr class="${c.is_active ? 'table-primary' : ''}">
                    <td class="text-muted small">${c.id}</td>
                    <td><strong>${escHtml(c.period || '—')}</strong></td>
                    <td class="small">${fmt(c.start_date)}</td>
                    <td class="small">${fmt(c.end_date)}</td>
                    <td class="small">${money(c.monthly_amount)}</td>
                    <td>${c.students_affected ?? 0}</td>
                    <td>
                        ${c.is_active
                            ? '<span class="badge bg-success rounded-pill px-3">Activo</span>'
                            : '<span class="badge bg-secondary rounded-pill px-3">Inactivo</span>'}
                    </td>
                    <td class="text-nowrap">
                        <button class="btn btn-sm btn-outline-primary rounded-pill me-1" title="Editar" onclick="openEditCycle(${c.id})">
                            <i class="bi bi-pencil"></i>
                        </button>
                        ${!c.is_active ? `
                        <button class="btn btn-sm btn-outline-success rounded-pill me-1" title="Activar ciclo" onclick="activateCycle(${c.id})">
                            <i class="bi bi-lightning-fill"></i>
                        </button>` : ''}
                        <button class="btn btn-sm btn-outline-danger rounded-pill" title="Eliminar" onclick="confirmDeleteCycle(${c.id}, '${escHtml(c.period || '')}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>`).join('');
        }

        function openCreateCycle() {
            document.getElementById('cycleEditId').value = '';
            document.getElementById('cycleFormModalTitle').innerHTML = '<i class="bi bi-calendar-plus me-2 text-primary"></i>Nuevo Ciclo Escolar';
            document.getElementById('cyclePeriod').value = '';
            document.getElementById('cycleStartDate').value = '';
            document.getElementById('cycleEndDate').value = '';
            document.getElementById('cycleMonthlyAmount').value = '';
            document.getElementById('cycleIsActive').checked = true;
            document.getElementById('cycleTuitionsTbody').innerHTML = '';
            document.getElementById('cycleTuitionsEmpty').style.display = '';
            addCycleTuitionRow();
            bootstrap.Modal.getOrCreateInstance(document.getElementById('cycleFormModal')).show();
        }

        async function openEditCycle(cycleId) {
            document.getElementById('cycleEditId').value = cycleId;
            document.getElementById('cycleFormModalTitle').innerHTML = '<i class="bi bi-pencil-square me-2 text-primary"></i>Editar Ciclo Escolar';
            document.getElementById('cycleTuitionsTbody').innerHTML = '';
            document.getElementById('cycleTuitionsEmpty').style.display = '';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('cycleFormModal')).show();
            try {
                const res = await fetch(`/admin/school-cycles/${cycleId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error();
                const c = await res.json();
                document.getElementById('cyclePeriod').value = c.period || '';
                document.getElementById('cycleStartDate').value = c.start_date ? String(c.start_date).slice(0,10) : '';
                document.getElementById('cycleEndDate').value = c.end_date ? String(c.end_date).slice(0,10) : '';
                document.getElementById('cycleMonthlyAmount').value = c.monthly_amount ?? '';
                document.getElementById('cycleIsActive').checked = !!c.is_active;
                if (c.tuitions && c.tuitions.length) {
                    c.tuitions.forEach(t => addCycleTuitionRow(t.career_id, t.modality_id, t.amount));
                    document.getElementById('cycleTuitionsEmpty').style.display = 'none';
                } else {
                    addCycleTuitionRow();
                }
            } catch {
                showToast('Error al cargar detalle del ciclo', 'danger');
            }
        }

        function addCycleTuitionRow(careerId, modalityId, amount) {
            const tbody = document.getElementById('cycleTuitionsTbody');
            document.getElementById('cycleTuitionsEmpty').style.display = 'none';
            const careers = catalogCareers || [];
            const modalities = catalogModalities || [];
            const careerOpts = careers.map(c => `<option value="${c.id}" ${c.id == careerId ? 'selected' : ''}>${escHtml(c.name)}</option>`).join('');
            const modalityOpts = modalities.map(m => `<option value="${m.id}" ${m.id == modalityId ? 'selected' : ''}>${escHtml(m.name)}</option>`).join('');
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <select class="form-select form-select-sm rounded-3 tuition-career">
                        <option value="">— Carrera —</option>
                        ${careerOpts}
                    </select>
                </td>
                <td>
                    <select class="form-select form-select-sm rounded-3 tuition-modality">
                        <option value="">— Modalidad —</option>
                        ${modalityOpts}
                    </select>
                </td>
                <td>
                    <input type="number" class="form-control form-control-sm rounded-3 tuition-amount" min="0.01" step="0.01" placeholder="0.00" value="${amount != null ? amount : ''}">
                </td>
                <td>
                    <button type="button" class="btn btn-sm btn-outline-danger rounded-pill" onclick="removeCycleTuitionRow(this)">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </td>`;
            tbody.appendChild(tr);
        }

        function removeCycleTuitionRow(btn) {
            btn.closest('tr').remove();
            if (!document.getElementById('cycleTuitionsTbody').children.length) {
                document.getElementById('cycleTuitionsEmpty').style.display = '';
            }
        }

        function collectCycleTuitions() {
            const rows = document.querySelectorAll('#cycleTuitionsTbody tr');
            const tuitions = [];
            for (const row of rows) {
                const careerId = parseInt(row.querySelector('.tuition-career')?.value);
                const modalityId = parseInt(row.querySelector('.tuition-modality')?.value);
                const amount = parseFloat(row.querySelector('.tuition-amount')?.value);
                if (!careerId || !modalityId || isNaN(amount) || amount <= 0) return null;
                tuitions.push({ career_id: careerId, modality_id: modalityId, amount });
            }
            return tuitions;
        }

        async function saveCycleForm() {
            const editId = document.getElementById('cycleEditId').value;
            const period = document.getElementById('cyclePeriod').value.trim();
            const startDate = document.getElementById('cycleStartDate').value;
            const endDate = document.getElementById('cycleEndDate').value;
            const monthlyAmount = parseFloat(document.getElementById('cycleMonthlyAmount').value) || 0;
            const isActive = document.getElementById('cycleIsActive').checked;

            if (!period) { showToast('El periodo es obligatorio', 'warning'); return; }
            if (!startDate || !endDate) { showToast('Las fechas son obligatorias', 'warning'); return; }
            if (startDate >= endDate) { showToast('La fecha de inicio debe ser anterior a la de fin', 'warning'); return; }

            const tuitions = collectCycleTuitions();
            if (tuitions === null) { showToast('Completa correctamente todos los costos (carrera, modalidad y monto > 0)', 'warning'); return; }
            if (!tuitions.length) { showToast('Agrega al menos un costo por carrera y modalidad', 'warning'); return; }

            const payload = {
                period,
                start_date: startDate + 'T00:00:00',
                end_date: endDate + 'T00:00:00',
                monthly_amount: monthlyAmount,
                is_active: isActive,
                tuitions
            };

            const url = editId
                ? `/admin/school-cycles/${editId}`
                : '/admin/school-cycle';
            const method = editId ? 'PUT' : 'POST';

            try {
                const res = await fetch(url, {
                    method,
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al guardar ciclo', 'danger');
                    return;
                }
                bootstrap.Modal.getOrCreateInstance(document.getElementById('cycleFormModal')).hide();
                showToast(editId ? 'Ciclo actualizado correctamente' : 'Ciclo creado correctamente', 'success');
                await loadCiclosView();
                loadSchoolCycle();
            } catch {
                showToast('Error de conexión', 'danger');
            }
        }

        async function activateCycle(cycleId) {
            try {
                const res = await fetch(`/admin/school-cycles/${cycleId}/set-active`, {
                    method: 'PATCH',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al activar ciclo', 'danger');
                    return;
                }
                showToast('Ciclo activado correctamente', 'success');
                await loadCiclosView();
                loadSchoolCycle();
            } catch {
                showToast('Error de conexión', 'danger');
            }
        }

        function confirmDeleteCycle(cycleId, period) {
            document.getElementById('deleteCycleId').value = cycleId;
            document.getElementById('deleteCyclePeriodLabel').textContent = period;
            bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteCycleModal')).show();
        }

        async function doDeleteCycle() {
            const cycleId = document.getElementById('deleteCycleId').value;
            try {
                const res = await fetch(`/admin/school-cycles/${cycleId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al eliminar ciclo', 'danger');
                    return;
                }
                bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteCycleModal')).hide();
                showToast('Ciclo eliminado correctamente', 'success');
                await loadCiclosView();
                loadSchoolCycle();
            } catch {
                showToast('Error de conexión', 'danger');
            }
        }
