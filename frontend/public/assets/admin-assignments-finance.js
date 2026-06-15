        let allAssignments = [];

        function populateAssignmentSelects() {
            // Career filter dropdown
            const careers = [...new Set(allSubjects.map(s => s.career).filter(Boolean))].sort();
            const careerFilterEl = document.getElementById('assignCareerFilter');
            if (careerFilterEl) {
                careerFilterEl.innerHTML = '<option value="">Todas las carreras</option>' +
                    careers.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
            }

            // Subject select (all)
            const subjectOpts = '<option value="">Seleccionar materia...</option>' +
                allSubjects.map(s => `<option value="${s.id}" data-career="${escHtml(s.career)}">${escHtml(s.name)} (Sem ${escHtml(s.semester)})</option>`).join('');
            document.getElementById('assignmentSubjectId').innerHTML = subjectOpts;

            // Teacher select
            const teacherOpts = '<option value="">Seleccionar docente...</option>' +
                allTeachers.map(t => `<option value="${escHtml(t.username)}">${escHtml(t.full_name)}</option>`).join('');
            document.getElementById('assignmentTeacherUsername').innerHTML = teacherOpts;

            // Group select
            const groupOpts = '<option value="">Seleccionar grupo...</option>' +
                allGroupSummaries.map(g => `<option value="${g.group_id}">${escHtml(g.grupo)} — ${escHtml(g.carrera)} (${g.total || 0} alumnos)</option>`).join('');
            document.getElementById('assignmentGroupId').innerHTML = groupOpts;

            // Reset preview
            document.getElementById('assignPreviewCard')?.classList.add('d-none');
        }

        function filterCreateAssignmentSubjects() {
            const career = document.getElementById('assignCareerFilter')?.value || '';
            const subjectSel = document.getElementById('assignmentSubjectId');
            const prevVal = subjectSel.value;
            if (!career) {
                const opts = '<option value="">Seleccionar materia...</option>' +
                    allSubjects.map(s => `<option value="${s.id}" data-career="${escHtml(s.career)}">${escHtml(s.name)} (Sem ${escHtml(s.semester)})</option>`).join('');
                subjectSel.innerHTML = opts;
            } else {
                const filtered = allSubjects.filter(s => s.career === career);
                const opts = `<option value="">Seleccionar materia (${filtered.length})...</option>` +
                    filtered.map(s => `<option value="${s.id}" data-career="${escHtml(s.career)}">${escHtml(s.name)} — Sem ${escHtml(s.semester)}</option>`).join('');
                subjectSel.innerHTML = opts;
            }
            // Restore value if still valid
            if (prevVal && subjectSel.querySelector(`option[value="${prevVal}"]`)) {
                subjectSel.value = prevVal;
            }
            updateAssignPreview();
        }

        function updateAssignPreview() {
            const subjectSel = document.getElementById('assignmentSubjectId');
            const teacherSel = document.getElementById('assignmentTeacherUsername');
            const groupSel = document.getElementById('assignmentGroupId');
            const card = document.getElementById('assignPreviewCard');
            if (!card) return;

            const subjectText = subjectSel.options[subjectSel.selectedIndex]?.text;
            const teacherText = teacherSel.options[teacherSel.selectedIndex]?.text;
            const groupText = groupSel.options[groupSel.selectedIndex]?.text;

            const hasSubject = subjectSel.value;
            const hasTeacher = teacherSel.value;
            const hasGroup = groupSel.value;

            if (hasSubject || hasTeacher || hasGroup) {
                card.classList.remove('d-none');
                document.getElementById('previewSubject').textContent = hasSubject ? subjectText : '—';
                document.getElementById('previewTeacher').textContent = hasTeacher ? teacherText : '—';
                document.getElementById('previewGroup').textContent = hasGroup ? groupText : '—';
            } else {
                card.classList.add('d-none');
            }
        }

        function _assignmentCyclePeriod(cycleId) {
            if (!cycleId) return '—';
            const c = allCycles.find(c => c.id === cycleId);
            return c ? escHtml(c.period) : `Ciclo ${cycleId}`;
        }

        async function loadAssignments() {
            try {
                const response = await fetch('/admin/subject-assignments', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) return;
                allAssignments = await response.json();
                filteredAssignments = [...allAssignments];

                // Stats
                const uniqueTeachers = new Set(allAssignments.map(a => a.teacher_id).filter(Boolean));
                const uniqueSubjects = new Set(allAssignments.map(a => a.subject_id).filter(Boolean));
                const totalStudents = allAssignments.reduce((sum, a) => sum + (a.student_count || 0), 0);
                document.getElementById('assignStatTotal').textContent = allAssignments.length;
                document.getElementById('assignStatTeachers').textContent = uniqueTeachers.size;
                document.getElementById('assignStatSubjects').textContent = uniqueSubjects.size;
                document.getElementById('assignStatStudents').textContent = totalStudents;

                // Populate filter dropdowns
                const careers = [...new Set(allAssignments.map(a => a.subject?.career).filter(Boolean))].sort();
                const careerSel = document.getElementById('filterAssignCareer');
                const prevCareer = careerSel.value;
                careerSel.innerHTML = '<option value="">Todas las carreras</option>' +
                    careers.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
                careerSel.value = prevCareer;

                const teachers = [...new Map(allAssignments
                    .filter(a => a.teacher)
                    .map(a => [a.teacher.username, a.teacher.full_name]))].sort((a,b) => a[1].localeCompare(b[1]));
                const teacherSel = document.getElementById('filterAssignTeacher');
                const prevTeacher = teacherSel.value;
                teacherSel.innerHTML = '<option value="">Todos los docentes</option>' +
                    teachers.map(([u, n]) => `<option value="${escHtml(u)}">${escHtml(n)}</option>`).join('');
                teacherSel.value = prevTeacher;

                renderAssignments(allAssignments);
                updateOfferSummary();
                populateGradeAssignmentSelector();
            } catch (e) { /* silencioso */ }
        }

        function filterAssignments() {
            const q = (document.getElementById('filterAssignSearch')?.value || '').toLowerCase().trim();
            const career = document.getElementById('filterAssignCareer')?.value || '';
            const teacher = document.getElementById('filterAssignTeacher')?.value || '';
            filteredAssignments = allAssignments.filter(a => {
                const subj = a.subject || {};
                const tch = a.teacher || {};
                if (career && subj.career !== career) return false;
                if (teacher && tch.username !== teacher) return false;
                if (q) {
                    const haystack = `${subj.name || ''} ${tch.full_name || ''} ${a.group_name || ''}`.toLowerCase();
                    if (!haystack.includes(q)) return false;
                }
                return true;
            });
            assignmentsPage = 1;
            renderAssignments(filteredAssignments);
        }

        function clearAssignmentFilters() {
            document.getElementById('filterAssignSearch').value = '';
            document.getElementById('filterAssignCareer').value = '';
            document.getElementById('filterAssignTeacher').value = '';
            filteredAssignments = [...allAssignments];
            assignmentsPage = 1;
            renderAssignments(filteredAssignments);
        }

        function renderAssignments(assignments) {
            const tbody = document.getElementById('allAssignmentsTableBody');
            if (!assignments.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay asignaciones para el ciclo activo.</td></tr>';
                buildTablePagination('assignments-pagination', 'assignments-info', 1, 0, TABLE_PER_PAGE, 'changeAssignmentsPage');
                return;
            }
            const start = (assignmentsPage - 1) * TABLE_PER_PAGE;
            const page  = assignments.slice(start, start + TABLE_PER_PAGE);
            tbody.innerHTML = page.map(a => {
                const subj = a.subject || {};
                const tch = a.teacher || {};
                const groupLabel = a.group_name ? `<span class="badge bg-secondary">${escHtml(a.group_name)}</span>` : '<span class="text-muted">—</span>';
                const teacherLabel = tch.full_name
                    ? `${escHtml(tch.full_name)}<div class="text-muted" style="font-size:.75rem">${escHtml(tch.username || '')}</div>`
                    : '<span class="text-muted">Sin docente</span>';
                const cyclePeriod = _assignmentCyclePeriod(a.cycle_id);
                return `<tr>
                    <td>
                        <div class="fw-semibold">${escHtml(subj.name || '?')}</div>
                        <div class="d-flex gap-1 mt-1 flex-wrap">
                            <span class="badge bg-primary bg-opacity-10 text-primary" style="font-size:.7rem">${escHtml(subj.career || '?')}</span>
                            <span class="badge bg-light text-muted border" style="font-size:.7rem">Sem ${escHtml(subj.semester || '?')}</span>
                        </div>
                    </td>
                    <td>${teacherLabel}</td>
                    <td>${groupLabel}</td>
                    <td><span class="badge bg-success bg-opacity-10 text-success">${a.student_count || 0} alumnos</span></td>
                    <td><span class="text-muted small">${cyclePeriod}</span></td>
                    <td>
                        <div class="d-flex gap-1">
                            <button class="btn btn-sm btn-outline-primary rounded-3" title="Editar" onclick="openEditAssignment(${a.id})">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger rounded-3" title="Eliminar" onclick="confirmDeleteAssignment(${a.id}, '${escHtml(subj.name || '?')} — ${escHtml(tch.full_name || 'Sin docente')}')">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>`;
            }).join('');
            buildTablePagination('assignments-pagination', 'assignments-info', assignmentsPage, assignments.length, TABLE_PER_PAGE, 'changeAssignmentsPage');
        }

        function openCreateAssignmentModal() {
            if (allGroupSummaries.length === 0) {
                loadGroups().then(populateAssignmentSelects);
            } else {
                populateAssignmentSelects();
            }
            document.getElementById('createAssignmentForm').reset();
            new bootstrap.Modal(document.getElementById('createAssignmentModal')).show();
        }

        async function createAssignment(event) {
            event.preventDefault();
            const groupIdVal = document.getElementById('assignmentGroupId').value;
            if (!groupIdVal) { showToast('Debes seleccionar un grupo', 'danger'); return; }
            const data = {
                subject_id: parseInt(document.getElementById('assignmentSubjectId').value),
                teacher_username: document.getElementById('assignmentTeacherUsername').value,
                group_id: parseInt(groupIdVal),
            };
            try {
                const res = await fetch('/admin/subject-assignments', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    const result = await res.json();
                    const linked = result._auto_linked ? result.auto_linked : null;
                    const msg = linked !== null && linked > 0
                        ? `Asignacion creada y ${linked} alumno(s) vinculados automaticamente`
                        : 'Asignacion creada exitosamente';
                    showToast(msg, 'success');
                    bootstrap.Modal.getInstance(document.getElementById('createAssignmentModal')).hide();
                    document.getElementById('createAssignmentForm').reset();
                    loadAssignments();
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Error al crear asignacion', 'danger');
                }
            } catch (e) { showToast('Error de conexion', 'danger'); }
        }

        function openEditAssignment(id) {
            const a = allAssignments.find(x => x.id === id);
            if (!a) return;
            document.getElementById('editAssignmentId').value = id;
            const subj = a.subject || {};
            document.getElementById('editAssignmentSubjectLabel').innerHTML =
                `Materia: <strong>${escHtml(subj.name || '?')}</strong> — ${escHtml(subj.career || '')} Sem ${escHtml(subj.semester || '')}`;

            const teacherOpts = '<option value="">Sin cambiar...</option>' +
                allTeachers.map(t => `<option value="${escHtml(t.username)}" ${a.teacher?.username === t.username ? 'selected' : ''}>${escHtml(t.full_name)} (${escHtml(t.username)})</option>`).join('');
            document.getElementById('editAssignmentTeacher').innerHTML = teacherOpts;

            const groupOpts = '<option value="">Sin cambiar...</option>' +
                allGroupSummaries.map(g => `<option value="${g.group_id}" ${a.group_id === g.group_id ? 'selected' : ''}>${escHtml(g.grupo)} — ${escHtml(g.carrera)}</option>`).join('');
            document.getElementById('editAssignmentGroup').innerHTML = groupOpts;

            new bootstrap.Modal(document.getElementById('editAssignmentModal')).show();
        }

        async function saveEditAssignment() {
            const id = document.getElementById('editAssignmentId').value;
            const teacherVal = document.getElementById('editAssignmentTeacher').value;
            const groupVal = document.getElementById('editAssignmentGroup').value;
            if (!teacherVal && !groupVal) { showToast('Selecciona al menos un cambio', 'warning'); return; }
            const data = {};
            if (teacherVal) data.teacher_username = teacherVal;
            if (groupVal) data.group_id = parseInt(groupVal);
            try {
                const res = await fetch(`/admin/subject-assignments/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    showToast('Asignacion actualizada', 'success');
                    bootstrap.Modal.getInstance(document.getElementById('editAssignmentModal')).hide();
                    loadAssignments();
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Error al actualizar', 'danger');
                }
            } catch (e) { showToast('Error de conexion', 'danger'); }
        }

        function confirmDeleteAssignment(id, label) {
            document.getElementById('deleteAssignmentId').value = id;
            document.getElementById('deleteAssignLabel').textContent = label;
            new bootstrap.Modal(document.getElementById('deleteAssignmentModal')).show();
        }

        async function doDeleteAssignment() {
            const id = document.getElementById('deleteAssignmentId').value;
            try {
                const res = await fetch(`/admin/subject-assignments/${id}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok || res.status === 204) {
                    showToast('Asignacion eliminada', 'success');
                    bootstrap.Modal.getInstance(document.getElementById('deleteAssignmentModal')).hide();
                    loadAssignments();
                } else {
                    showToast('Error al eliminar asignacion', 'danger');
                }
            } catch (e) { showToast('Error de conexion', 'danger'); }
        }

        document.getElementById('createAssignmentModal').addEventListener('show.bs.modal', populateAssignmentSelects);

        document.getElementById('registerStudentModal').addEventListener('show.bs.modal', () => {
            const sel = document.getElementById('newGroup');
            if (sel) {
                sel.innerHTML = '<option value="">Sin grupo</option>' +
                    allGroupSummaries.map(g => `<option value="${escHtml(g.grupo)}">${escHtml(g.grupo)} — ${escHtml(g.carrera)}</option>`).join('');
            }
        });

        function openAssignSubjectForTeacher(teacherUsername) {
            populateAssignmentSelects();
            document.getElementById('assignmentTeacherUsername').value = teacherUsername;
            new bootstrap.Modal(document.getElementById('createAssignmentModal')).show();
        }

        async function createSubject(event) {
            event.preventDefault();

            const teacherUsername = document.getElementById('newSubjectTeacher').value;
            const subjectData = {
                name: document.getElementById('newSubjectName').value,
                career: document.getElementById('newSubjectCareer').value,
                semester: document.getElementById('newSubjectSemester').value,
                credits: parseInt(document.getElementById('newSubjectCredits').value) || 0,
                ...(teacherUsername && { teacher_username: teacherUsername })
            };

            try {
                const response = await fetch('/admin/subjects', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(subjectData)
                });

                if (response.ok) {
                    showToast('Materia creada exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createSubjectModal'));
                    modal.hide();
                    document.getElementById('createSubjectForm').reset();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al crear materia', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        function openEditSubject(id) {
            const subject = allSubjects.find(s => s.id === id);
            if (subject) {
                document.getElementById('editSubjectId').value = subject.id;
                document.getElementById('editSubjectName').value = subject.name;
                document.getElementById('editSubjectCareer').value = subject.career;
                document.getElementById('editSubjectSemester').value = subject.semester;
                document.getElementById('editSubjectCredits').value = subject.credits;
                const modal = new bootstrap.Modal(document.getElementById('editSubjectModal'));
                modal.show();
            }
        }

        async function updateSubject(event) {
            event.preventDefault();
            const id = document.getElementById('editSubjectId').value;
            
            const updateData = {
                name: document.getElementById('editSubjectName').value,
                career: document.getElementById('editSubjectCareer').value,
                semester: document.getElementById('editSubjectSemester').value,
                credits: parseInt(document.getElementById('editSubjectCredits').value) || 0
            };

            try {
                const response = await fetch(`/admin/subjects/${id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    showToast('Materia actualizada exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editSubjectModal'));
                    modal.hide();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al actualizar materia', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        async function createPayment(event) {
            event.preventDefault();
            
            const paymentData = {
                student_username: document.getElementById('newPaymentStudent').value,
                charge_type: 'Otro',
                concept: document.getElementById('newPaymentConcept').value,
                period_label: document.getElementById('newPaymentConcept').value,
                amount: parseFloat(document.getElementById('newPaymentAmount').value),
                discount_amount: parseFloat(document.getElementById('newPaymentDiscount').value) || 0.0,
                due_date: new Date(document.getElementById('newPaymentDueDate').value).toISOString(),
                status: document.getElementById('newPaymentStatus').value,
                payment_date: document.getElementById('newPaymentDate').value ? new Date(document.getElementById('newPaymentDate').value).toISOString() : null,
                payment_method: document.getElementById('newPaymentMethod').value || null,
                reference: document.getElementById('newPaymentReference').value || null
            };

            try {
                const response = await fetch('/admin/charges', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(paymentData)
                });

                if (response.ok) {
                    showToast('Cargo registrado exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createPaymentModal'));
                    modal.hide();
                    document.getElementById('createPaymentForm').reset();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al registrar cargo', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        function openEditGlobalPayment(id) {
            const payment = allCharges.find(p => p.id === id);
            if (payment) {
                document.getElementById('editGlobalPaymentId').value = payment.id;
                document.getElementById('editGlobalPaymentConcept').value = payment.concept;
                document.getElementById('editGlobalPaymentAmount').value = payment.amount;
                document.getElementById('editGlobalPaymentDiscount').value = payment.discount_amount || 0;
                
                // Formatear fecha para el input type="date"
                const date = new Date(payment.due_date);
                const formattedDate = date.toISOString().split('T')[0];
                document.getElementById('editGlobalPaymentDueDate').value = formattedDate;
                
                document.getElementById('editGlobalPaymentStatus').value = payment.status;

                if (payment.payment_date) {
                    document.getElementById('editGlobalPaymentDate').value = new Date(payment.payment_date).toISOString().split('T')[0];
                } else {
                    document.getElementById('editGlobalPaymentDate').value = '';
                }
                
                document.getElementById('editGlobalPaymentMethod').value = payment.payment_method || '';
                document.getElementById('editGlobalPaymentReference').value = payment.reference || '';
                
                const modal = new bootstrap.Modal(document.getElementById('editGlobalPaymentModal'));
                modal.show();
            }
        }

        async function deleteGlobalPayment(id) {
            const payment = allCharges.find(p => p.id === id);
            const label = payment ? `${payment.concept || 'pago'} de ${payment.student?.username || 'alumno'}` : `pago #${id}`;
            if (!confirm(`Eliminar ${label}? Esta accion no se puede deshacer.`)) return;

            try {
                const response = await fetch(`/admin/charges/${id}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    showToast('Pago eliminado correctamente', 'success');
                    await loadAdminData();
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al eliminar pago', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        async function updateGlobalPayment(event) {
            event.preventDefault();
            const id = document.getElementById('editGlobalPaymentId').value;
            
            const updateData = {
                concept: document.getElementById('editGlobalPaymentConcept').value,
                period_label: document.getElementById('editGlobalPaymentConcept').value,
                amount: parseFloat(document.getElementById('editGlobalPaymentAmount').value),
                discount_amount: parseFloat(document.getElementById('editGlobalPaymentDiscount').value) || 0.0,
                due_date: new Date(document.getElementById('editGlobalPaymentDueDate').value).toISOString(),
                status: document.getElementById('editGlobalPaymentStatus').value,
                payment_date: document.getElementById('editGlobalPaymentDate').value ? new Date(document.getElementById('editGlobalPaymentDate').value).toISOString() : null,
                payment_method: document.getElementById('editGlobalPaymentMethod').value || null,
                reference: document.getElementById('editGlobalPaymentReference').value || null
            };

            try {
                const response = await fetch(`/admin/charges/${id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    showToast('Cargo actualizado exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editGlobalPaymentModal'));
                    modal.hide();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al actualizar cargo', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        async function createService(event) {
            event.preventDefault();
            const requestDate = document.getElementById('newServiceDate').value;
            
            const serviceData = {
                student_username: document.getElementById('newServiceStudent').value.trim(),
                type: document.getElementById('newServiceType').value,
                request_date: new Date(`${requestDate}T12:00:00`).toISOString(),
                status: document.getElementById('newServiceStatus').value
            };

            try {
                const response = await fetch('/admin/services', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(serviceData)
                });

                if (response.ok) {
                    showToast('Tramite registrado exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createServiceModal'));
                    modal.hide();
                    document.getElementById('createServiceForm').reset();
                    document.getElementById('selectedServiceStudent').textContent = '';
                    setTodayDateInputValue('newServiceDate');
                    renderServiceStudentPicker(allStudents);
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al registrar tramite', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        document.getElementById('createServiceModal')?.addEventListener('show.bs.modal', () => {
            setTodayDateInputValue('newServiceDate');
            document.getElementById('newServiceStudent').value = '';
            document.getElementById('selectedServiceStudent').textContent = '';
            renderServiceStudentPicker(allStudents);
        });

        function openEditGlobalService(id) {
            const service = allServices.find(s => s.id === id);
            if (service) {
                document.getElementById('editGlobalServiceId').value = service.id;
                document.getElementById('editGlobalServiceType').value = service.type;
                
                // Formatear fecha para el input type="date"
                const date = new Date(service.request_date);
                const formattedDate = date.toISOString().split('T')[0];
                document.getElementById('editGlobalServiceDate').value = formattedDate;
                
                document.getElementById('editGlobalServiceStatus').value = service.status;
                
                const modal = new bootstrap.Modal(document.getElementById('editGlobalServiceModal'));
                modal.show();
            }
        }

        async function updateGlobalService(event) {
            event.preventDefault();
            const id = document.getElementById('editGlobalServiceId').value;
            
            const updateData = {
                type: document.getElementById('editGlobalServiceType').value,
                request_date: new Date(document.getElementById('editGlobalServiceDate').value).toISOString(),
                status: document.getElementById('editGlobalServiceStatus').value
            };

            try {
                const response = await fetch(`/admin/services/${id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    showToast('Tramite actualizado exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editGlobalServiceModal'));
                    modal.hide();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al actualizar tramite', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        function openViewTeacher(username) {
            const teacher = allTeachers.find(t => t.username === username);
            if (!teacher) return;

            document.getElementById('viewTeacherInitials').textContent = getInitials(teacher.full_name);
            document.getElementById('viewTeacherName').textContent = teacher.full_name || 'Sin nombre';
            const teacherMoodleTag = teacher.moodle_id ? `  Moodle ID ${teacher.moodle_id}` : '  Sin vinculo Moodle';
            document.getElementById('viewTeacherUsernameDisplay').textContent = `Matricula: ${teacher.username}${teacherMoodleTag}`;
            document.getElementById('viewTeacherEmailDisplay').textContent = teacher.email || 'Sin correo';

            // Materias asignadas: filtrar de allAssignments
            const tbody = document.getElementById('teacherSubjectsTableBody');
            const assigned = (allAssignments || []).filter(a =>
                (a.teacher_username === username) ||
                (a.teacher && a.teacher.username === username)
            );
            if (!assigned.length) {
                tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-3">Sin materias asignadas actualmente.</td></tr>';
            } else {
                tbody.innerHTML = assigned.map(a => {
                    const subject = a.subject || {};
                    const cnt = a.student_count ?? a.students_count ?? '?';
                    return `<tr>
                        <td class="fw-semibold">${escHtml(subject.name || 'Sin nombre')}</td>
                        <td><span class="badge bg-light text-dark border">${escHtml(subject.semester || '?')}</span></td>
                        <td><span class="badge bg-primary rounded-pill">${cnt}</span></td>
                    </tr>`;
                }).join('');
            }

            new bootstrap.Modal(document.getElementById('viewTeacherModal')).show();
        }

        function openEditStudent(username) {
            const student = allStudents.find(s => s.username === username);
            if (!student) return;

            document.getElementById('editUsername').value = student.username;
            document.getElementById('editFullName').value = student.full_name || '';
            document.getElementById('editCurp').value = student.curp || '';
            document.getElementById('editSegUniqueKey').value = student.seg_unique_key || '';
            document.getElementById('editEmail').value = student.email || '';
            document.getElementById('editPassword').value = '';
            const majorSelect = document.getElementById('editMajor');
            if (student.career_id) {
                majorSelect.value = String(student.career_id);
            } else if (student.carrera) {
                const opt = Array.from(majorSelect.options).find(o => o.text.trim() === student.carrera.trim());
                majorSelect.value = opt ? opt.value : '';
            } else {
                majorSelect.value = '';
            }

            const modalidadSelect = document.getElementById('editModalidad');
            if (student.modality_id) {
                modalidadSelect.value = String(student.modality_id);
            } else if (student.modalidad) {
                const opt = Array.from(modalidadSelect.options).find(o => o.text.trim() === student.modalidad.trim());
                modalidadSelect.value = opt ? opt.value : '';
            } else {
                modalidadSelect.value = '';
            }
            document.getElementById('editSemester').value = student.semestre || '';

            // Poblar dropdown de grupos
            const editGroupSel = document.getElementById('editGroup');
            editGroupSel.innerHTML = '<option value="">Sin grupo</option>' +
                allGroupSummaries.map(g => `<option value="${escHtml(g.grupo)}">${escHtml(g.grupo)} — ${escHtml(g.carrera)}</option>`).join('');
            editGroupSel.value = student.grupo || '';

            document.getElementById('editCursando').value = student.cursando || '';
            if (!document.getElementById('editCursando').value) {
                syncTrackSelectWithCareer('editMajor', 'editCursando');
            }
            document.getElementById('editUserStatus').value = student.user_status || 'Activo';
            document.getElementById('editEnrollmentStatus').value = student.enrollment_status || 'No Inscrito';

            const editModal = new bootstrap.Modal(document.getElementById('editStudentModal'));
            editModal.show();
        }

        async function updateStudent() {
            const form = document.getElementById('editStudentForm');
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }

            const errorDiv = document.getElementById('editError');
            errorDiv.style.display = 'none';

            const username = document.getElementById('editUsername').value;
            const careerSelection = getCatalogSelection('editMajor');
            const modalitySelection = getCatalogSelection('editModalidad');
            const payload = {
                full_name: document.getElementById('editFullName').value,
                curp: document.getElementById('editCurp').value.trim().toUpperCase(),
                seg_unique_key: document.getElementById('editSegUniqueKey').value.trim(),
                email: document.getElementById('editEmail').value,
                career_id: careerSelection.id,
                carrera: careerSelection.name,
                modality_id: modalitySelection.id,
                modalidad: modalitySelection.name,
                semestre: document.getElementById('editSemester').value,
                grupo: document.getElementById('editGroup').value,
                cursando: document.getElementById('editCursando').value,
                user_status: document.getElementById('editUserStatus').value,
                enrollment_status: document.getElementById('editEnrollmentStatus').value
            };

            const password = document.getElementById('editPassword').value;
            if (password) {
                payload.password = password;
            }

            try {
                const response = await fetch(`/admin/students/${username}`, {
                    method: 'PUT',
                    headers: { 
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    showToast('Alumno actualizado exitosamente');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editStudentModal'));
                    modal.hide();
                    loadAdminData();
                } else {
                    const data = await response.json();
                    errorDiv.textContent = data.detail || 'Error al actualizar alumno';
                    errorDiv.style.display = 'block';
                }
            } catch (error) {
                errorDiv.textContent = 'Error de conexion';
                errorDiv.style.display = 'block';
            }
        }

        function showToast(msg, isError = false) {
            const toastEl = document.getElementById('adminToast');
            document.getElementById('adminToastMessage').textContent = msg;
            
            if (isError) {
                toastEl.classList.remove('bg-success');
                toastEl.classList.add('bg-danger');
            } else {
                toastEl.classList.remove('bg-danger');
                toastEl.classList.add('bg-success');
            }
            
            const toast = new bootstrap.Toast(toastEl);
            toast.show();
        }

        async function extractApiErrorMessage(response, fallbackMessage) {
            try {
                const data = await response.json();
                if (typeof data.detail === 'string') return data.detail;
                if (Array.isArray(data.detail)) return data.detail.map(item => item.msg || item.message || JSON.stringify(item)).join(', ');
                if (typeof data.message === 'string') return data.message;
            } catch (error) {
                console.warn('No se pudo leer el error del API', error);
            }
            return fallbackMessage;
        }
