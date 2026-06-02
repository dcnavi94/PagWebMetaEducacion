        async function registerStudent() {
            const form = document.getElementById('registerStudentForm');
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }

            const errorDiv = document.getElementById('registerError');
            errorDiv.style.display = 'none';

            const careerSelection = getCatalogSelection('newMajor');
            const modalitySelection = getCatalogSelection('newModalidad');
            if (!document.getElementById('newCursando').value) {
                syncTrackSelectWithCareer('newMajor', 'newCursando');
            }

            const payload = {
                username: document.getElementById('newUsername').value,
                full_name: document.getElementById('newFullName').value,
                curp: document.getElementById('newCurp').value.trim().toUpperCase(),
                seg_unique_key: document.getElementById('newSegUniqueKey').value.trim(),
                email: document.getElementById('newEmail').value,
                password: document.getElementById('newPassword').value,
                role: 'student',
                career_id: careerSelection.id,
                carrera: careerSelection.name,
                modality_id: modalitySelection.id,
                modalidad: modalitySelection.name,
                semestre: document.getElementById('newSemester').value,
                grupo: document.getElementById('newGroup').value,
                cursando: document.getElementById('newCursando').value
            };

            try {
                const response = await fetch('/admin/students', {
                    method: 'POST',
                    headers: { 
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    showToast('Alumno registrado exitosamente');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('registerStudentModal'));
                    modal.hide();
        /* Alumnos: eliminar */
                } else {
                    const errorData = await response.json();
                    errorDiv.textContent = errorData.detail || 'Error al registrar al alumno';
                    errorDiv.style.display = 'block';
                }
            } catch (error) {
                console.error('Error:', error);
                errorDiv.textContent = 'Error de conexion con el servidor';
                errorDiv.style.display = 'block';
            }
        }

        async function registerTeacher(event) {
            event.preventDefault();
            const form = document.getElementById('registerTeacherForm');
            if (!form.checkValidity()) { form.reportValidity(); return; }

            const errorDiv = document.getElementById('registerTeacherError');
            errorDiv.style.display = 'none';

            const payload = {
                username: document.getElementById('newTeacherUsername').value.trim(),
                full_name: document.getElementById('newTeacherName').value.trim(),
                email: document.getElementById('newTeacherEmail').value.trim(),
                password: document.getElementById('newTeacherPassword').value,
                role: 'teacher'
            };

            try {
                const response = await fetch('/admin/teachers', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    showToast('aDocente registrado exitosamente!');
                    bootstrap.Modal.getInstance(document.getElementById('registerTeacherModal')).hide();
                    form.reset();
                    loadAdminData();
                } else {
                    const err = await response.json();
                    errorDiv.textContent = err.detail || 'Error al registrar al docente';
                    errorDiv.style.display = 'block';
                }
            } catch (e) {
                errorDiv.textContent = 'No se pudo conectar con el servidor. Verifica que el backend este activo.';
                errorDiv.style.display = 'block';
            }
        }

        // Limpiar campos del modal de docente cada vez que se abre
        document.getElementById('registerTeacherModal').addEventListener('show.bs.modal', () => {
            document.getElementById('registerTeacherForm').reset();
            document.getElementById('registerTeacherError').style.display = 'none';
            // Forzar limpieza de campos (contra autocompletado agresivo)
            setTimeout(() => {
                ['newTeacherName','newTeacherUsername','newTeacherEmail','newTeacherPassword']
                    .forEach(id => { const el = document.getElementById(id); if(el) el.value = ''; });
            }, 50);
        });

        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('show');
            document.getElementById('sidebarOverlay').classList.toggle('show');
        }

        // ? Gestion de Grupos ?

        async function reloadStudents() {
            try {
                const res = await fetch('/admin/students', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    allStudents = await res.json();
                    const enrollmentRes = await fetch('/admin/student-enrollments', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (enrollmentRes.ok) {
                        allStudentEnrollments = await enrollmentRes.json();
                    }
                    syncStudentsWithActiveEnrollments();
                    filteredStudents = [...allStudents];
                    populateGroupFilter();
                    renderStudents(filteredStudents);
                    renderPagination();
                }
            } catch(e) { /* silent */ }
        }

        let currentGroupGrupo = null;
        let currentGroupCarrera = null;
        let currentGroupId = null;
        let currentGroupStudents = [];
        let createGroupAllStudents = [];

        function openCreateGroup() {
            // Populate carrera select from catalog
            const sel = document.getElementById('newGroupCarrera');
            sel.innerHTML = '<option value="">Selecciona carrera...</option>' +
                catalogCareers.map(c => `<option value="${escHtml(c.name)}">${escHtml(c.name)}</option>`).join('');
            document.getElementById('newGroupName').value = '';
            document.getElementById('createGroupSearchInput').value = '';
            document.getElementById('createGroupSelectedCount').textContent = '0 seleccionados';
            document.getElementById('createGroupSelectAll').checked = false;

            createGroupAllStudents = [...allStudents];
            renderCreateGroupStudentList(createGroupAllStudents);
            bootstrap.Modal.getOrCreateInstance(document.getElementById('createGroupModal')).show();
        }

        function renderCreateGroupStudentList(students) {
            const container = document.getElementById('createGroupStudentList');
            if (!students.length) {
                container.innerHTML = '<p class="text-muted small p-3">Sin alumnos disponibles.</p>';
                updateCreateGroupCount();
                return;
            }

            const sinGrupo = students.filter(s => !s.grupo);
            const conGrupo = students.filter(s => s.grupo);

            const renderRow = s => `
                <label class="d-flex align-items-center gap-2 px-3 py-2 border-bottom create-group-student-row"
                    style="cursor:pointer;" onmouseover="this.style.background='#f8f9fa'" onmouseout="this.style.background=''">
                    <input type="checkbox" class="form-check-input create-group-cb flex-shrink-0"
                        value="${escHtml(s.username)}" onchange="updateCreateGroupCount()">
                    <div class="flex-grow-1 min-w-0">
                        <div class="fw-semibold small text-truncate">${escHtml(s.full_name || s.username)}</div>
                        <div class="text-muted" style="font-size:0.72rem">${escHtml(s.username)}
                            ${s.carrera ? `· ${escHtml(s.carrera)}` : ''}
                        </div>
                    </div>
                    ${s.grupo ? `<span class="badge bg-warning text-dark flex-shrink-0" title="Sera movido de este grupo">Grupo ${escHtml(s.grupo)}</span>` : ''}
                </label>`;

            let html = '';
            if (sinGrupo.length) {
                html += `<div class="px-3 py-1 bg-light border-bottom"><small class="text-success fw-semibold"><i class="bi bi-person-plus me-1"></i>Sin grupo (${sinGrupo.length})</small></div>`;
                html += sinGrupo.map(renderRow).join('');
            }
            if (conGrupo.length) {
                html += `<div class="px-3 py-1 bg-warning bg-opacity-10 border-bottom border-top mt-1"><small class="text-warning fw-semibold"><i class="bi bi-arrow-left-right me-1"></i>Ya en otro grupo - seran movidos (${conGrupo.length})</small></div>`;
                html += conGrupo.map(renderRow).join('');
            }

            container.innerHTML = html;
            updateCreateGroupCount();
        }

        function filterCreateGroupStudents() {
            // Save checked state before re-render
            const checked = new Set([...document.querySelectorAll('.create-group-cb:checked')].map(c => c.value));
            const q = document.getElementById('createGroupSearchInput').value.toLowerCase();
            const filtered = createGroupAllStudents.filter(s =>
                (s.username || '').toLowerCase().includes(q) ||
                (s.full_name || '').toLowerCase().includes(q) ||
                (s.carrera || '').toLowerCase().includes(q)
            );
            renderCreateGroupStudentList(filtered);
            // Restore checked state
            document.querySelectorAll('.create-group-cb').forEach(c => { if (checked.has(c.value)) c.checked = true; });
            updateCreateGroupCount();
        }

        function toggleCreateGroupSelectAll(cb) {
            document.querySelectorAll('.create-group-cb').forEach(c => { c.checked = cb.checked; });
            updateCreateGroupCount();
        }

        function updateCreateGroupCount() {
            const n = document.querySelectorAll('.create-group-cb:checked').length;
            document.getElementById('createGroupSelectedCount').textContent = `${n} seleccionado${n !== 1 ? 's' : ''}`;
        }

        async function doCreateGroup() {
            const grupo = document.getElementById('newGroupName').value.trim();
            const carrera = document.getElementById('newGroupCarrera').value.trim();
            if (!grupo) { showToast('Escribe el nombre del grupo', 'warning'); return; }
            if (!carrera) { showToast('Selecciona la carrera del grupo', 'warning'); return; }

            const usernames = [...document.querySelectorAll('.create-group-cb:checked')].map(c => c.value);

            // Warn if any selected student is already in a different group
            const toMove = allStudents.filter(s => usernames.includes(s.username) && s.grupo && s.grupo !== grupo);
            if (toMove.length > 0) {
                const names = toMove.map(s => `${s.full_name || s.username} (Grupo ${s.grupo})`).join(', ');
                if (!confirm(`Los siguientes alumnos seran MOVIDOS de su grupo actual:\n\n${names}\n\n¿Continuar?`)) return;
            }

            try {
                await fetch('/admin/groups', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: grupo, is_active: true })
                });
            } catch (error) {
                console.error('Error creating formal group', error);
            }

            // Create/update each selected student's enrollment group
            let ok = 0, fail = 0;
            for (const username of usernames) {
                try {
                    const res = await fetch('/admin/student-enrollments/move-group', {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            username,
                            group_name: grupo,
                            reason: `Alta o asignacion al grupo ${grupo}`
                        })
                    });
                    res.ok ? ok++ : fail++;
                } catch { fail++; }
            }

            bootstrap.Modal.getOrCreateInstance(document.getElementById('createGroupModal')).hide();
            if (!usernames.length) {
                showToast(`Grupo "${grupo}" creado. Puedes asignar alumnos después.`, 'success');
            } else if (fail) {
                showToast(`Grupo creado con ${ok} alumnos. ${fail} fallaron.`, 'warning');
            } else {
                showToast(`Grupo "${grupo}" creado con ${ok} alumnos`, 'success');
            }
            await reloadStudents();
            await loadGroups();
            const createdGroup = allGroupSummaries.find(item => item.grupo === grupo && item.carrera === carrera) || allGroupSummaries.find(item => item.grupo === grupo);
            if (createdGroup) selectGroup(createdGroup.group_id, createdGroup.grupo, createdGroup.carrera);
        }

        async function loadGroups() {
            const panel = document.getElementById('groupListPanel');
            panel.innerHTML = '<p class="text-muted small p-2"><span class="spinner-border spinner-border-sm me-2"></span>Cargando...</p>';
            try {
                const res = await fetch('/admin/groups', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const groups = await res.json();
                allGroupSummaries = groups;
                document.getElementById('groupsActiveCount').textContent = groups.length;
                document.getElementById('groupsAssignedStudentsCount').textContent = groups.reduce((sum, group) => sum + (group.total || 0), 0);
                document.getElementById('groupsTutorCount').textContent = groups.filter(group => !!group.tutor_name).length;
                if (!groups.length) {
                    panel.innerHTML = '<p class="text-muted small p-3">Sin grupos registrados. Usa <strong>+</strong> para crear uno.</p>';
                    return;
                }
                panel.innerHTML = groups.map(g => `
                    <button class="btn btn-outline-secondary btn-sm w-100 text-start mb-1 rounded-3 group-btn"
                        data-group-id="${g.group_id}"
                        data-grupo="${escHtml(g.grupo)}" data-carrera="${escHtml(g.carrera)}"
                        onclick="selectGroup(${g.group_id}, '${escHtml(g.grupo)}','${escHtml(g.carrera)}')">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <span class="fw-bold">Grupo ${escHtml(g.grupo)}</span>
                                <div class="text-muted" style="font-size:0.7rem">${escHtml(g.carrera)}</div>
                                <div class="text-muted" style="font-size:0.7rem">${escHtml(g.tutor_name || 'Sin tutor')}</div>
                            </div>
                            <span class="badge bg-primary rounded-pill">${g.total}</span>
                        </div>
                    </button>`).join('');
                // Re-highlight if a group was previously selected
                if (currentGroupId || currentGroupGrupo) {
                    const btn = currentGroupId
                        ? document.querySelector(`.group-btn[data-group-id="${currentGroupId}"]`)
                        : document.querySelector(`.group-btn[data-grupo="${CSS.escape(currentGroupGrupo)}"][data-carrera="${CSS.escape(currentGroupCarrera)}"]`);
                    if (btn) btn.classList.add('active', 'btn-primary', 'text-white');
                }
            } catch(e) {
                panel.innerHTML = `<p class="text-danger small p-2">Error al cargar grupos.</p>`;
                console.error('loadGroups error:', e);
            }
        }

        function escHtml(s) {
            return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }

        async function selectGroup(groupId, grupo, carrera) {
            if (typeof groupId !== 'number') {
                carrera = grupo;
                grupo = groupId;
                const summary = allGroupSummaries.find(item => item.grupo === grupo && item.carrera === carrera);
                groupId = summary?.group_id || 0;
            }

            currentGroupId = groupId;
            currentGroupGrupo = grupo;
            currentGroupCarrera = carrera;

            // Highlight selected
            document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active', 'btn-primary', 'text-white'));
            const selected = groupId
                ? document.querySelector(`.group-btn[data-group-id="${groupId}"]`)
                : document.querySelector(`.group-btn[data-grupo="${CSS.escape(grupo)}"][data-carrera="${CSS.escape(carrera)}"]`);
            if (selected) { selected.classList.add('active', 'btn-primary', 'text-white'); }

            const panel = document.getElementById('groupDetailPanel');
            panel.innerHTML = '<div class="dashboard-card text-center py-5 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Cargando detalle del grupo...</div>';

            let students = [];
            let groupDetail = null;
            if (groupId) {
                try {
                    const [groupRes, studentsRes] = await Promise.all([
                        fetch(`/admin/groups/${groupId}`, { headers: { 'Authorization': `Bearer ${token}` } }),
                        fetch(`/admin/groups/${groupId}/students`, { headers: { 'Authorization': `Bearer ${token}` } })
                    ]);
                    if (groupRes.ok) groupDetail = await groupRes.json();
                    if (studentsRes.ok) {
                        const enrollments = await studentsRes.json();
                        students = enrollments.map(enrollment => ({
                            username: enrollment.student?.username,
                            full_name: enrollment.student?.full_name,
                            semestre: enrollment.semester,
                            enrollment_status: enrollment.enrollment_status,
                            carrera: enrollment.career?.name || carrera,
                            grupo: enrollment.group?.name || grupo
                        }));
                    }
                } catch (error) {
                    console.error('Error loading group detail', error);
                }
            }
            if (!students.length) {
                students = allStudents.filter(s => s.grupo === grupo && (s.carrera || 'Sin carrera') === carrera);
            }
            currentGroupStudents = students;

            const enrollBadge = s => {
                const map = {'Inscrito':'success','No Inscrito':'secondary','Baja Temporal':'warning','Baja Definitiva':'danger','Graduado':'info'};
                return `<span class="badge bg-${map[s]||'secondary'}">${s}</span>`;
            };

            panel.innerHTML = `
                    <div class="dashboard-card mb-3">
                        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
                            <div>
                                <h5 class="fw-bold mb-0 d-flex align-items-center gap-2" id="groupNameHeader">
                                    Grupo <span class="text-primary" id="groupNameDisplay">${escHtml(grupo)}</span>
                                    <button class="btn btn-sm btn-link p-0 text-muted" title="Editar nombre" onclick="inlineEditGroupName(${groupId}, '${escHtml(grupo)}')">
                                        <i class="bi bi-pencil-square fs-6"></i>
                                    </button>
                                </h5>
                                <p class="text-muted small mb-0">${escHtml(carrera)} &bull; ${students.length} alumnos &bull; ${escHtml(groupDetail?.tutor?.full_name || groupDetail?.tutor?.username || 'Sin tutor')}</p>
                            </div>
                            <div class="d-flex gap-2 flex-wrap">
                                <button class="btn btn-sm btn-outline-secondary rounded-pill" onclick="openEditGroup(${groupId})">
                                    <i class="bi bi-sliders me-1"></i>Editar Grupo
                                </button>
                                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openBulkEnroll()">
                                    <i class="bi bi-person-check me-1"></i>Cambiar Inscripcion
                                </button>
                                <button class="btn btn-sm btn-outline-success rounded-pill" onclick="openBulkAssign()">
                                    <i class="bi bi-book me-1"></i>Inscribir Materia
                                </button>
                                <button class="btn btn-sm btn-outline-warning rounded-pill" onclick="openAddStudentToGroup()">
                                    <i class="bi bi-person-plus me-1"></i>Agregar Alumno
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="dashboard-card p-0 overflow-hidden">
                        <div class="table-responsive">
                            <table class="table table-admin mb-0">
                                <thead>
                                    <tr>
                                        <th><input type="checkbox" id="groupSelectAll" onchange="toggleSelectAllGroup(this)"></th>
                                        <th>Matricula</th>
                                        <th>Nombre</th>
                                        <th>Semestre</th>
                                        <th>Inscripcion</th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${students.length === 0
                                        ? '<tr><td colspan="6" class="text-center py-4 text-muted">Sin alumnos en este grupo.</td></tr>'
                                        : students.map(s => `
                                        <tr>
                                            <td><input type="checkbox" class="group-student-cb" value="${escHtml(s.username)}"></td>
                                            <td><span class="fw-bold text-primary">${escHtml(s.username)}</span></td>
                                            <td>${escHtml(s.full_name || '?')}</td>
                                            <td>${escHtml(s.semestre || '?')}</td>
                                            <td>${enrollBadge(s.enrollment_status || 'No Inscrito')}</td>
                                            <td>
                                                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openViewStudent('${escHtml(s.username)}')">
                                                    <i class="bi bi-eye"></i>
                                                </button>
                                                <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="removeStudentFromGroup('${escHtml(s.username)}', '${escHtml(grupo)}', '${escHtml(carrera)}')">
                                                    <i class="bi bi-x-lg"></i>
                                                </button>
                                            </td>
                                        </tr>`).join('')
                                    }
                                </tbody>
                            </table>
                        </div>
                    </div>`;
        }

        function inlineEditGroupName(groupId, currentName) {
            const header = document.getElementById('groupNameHeader');
            if (!header) return;
            header.innerHTML = `
                <span class="text-muted fw-normal">Grupo</span>
                <input id="groupNameInput" class="form-control form-control-sm d-inline-block ms-1"
                    style="width:160px" value="${escHtml(currentName)}" maxlength="60" autofocus>
                <button class="btn btn-sm btn-primary rounded-pill" onclick="saveGroupRename(${groupId})">
                    <i class="bi bi-check-lg"></i>
                </button>
                <button class="btn btn-sm btn-outline-secondary rounded-pill" onclick="selectGroup(${groupId}, '${escHtml(currentName)}', currentGroupCarrera)">
                    <i class="bi bi-x-lg"></i>
                </button>`;
            const input = document.getElementById('groupNameInput');
            if (input) { input.focus(); input.select(); }
        }

        function openEditGroup(groupId) {
            if (!groupId) return;
            const summary = allGroupSummaries.find(g => g.group_id === groupId);
            document.getElementById('editGroupId').value = groupId;
            document.getElementById('editGroupNameLabel').textContent = summary ? summary.grupo : '';

            // Populate career select
            const careerSel = document.getElementById('editGroupCareer');
            careerSel.innerHTML = '<option value="">Sin carrera</option>' +
                catalogCareers.map(c => `<option value="${c.id || ''}" data-name="${escHtml(c.name)}">${escHtml(c.name)}</option>`).join('');
            // Pre-select current career
            if (summary?.career_id) {
                careerSel.value = summary.career_id;
            } else if (summary?.carrera && summary.carrera !== 'Sin carrera') {
                // fallback: match by name
                const opt = [...careerSel.options].find(o => o.dataset.name === summary.carrera);
                if (opt) careerSel.value = opt.value;
            }

            // Populate tutor select
            const tutorSel = document.getElementById('editGroupTutor');
            tutorSel.innerHTML = '<option value="">Sin tutor</option>' +
                (allTeachers || []).map(t => `<option value="${escHtml(t.username)}">${escHtml(t.full_name || t.username)}</option>`).join('');
            // Pre-select current tutor by id (or fallback to name match)
            if (summary?.tutor_id) {
                const teacher = allTeachers.find(t => t.id === summary.tutor_id);
                if (teacher) tutorSel.value = teacher.username;
            } else if (summary?.tutor_name) {
                const teacher = allTeachers.find(t => t.full_name === summary.tutor_name || t.username === summary.tutor_name);
                if (teacher) tutorSel.value = teacher.username;
            }

            bootstrap.Modal.getOrCreateInstance(document.getElementById('editGroupModal')).show();
        }

        async function saveEditGroup() {
            const groupId = parseInt(document.getElementById('editGroupId').value);
            if (!groupId) return;

            const careerSel = document.getElementById('editGroupCareer');
            const tutorSel = document.getElementById('editGroupTutor');

            const careerId = careerSel.value ? parseInt(careerSel.value) : null;
            const tutorUsername = tutorSel.value || null;

            // Resolve tutor_id from username
            let tutorId = null;
            if (tutorUsername) {
                const teacher = allTeachers.find(t => t.username === tutorUsername);
                tutorId = teacher?.id || null;
            }

            try {
                const res = await fetch(`/admin/groups/${groupId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ career_id: careerId, tutor_id: tutorId })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al guardar cambios del grupo', 'danger');
                    return;
                }
                bootstrap.Modal.getOrCreateInstance(document.getElementById('editGroupModal')).hide();
                showToast('Grupo actualizado correctamente', 'success');
                await loadGroups();
                await selectGroup(groupId, currentGroupGrupo, currentGroupCarrera);
            } catch (e) {
                showToast('Error de conexión al actualizar grupo', 'danger');
            }
        }

        async function saveGroupRename(groupId) {
            const input = document.getElementById('groupNameInput');
            if (!input) return;
            const newName = input.value.trim();
            if (!newName) { showToast('El nombre no puede estar vacío', 'warning'); return; }
            try {
                const res = await fetch(`/admin/groups/${groupId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al renombrar grupo', 'danger');
                    return;
                }
                const updated = await res.json();
                showToast(`Grupo renombrado a "${updated.name}"`, 'success');
                currentGroupGrupo = updated.name;
                // Refresh list and reselect
                await loadGroups();
                await selectGroup(groupId, updated.name, currentGroupCarrera);
            } catch (e) {
                showToast('Error de conexión al renombrar grupo', 'danger');
            }
        }

        function toggleSelectAllGroup(cb) {
            document.querySelectorAll('.group-student-cb').forEach(c => c.checked = cb.checked);
        }

        function getSelectedGroupUsernames() {
            return [...document.querySelectorAll('.group-student-cb:checked')].map(c => c.value);
        }

        function openBulkEnroll() {
            if (!currentGroupGrupo) return;
            const selected = getSelectedGroupUsernames();
            document.getElementById('bulkEnrollGrupo').value = currentGroupGrupo;
            document.getElementById('bulkEnrollCarrera').value = currentGroupCarrera;
            document.getElementById('bulkEnrollGroupName').textContent = currentGroupGrupo + ' - ' + currentGroupCarrera;
            document.getElementById('bulkEnrollCount').textContent = selected.length ? selected.length : 'todos';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('groupBulkEnrollModal')).show();
        }

        async function doBulkEnroll() {
            const grupo = document.getElementById('bulkEnrollGrupo').value;
            const carrera = document.getElementById('bulkEnrollCarrera').value;
            const status = document.getElementById('bulkEnrollStatus').value;
            const selected = getSelectedGroupUsernames();
            const body = { grupo, carrera, enrollment_status: status };
            if (selected.length) body.usernames = selected;

            try {
                const res = await fetch('/admin/group-actions/bulk-enrollment', {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                bootstrap.Modal.getOrCreateInstance(document.getElementById('groupBulkEnrollModal')).hide();
                showToast(`Inscripción actualizada: ${data.updated} alumnos -> ${status}`, 'success');
                await reloadStudents();
                selectGroup(currentGroupGrupo, currentGroupCarrera);
            } catch(e) {
                showToast('Error al actualizar inscripcion', 'danger');
            }
        }

        async function openBulkAssign() {
            if (!currentGroupGrupo) return;
            // Load assignments for the select
            const sel = document.getElementById('bulkAssignAssignmentId');
            sel.innerHTML = '<option value="">Cargando...</option>';
            try {
                const res = await fetch('/admin/subject-assignments', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const assignments = await res.json();
                sel.innerHTML = assignments.map(a =>
                    `<option value="${a.id}">${escHtml(a.subject?.name || `Materia #${a.subject_id}`)} ? ${escHtml(a.teacher?.full_name || a.teacher?.username || 'Sin docente')} (${escHtml(a.subject?.semester || '')})</option>`
                ).join('');
            } catch(e) {
                sel.innerHTML = '<option value="">Error al cargar</option>';
            }

            const selected = getSelectedGroupUsernames();
            document.getElementById('bulkAssignGrupo').value = currentGroupGrupo;
            document.getElementById('bulkAssignCarrera').value = currentGroupCarrera;
            document.getElementById('bulkAssignGroupName').textContent = currentGroupGrupo + ' - ' + currentGroupCarrera;
            document.getElementById('bulkAssignCount').textContent = selected.length ? selected.length : 'todos';
            bootstrap.Modal.getOrCreateInstance(document.getElementById('groupBulkAssignModal')).show();
        }

        async function doBulkAssign() {
            const grupo = document.getElementById('bulkAssignGrupo').value;
            const carrera = document.getElementById('bulkAssignCarrera').value;
            const assignmentId = parseInt(document.getElementById('bulkAssignAssignmentId').value);
            if (!assignmentId) { showToast('Selecciona una asignacion', 'warning'); return; }

            const selected = getSelectedGroupUsernames();
            const body = { grupo, carrera, assignment_id: assignmentId };
            if (selected.length) body.usernames = selected;

            try {
                const res = await fetch('/admin/group-actions/bulk-assign', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                bootstrap.Modal.getOrCreateInstance(document.getElementById('groupBulkAssignModal')).hide();
                showToast(`Materia asignada: ${data.enrolled} inscritos, ${data.reassigned} reasignados`, 'success');
            } catch(e) {
                showToast('Error al asignar materia al grupo', 'danger');
            }
        }

        let addStudentCandidates = [];

        function openAddStudentToGroup() {
            if (!currentGroupGrupo) return;
            document.getElementById('addStudentToGrupo').value = currentGroupGrupo;
            document.getElementById('addStudentToCarrera').value = currentGroupCarrera;
            document.getElementById('addStudentGroupName').textContent = currentGroupGrupo;
            document.getElementById('addStudentSearchInput').value = '';
            document.getElementById('addStudentSelectAll').checked = false;
            document.getElementById('addStudentSelectedCount').textContent = '0 seleccionados';

            // Show all students not already in this exact group
            addStudentCandidates = allStudents.filter(s =>
                !(s.grupo === currentGroupGrupo && (s.carrera || 'Sin carrera') === currentGroupCarrera)
            );
            renderAddStudentList(addStudentCandidates);
            bootstrap.Modal.getOrCreateInstance(document.getElementById('groupAddStudentModal')).show();
        }

        function renderAddStudentList(students) {
            const container = document.getElementById('addStudentList');
            if (!students.length) {
                container.innerHTML = '<p class="text-muted small p-3">No hay mas alumnos disponibles.</p>';
                return;
            }
            container.innerHTML = students.map(s => `
                <label class="d-flex align-items-center gap-2 px-3 py-2 border-bottom add-student-row"
                    style="cursor:pointer;" onmouseover="this.style.background='#f8f9fa'" onmouseout="this.style.background=''">
                    <input type="checkbox" class="form-check-input add-student-cb flex-shrink-0"
                        value="${escHtml(s.username)}" onchange="updateAddStudentCount()">
                    <div class="flex-grow-1 min-w-0">
                        <div class="fw-semibold small text-truncate">${escHtml(s.full_name || s.username)}</div>
                        <div class="text-muted" style="font-size:0.75rem">${escHtml(s.username)}
                            ${s.grupo ? `<span class="badge bg-secondary ms-1">Grupo ${escHtml(s.grupo)}</span>` : '<span class="text-muted ms-1">Sin grupo</span>'}
                            ${s.carrera ? `<span class="text-muted ms-1">· ${escHtml(s.carrera)}</span>` : ''}
                        </div>
                    </div>
                </label>`).join('');
            updateAddStudentCount();
        }

        function filterAddStudentList() {
            const checked = new Set([...document.querySelectorAll('.add-student-cb:checked')].map(c => c.value));
            const q = document.getElementById('addStudentSearchInput').value.toLowerCase();
            const filtered = addStudentCandidates.filter(s =>
                (s.username || '').toLowerCase().includes(q) ||
                (s.full_name || '').toLowerCase().includes(q) ||
                (s.carrera || '').toLowerCase().includes(q)
            );
            renderAddStudentList(filtered);
            document.querySelectorAll('.add-student-cb').forEach(c => { if (checked.has(c.value)) c.checked = true; });
            updateAddStudentCount();
        }

        function toggleAddStudentSelectAll(cb) {
            document.querySelectorAll('.add-student-cb').forEach(c => { c.checked = cb.checked; });
            updateAddStudentCount();
        }

        function updateAddStudentCount() {
            const n = document.querySelectorAll('.add-student-cb:checked').length;
            document.getElementById('addStudentSelectedCount').textContent = `${n} seleccionado${n !== 1 ? 's' : ''}`;
        }

        async function doAddStudentToGroup() {
            const grupo = document.getElementById('addStudentToGrupo').value;
            const carrera = document.getElementById('addStudentToCarrera').value;
            const usernames = [...document.querySelectorAll('.add-student-cb:checked')].map(c => c.value);
            if (!usernames.length) { showToast('Selecciona al menos un alumno', 'warning'); return; }

            let ok = 0, fail = 0;
            for (const username of usernames) {
                try {
                    const res = await fetch('/admin/student-enrollments/move-group', {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            username,
                            group_name: grupo,
                            reason: `Movimiento al grupo ${grupo}`
                        })
                    });
                    res.ok ? ok++ : fail++;
                } catch { fail++; }
            }

            bootstrap.Modal.getOrCreateInstance(document.getElementById('groupAddStudentModal')).hide();
            showToast(`${ok} alumno${ok !== 1 ? 's' : ''} agregado${ok !== 1 ? 's' : ''} al grupo ${grupo}${fail ? ` (${fail} fallaron)` : ''}`, fail ? 'warning' : 'success');
            await reloadStudents();
            await loadGroups();
            selectGroup(currentGroupGrupo, currentGroupCarrera);
        }

        async function removeStudentFromGroup(username, grupo, carrera) {
            if (!confirm(`¿Quitar a ${username} del grupo ${grupo}?`)) return;
            try {
                const res = await fetch('/admin/student-enrollments/move-group', {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username,
                        group_name: null,
                        reason: `Salida del grupo ${grupo}`
                    })
                });
                if (!res.ok) { showToast('Error al quitar alumno', 'danger'); return; }
                showToast(`${username} quitado del grupo`, 'success');
                await reloadStudents();
                await loadGroups();
                // If group still has students, show it; otherwise clear detail
                const stillExists = allStudents.some(s => s.grupo === grupo && (s.carrera || 'Sin carrera') === carrera);
                if (stillExists) selectGroup(grupo, carrera);
                else document.getElementById('groupDetailPanel').innerHTML = '<div class="dashboard-card text-center py-5 text-muted"><i class="bi bi-people fs-1 d-block mb-3 opacity-25"></i><p class="mb-0">El grupo quedo vacio. Selecciona otro grupo.</p></div>';
            } catch(e) {
                showToast('Error al quitar alumno', 'danger');
            }
        }

        function switchView(targetId) {
            // Ocultar todas las secciones
            document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
            
            // Mostrar la seccion seleccionada
            document.getElementById(targetId).classList.add('active');

            // Actualizar el menu lateral
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            const activeLink = document.querySelector(`.nav-link[data-target="${targetId}"]`);
            if (activeLink) activeLink.classList.add('active');
            const title = document.querySelector('.top-navbar h4');
            if (title && activeLink) {
                title.textContent = activeLink.textContent.trim();
            }

            // Cerrar menu en moviles
            if (window.innerWidth < 992) {
                document.getElementById('sidebar').classList.remove('show');
                document.getElementById('sidebarOverlay').classList.remove('show');
            }
        }

        // Configurar los enlaces del menu
        document.addEventListener('DOMContentLoaded', () => {
            fixMojibakeInDom();
            const observer = new MutationObserver(() => fixMojibakeInDom());
            observer.observe(document.body, { childList: true, subtree: true });

            loadAdminData();
            loadSchoolCycle();
            loadAssignments();
            loadCyclesPaymentTable();
            loadAdminNotifications(false);

            ['settingStartDate','settingEndDate'].forEach(id => {
                document.getElementById(id)?.addEventListener('change', updateCyclePreview);
            });

            document.getElementById('newMajor')?.addEventListener('change', () => {
                syncTrackSelectWithCareer('newMajor', 'newCursando');
            });
            document.getElementById('editMajor')?.addEventListener('change', () => {
                syncTrackSelectWithCareer('editMajor', 'editCursando');
            });

            const links = document.querySelectorAll('.nav-link[data-target]');
            links.forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const targetId = link.getAttribute('data-target');
                    switchView(targetId);
                    fixMojibakeInDom();
                    if (targetId === 'view-moodle-admin') loadMoodleAdminView();
                    if (targetId === 'view-soporte-admin') loadAdminSupportTickets();
                    if (targetId === 'view-tramites') reloadServices();
                    if (targetId === 'view-finanzas') loadCyclesPaymentTable();
                    if (targetId === 'view-finanzas') loadTreasuryView();
                    if (targetId === 'view-grupos') loadGroups();
                    if (targetId === 'view-ciclos') loadCiclosView();
                    if (targetId === 'view-control-escolar') loadControlSchoolData();
                    if (targetId === 'view-calificaciones') loadGradeCenter();
                    if (targetId === 'view-asignaciones') loadAssignments();
                    if (targetId === 'view-web-admin') loadWebManagementView();
                    if (targetId === 'view-reportes') {
                        loadReportFilterOptions();
                        loadReportsDashboard();
                    }
                });
            });
        });

        function logout() {
            localStorage.removeItem('token');
            window.location.href = 'login.html';
        }

        /* Alumnos: eliminar */
        function confirmDeleteStudent(username, fullName) {
            document.getElementById('deleteStudentUsername').value = username;
            document.getElementById('deleteStudentUsernameLabel').textContent = username;
            document.getElementById('deleteStudentNameLabel').textContent = fullName;
            bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteStudentModal')).show();
        }

        async function doDeleteStudent() {
            const username = document.getElementById('deleteStudentUsername').value;
            try {
                const res = await fetch(`/admin/students/${encodeURIComponent(username)}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok && res.status !== 204) {
                    const err = await res.json().catch(() => ({}));
                    showToast(err.detail || 'Error al eliminar alumno', 'danger');
                    return;
                }
                bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteStudentModal')).hide();
                showToast(`Alumno "${username}" eliminado correctamente`, 'success');
                await reloadStudents();
            } catch {
                showToast('Error de conexión', 'danger');
            }
        }

