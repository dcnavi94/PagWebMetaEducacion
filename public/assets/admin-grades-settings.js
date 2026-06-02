        let currentGradeAssignmentId = null;

        function populateGradeAssignmentSelector() {
            renderGradeAssignmentList();
        }

        function renderGradeAssignmentList() {
            const list = document.getElementById('gradeAssignmentList');
            if (!list) return;

            // Populate career filter
            const careerFilter = document.getElementById('gradeCareerFilter');
            if (careerFilter) {
                const careers = [...new Set(allAssignments.map(a => a.subject?.career || 'Sin carrera').filter(Boolean))].sort();
                careerFilter.innerHTML = '<option value="">Todas las carreras</option>' +
                    careers.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
            }

            filterGradeAssignments();
        }

        function filterGradeAssignments() {
            const list = document.getElementById('gradeAssignmentList');
            if (!list) return;
            const search  = (document.getElementById('gradeAssignmentSearch')?.value || '').toLowerCase();
            const career  = document.getElementById('gradeCareerFilter')?.value || '';

            const filtered = allAssignments.filter(a => {
                const subject  = (a.subject?.name || '').toLowerCase();
                const teacher  = (a.teacher?.full_name || a.teacher?.username || '').toLowerCase();
                const aCareer  = a.subject?.career || 'Sin carrera';
                const matchSearch = !search || subject.includes(search) || teacher.includes(search);
                const matchCareer = !career || aCareer === career;
                return matchSearch && matchCareer;
            });

            if (!filtered.length) {
                list.innerHTML = '<p class="text-muted small p-3">No hay asignaciones que coincidan.</p>';
                return;
            }

            list.innerHTML = filtered.map(a => {
                const outcome = (gradeOutcomeRows || []).find(o => String(o.assignment_id) === String(a.id));
                const total    = outcome ? (outcome.approved_count + outcome.failed_count + outcome.in_progress_count) : 0;
                const graded   = outcome ? (outcome.approved_count + outcome.failed_count) : 0;
                const pct      = total > 0 ? Math.round(graded / total * 100) : 0;
                const isActive = currentGradeAssignmentId === a.id;
                return `
                <button class="btn btn-outline-secondary btn-sm w-100 text-start mb-1 rounded-3 grade-assignment-btn px-3 py-2 ${isActive ? 'active btn-primary text-white border-primary' : ''}"
                    data-id="${a.id}" onclick="selectGradeAssignment(${a.id})">
                    <div class="fw-bold small text-truncate">${escHtml(a.subject?.name || 'Materia')}</div>
                    <div class="text-muted small text-truncate" style="font-size:.75rem">${escHtml(a.teacher?.full_name || a.teacher?.username || 'Sin docente')}</div>
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <span class="badge bg-light text-dark border" style="font-size:.7rem">${escHtml(a.subject?.career || 'Sin carrera')}</span>
                        <span class="text-muted" style="font-size:.7rem">${graded}/${total} · ${pct}%</span>
                    </div>
                    ${total > 0 ? `<div class="progress mt-1" style="height:3px"><div class="progress-bar ${pct === 100 ? 'bg-success' : 'bg-primary'}" style="width:${pct}%"></div></div>` : ''}
                </button>`;
            }).join('');
        }

        async function selectGradeAssignment(assignmentId) {
            currentGradeAssignmentId = assignmentId;
            document.querySelectorAll('.grade-assignment-btn').forEach(b => {
                const active = Number(b.dataset.id) === assignmentId;
                b.classList.toggle('active', active);
                b.classList.toggle('btn-primary', active);
                b.classList.toggle('text-white', active);
                b.classList.toggle('border-primary', active);
            });

            const panel = document.getElementById('gradeDetailPanel');
            const assignment = allAssignments.find(a => a.id === assignmentId);
            panel.innerHTML = `<div class="dashboard-card text-center py-4 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Cargando alumnos...</div>`;

            try {
                const res = await fetch(`/teacher/students/${assignmentId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                selectedGradeRows = await res.json();
                gradeRowsPage = 1;
                renderGradeDetailPanel(assignment, selectedGradeRows);
            } catch (error) {
                panel.innerHTML = '<div class="dashboard-card text-center py-4 text-danger"><i class="bi bi-wifi-off me-2"></i>No fue posible cargar la lista.</div>';
            }
        }

        // Keep legacy function name for backward compatibility
        async function loadGradeAssignmentStudents() {
            if (currentGradeAssignmentId) await selectGradeAssignment(currentGradeAssignmentId);
        }

        function renderGradeDetailPanel(assignment, rows) {
            const panel = document.getElementById('gradeDetailPanel');
            const subject  = assignment?.subject?.name  || 'Materia';
            const teacher  = assignment?.teacher?.full_name || assignment?.teacher?.username || 'Sin docente';
            const career   = assignment?.subject?.career || 'Sin carrera';
            const group    = assignment?.group?.name || assignment?.group_name || '—';
            const cycle    = assignment?.cycle?.period || '—';

            const total  = rows.length;
            const graded = rows.filter(r => r.score != null).length;
            const pct    = total > 0 ? Math.round(graded / total * 100) : 0;
            const approved = rows.filter(r => r.status === 'Aprobada').length;
            const failed   = rows.filter(r => r.status === 'Reprobada').length;

            panel.innerHTML = `
                <div class="dashboard-card mb-3">
                    <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
                        <div>
                            <h5 class="fw-bold mb-1">${escHtml(subject)}</h5>
                            <p class="text-muted small mb-1">
                                <i class="bi bi-person-badge me-1"></i>${escHtml(teacher)}
                                &nbsp;&bull;&nbsp;
                                <i class="bi bi-mortarboard me-1"></i>${escHtml(career)}
                                &nbsp;&bull;&nbsp;
                                <i class="bi bi-people me-1"></i>Grupo ${escHtml(group)}
                                &nbsp;&bull;&nbsp;
                                <i class="bi bi-calendar3 me-1"></i>${escHtml(cycle)}
                            </p>
                            <div class="d-flex align-items-center gap-3 mt-2">
                                <div class="progress flex-grow-1" style="height:6px; min-width:140px">
                                    <div class="progress-bar ${pct===100?'bg-success':'bg-primary'}" style="width:${pct}%"></div>
                                </div>
                                <span class="small text-muted">${graded}/${total} calificados (${pct}%)</span>
                                <span class="badge bg-success-subtle text-success border">${approved} aprobados</span>
                                <span class="badge bg-danger-subtle text-danger border">${failed} reprobados</span>
                            </div>
                        </div>
                        <div class="d-flex gap-2 flex-wrap">
                            <button class="btn btn-sm btn-outline-secondary rounded-pill" onclick="exportCurrentGradesCsv()" title="Exportar lista actual">
                                <i class="bi bi-filetype-csv me-1"></i>Exportar
                            </button>
                            <button class="btn btn-sm btn-success rounded-pill px-3" onclick="saveAllGrades()">
                                <i class="bi bi-check2-all me-1"></i>Guardar Todo
                            </button>
                        </div>
                    </div>
                </div>
                <div class="dashboard-card p-0 overflow-hidden">
                    <div class="table-responsive">
                        <table class="table table-admin mb-0">
                            <thead>
                                <tr>
                                    <th>Matrícula</th>
                                    <th>Alumno</th>
                                    <th>Intento</th>
                                    <th style="width:130px">Calificación (0-10)</th>
                                    <th>Estatus</th>
                                    <th>Acción</th>
                                </tr>
                            </thead>
                            <tbody id="gradeCenterTableBody">
                                ${renderGradeRows(rows)}
                            </tbody>
                        </table>
                    </div>
                    <nav class="mt-2 px-1 d-flex justify-content-between align-items-center">
                        <small class="text-muted" id="grade-rows-info"></small>
                        <ul class="pagination pagination-sm mb-0" id="grade-rows-pagination"></ul>
                    </nav>
                </div>`;
        }

        function renderGradeRows(rows) {
            if (!rows.length) return '<tr><td colspan="6" class="text-center py-4 text-muted">No hay alumnos inscritos en esta asignación.</td></tr>';
            return rows.map((row, idx) => {
                const key      = row.grade_id || row.course_enrollment_id;
                const hasGrade = !!row.grade_id;
                const score    = row.score ?? '';
                const statusMap = { 'Aprobada':'bg-success', 'Reprobada':'bg-danger', 'Cursando':'bg-warning text-dark' };
                const badgeClass = statusMap[row.status] || 'bg-secondary';
                const scoreColor = score === '' ? '' : parseFloat(score) >= 6 ? 'text-success fw-bold' : 'text-danger fw-bold';
                return `
                <tr id="grade-row-${key}" class="${row.status === 'Reprobada' ? 'table-danger' : row.status === 'Aprobada' ? 'table-success' : ''}">
                    <td class="fw-bold text-primary small">${escHtml(row.username)}</td>
                    <td class="small">${escHtml(row.full_name || 'Sin nombre')}</td>
                    <td><span class="badge bg-light text-dark border small">${escHtml(row.attempt_type || 'Regular')}</span></td>
                    <td>
                        ${hasGrade ? `
                        <input type="number" min="0" max="10" step="0.1"
                            class="form-control form-control-sm text-center ${scoreColor}"
                            id="grade-score-${key}"
                            value="${score}"
                            oninput="onScoreInput(this, ${key})"
                            onkeydown="gradeInputKeydown(event, ${idx})"
                            data-original="${score}">` : '<span class="badge bg-secondary">Sin acta</span>'}
                    </td>
                    <td id="grade-status-badge-${key}">
                        <span class="badge ${badgeClass} rounded-pill px-2">${row.status || 'Cursando'}</span>
                    </td>
                    <td>
                        ${hasGrade ? `
                        <button class="btn btn-sm btn-outline-primary rounded-pill" id="grade-save-btn-${key}"
                            onclick="saveFinalGrade(${row.grade_id}, '${key}')">
                            <i class="bi bi-check-lg"></i>
                        </button>` : ''}
                    </td>
                </tr>`;
            }).join('');
        }

        function onScoreInput(input, key) {
            const raw = input.value === '' ? null : parseFloat(input.value);
            const status = raw === null ? 'Cursando' : raw >= 6 ? 'Aprobada' : 'Reprobada';
            const badgeEl = document.getElementById(`grade-status-badge-${key}`);
            if (badgeEl) {
                const map = { 'Aprobada':'bg-success', 'Reprobada':'bg-danger', 'Cursando':'bg-warning text-dark' };
                badgeEl.innerHTML = `<span class="badge ${map[status]} rounded-pill px-2">${status}</span>`;
            }
            const row = document.getElementById(`grade-row-${key}`);
            if (row) {
                row.classList.toggle('table-success', status === 'Aprobada');
                row.classList.toggle('table-danger',  status === 'Reprobada');
                row.classList.toggle('table-warning',  status === 'Cursando' && raw !== null);
                row.classList.remove(status === 'Aprobada' ? 'table-danger' : 'table-success');
            }
            // Mark as dirty
            const btn = document.getElementById(`grade-save-btn-${key}`);
            if (btn) btn.classList.replace('btn-outline-primary', 'btn-primary');
            input.classList.toggle('text-success', raw !== null && raw >= 6);
            input.classList.toggle('fw-bold', raw !== null);
            input.classList.toggle('text-danger', raw !== null && raw < 6);
        }

        function gradeInputKeydown(e, rowIdx) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const inputs = [...document.querySelectorAll('#gradeCenterTableBody input[type="number"]')];
                const next = inputs[rowIdx + 1];
                if (next) next.focus();
            }
        }

        function renderGradeAssignmentRows(rows) {
            const tbody = document.getElementById('gradeCenterTableBody');
            if (!tbody) return;
            const start = (gradeRowsPage - 1) * TABLE_PER_PAGE;
            const pageRows = rows.slice(start, start + TABLE_PER_PAGE);
            tbody.innerHTML = pageRows.length ? renderGradeRows(pageRows) : renderGradeRows([]);
            buildTablePagination('grade-rows-pagination', 'grade-rows-info', gradeRowsPage, rows.length, TABLE_PER_PAGE, 'changeGradeRowsPage');
        }

        async function saveFinalGrade(gradeId, rowKey) {
            const scoreInput = document.getElementById(`grade-score-${rowKey}`);
            const rawScore = scoreInput?.value === '' ? null : parseFloat(scoreInput?.value);
            const status = normalizeGradeStatus(rawScore, '');

            try {
                const response = await fetch(`/admin/grades/${gradeId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ score: rawScore, status })
                });
                if (!response.ok) {
                    const error = await response.json();
                    showToast(error.detail || 'No se pudo guardar la calificacion', 'danger');
                    return;
                }
                const btn = document.getElementById(`grade-save-btn-${rowKey}`);
                if (btn) btn.classList.replace('btn-primary', 'btn-outline-primary');
                showToast('Calificación guardada', 'success');
                await loadGradeCenter();
                filterGradeAssignments();
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        async function saveAllGrades() {
            const inputs = [...document.querySelectorAll('#gradeCenterTableBody input[type="number"]')];
            if (!inputs.length) return;
            let saved = 0, errors = 0;
            for (const input of inputs) {
                const key     = input.id.replace('grade-score-', '');
                const rawScore = input.value === '' ? null : parseFloat(input.value);
                const status   = normalizeGradeStatus(rawScore, '');
                const gradeId  = key;
                try {
                    const res = await fetch(`/admin/grades/${gradeId}`, {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ score: rawScore, status })
                    });
                    if (res.ok) { saved++; const btn = document.getElementById(`grade-save-btn-${key}`); if (btn) btn.classList.replace('btn-primary','btn-outline-primary'); }
                    else errors++;
                } catch { errors++; }
            }
            showToast(errors ? `${saved} guardadas, ${errors} errores` : `${saved} calificaciones guardadas`, errors ? 'warning' : 'success');
            await loadGradeCenter();
            filterGradeAssignments();
        }

        function exportCurrentGradesCsv() {
            const rows = selectedGradeRows || [];
            if (!rows.length) return;
            const assignment = allAssignments.find(a => a.id === currentGradeAssignmentId);
            const lines = [
                `Materia,${assignment?.subject?.name || ''}`,
                `Docente,${assignment?.teacher?.full_name || ''}`,
                `Carrera,${assignment?.subject?.career || ''}`,
                '',
                'Matricula,Nombre,Intento,Calificacion,Estatus'
            ];
            rows.forEach(r => {
                const input = document.getElementById(`grade-score-${r.grade_id || r.course_enrollment_id}`);
                const score = input ? (input.value || '') : (r.score ?? '');
                lines.push(`${r.username},"${r.full_name || ''}",${r.attempt_type || 'Regular'},${score},${r.status || 'Cursando'}`);
            });
            const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
            const url  = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `calificaciones_${assignment?.subject?.name || 'asignacion'}_${new Date().toISOString().slice(0,10)}.csv`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        }

        let careerChartInstance = null;
        let paymentChartInstance = null;

        function generateCharts() {
            // Preparar datos para grafica de carreras
            const careerCounts = {};
            allStudents.forEach(s => {
                const career = s.carrera || 'Sin Asignar';
                careerCounts[career] = (careerCounts[career] || 0) + 1;
            });

            const careerLabels = Object.keys(careerCounts);
            const careerData = Object.values(careerCounts);

            document.getElementById('chartCareerPlaceholder').style.display = 'none';
            const ctxCareer = document.getElementById('careerChart');
            ctxCareer.style.display = 'block';

            if (careerChartInstance) careerChartInstance.destroy();
            careerChartInstance = new Chart(ctxCareer, {
                type: 'doughnut',
                data: {
                    labels: careerLabels,
                    datasets: [{
                        data: careerData,
                        backgroundColor: ['#0d6efd', '#20c997', '#ffc107', '#dc3545', '#6c757d', '#6610f2'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right' }
                    }
                }
            });

            // Preparar datos para grafica de pagos
            const sourcePayments = allCharges;
            const paymentCounts = { 'Pagado': 0, 'Pendiente': 0, 'Vencido': 0 };
            sourcePayments.forEach(p => {
                if (paymentCounts[p.status] !== undefined) {
                    paymentCounts[p.status]++;
                }
            });

            document.getElementById('chartPaymentPlaceholder').style.display = 'none';
            const ctxPayment = document.getElementById('paymentChart');
            ctxPayment.style.display = 'block';

            if (paymentChartInstance) paymentChartInstance.destroy();
            paymentChartInstance = new Chart(ctxPayment, {
                type: 'bar',
                data: {
                    labels: ['Pagado', 'Pendiente', 'Vencido'],
                    datasets: [{
                        label: 'Cantidad de Cargos',
                        data: [paymentCounts['Pagado'], paymentCounts['Pendiente'], paymentCounts['Vencido']],
                        backgroundColor: ['#198754', '#ffc107', '#dc3545'],
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
                }
            });
        }

        function calculateAcademicStats() {
            let totalGpa = 0;
            let studentsWithGpa = 0;
            let totalGrades = 0;
            let approvedGrades = 0;

            allStudents.forEach(s => {
                if (s.grades && s.grades.length > 0) {
                    const gradedSubjects = s.grades.filter(g => g.score !== null && g.score > 0);
                    
                    if (gradedSubjects.length > 0) {
                        const studentTotal = gradedSubjects.reduce((acc, g) => acc + parseFloat(g.score), 0);
                        totalGpa += (studentTotal / gradedSubjects.length);
                        studentsWithGpa++;
                    }

                    s.grades.forEach(g => {
                        if (g.status === 'Aprobada' || g.status === 'Reprobada') {
                            totalGrades++;
                            if (g.status === 'Aprobada') approvedGrades++;
                        }
                    });
                }
            });

            const avgGpa = studentsWithGpa > 0 ? (totalGpa / studentsWithGpa).toFixed(1) : '0.0';
            const approvedRate = totalGrades > 0 ? Math.round((approvedGrades / totalGrades) * 100) : 0;
            const failedRate = totalGrades > 0 ? 100 - approvedRate : 0;

            document.getElementById('reportAvgGpa').textContent = avgGpa;
            document.getElementById('reportApprovedRate').textContent = `${approvedRate}%`;
            document.getElementById('reportFailedRate').textContent = `${failedRate}%`;
        }

        function generateReport() {
            if (!allStudents || !allStudents.length) {
                showToast('No hay datos de alumnos para exportar', 'warning');
                return;
            }
            const headers = ['Matricula', 'Nombre Completo', 'Correo', 'Carrera', 'Modalidad', 'Semestre', 'Grupo', 'Rol'];
            const rows = allStudents.map(s => [
                s.username || '',
                s.full_name || '',
                s.email || '',
                s.carrera || s.career || '',
                s.modalidad || s.modality || '',
                s.semestre || s.semester || '',
                s.grupo || '',
                s.role || 'Alumno'
            ]);
            const csvContent = [headers, ...rows]
                .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
                .join('\r\n');
            const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `reporte_alumnos_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            showToast(`Reporte exportado: ${allStudents.length} alumnos`, 'success');
        }

        async function openExportGradesModal() {
            // Cargar ciclos en el select
            const sel = document.getElementById('exportGradesCycleId');
            sel.innerHTML = '<option value="">Todos los ciclos</option>';
            try {
                const res = await fetch('/admin/school-cycles/all', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    const cycles = await res.json();
                    cycles.forEach(c => {
                        const opt = document.createElement('option');
                        opt.value = c.id;
                        opt.textContent = `${c.period || 'Sin periodo'}${c.is_active ? ' (activo)' : ''}`;
                        if (c.is_active) opt.selected = true;
                        sel.appendChild(opt);
                    });
                }
            } catch(e) { /* silent */ }
            new bootstrap.Modal(document.getElementById('exportGradesModal')).show();
        }

        async function doExportGradesCsv() {
            const cycleId = document.getElementById('exportGradesCycleId').value;
            const url = cycleId
                ? `/admin/reports/grades-export?cycle_id=${cycleId}`
                : '/admin/reports/grades-export';
            showToast('Generando CSV de calificaciones...', 'info');
            try {
                const res = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
                if (!res.ok) { showToast('Error al exportar', 'danger'); return; }
                const blob = await res.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `calificaciones_${new Date().toISOString().slice(0,10)}.csv`;
                a.click();
                URL.revokeObjectURL(a.href);
                bootstrap.Modal.getInstance(document.getElementById('exportGradesModal')).hide();
                showToast('CSV descargado correctamente', 'success');
            } catch(e) { showToast('Error de conexion', 'danger'); }
        }

        async function loadSchoolCycle() {
            await renderTuitionMatrix(null);
            try {
                const res = await fetch('/admin/school-cycle', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    const cycle = await res.json();
                    if (cycle) {
                        document.getElementById('settingCurrentPeriod').value = cycle.period || '';
                        document.getElementById('settingStartDate').value = cycle.start_date ? cycle.start_date.substring(0, 10) : '';
                        document.getElementById('settingEndDate').value = cycle.end_date ? cycle.end_date.substring(0, 10) : '';
                        updateCyclePreview();
                        await renderTuitionMatrix(cycle.tuitions || []);
                    }
                }
            } catch(e) { /* silent */ }
        }

        async function renderTuitionMatrix(savedTuitions) {
            const container = document.getElementById('tuitionMatrix');
            if (!container) return;
            const careers = catalogCareers.length > 0 ? catalogCareers : DEFAULT_CAREERS;
            const modalities = ['Presencial Intensiva','Presencial Sabatino','Virtual'];
            // Build modality objects with IDs from catalogModalities
            const modalityObjs = modalities.map(name => {
                const found = catalogModalities.find(m => m.name === name);
                return found || { id: null, name };
            });
            // Build lookup from saved tuitions
            const lookup = {};
            if (savedTuitions) {
                savedTuitions.forEach(t => { lookup[`${t.career_id}_${t.modality_id}`] = t.amount; });
            }
            let html = '<table class="table table-sm table-bordered small"><thead><tr><th>Carrera</th>';
            modalityObjs.forEach(m => { html += `<th class="text-center">${m.name}</th>`; });
            html += '</tr></thead><tbody>';
            careers.forEach(c => {
                html += `<tr><td class="fw-bold">${c.name}</td>`;
                modalityObjs.forEach(m => {
                    const key = `${c.id}_${m.id}`;
                    const val = lookup[key] || '';
                    html += `<td><input type="number" class="form-control form-control-sm tuition-input" data-career="${c.id}" data-modality="${m.id}" placeholder="$0" min="0" step="0.01" value="${val}"></td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        }

        function getTuitionMatrix() {
            const inputs = document.querySelectorAll('.tuition-input');
            const tuitions = [];
            inputs.forEach(inp => {
                const amount = parseFloat(inp.value);
                const careerId = parseInt(inp.dataset.career);
                const modalityId = parseInt(inp.dataset.modality);
                if (amount > 0 && careerId && modalityId) {
                    tuitions.push({ career_id: careerId, modality_id: modalityId, amount });
                }
            });
            return tuitions;
        }

        function updateCyclePreview() {
            const start = document.getElementById('settingStartDate').value;
            const end = document.getElementById('settingEndDate').value;
            const preview = document.getElementById('cycleMonthsPreview');
            if (!start || !end) { preview.innerHTML = ''; return; }
            const months = [];
            let cur = new Date(start + 'T00:00:00');
            const endDate = new Date(end + 'T00:00:00');
            while (cur <= endDate) {
                months.push(cur.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' }));
                cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
            }
            preview.innerHTML = `<div class="alert alert-info py-2 small mb-0"><strong>${months.length} meses de pago:</strong> ${months.join(', ')}</div>`;
        }

        async function saveSettings() {
            const period = document.getElementById('settingCurrentPeriod').value.trim();
            const startDate = document.getElementById('settingStartDate').value;
            const endDate = document.getElementById('settingEndDate').value;
            const instName = document.getElementById('settingInstName').value.trim();

            if (!period || !startDate || !endDate || !instName) {
                showToast('Completa todos los campos obligatorios.', 'danger');
                return;
            }
            if (new Date(startDate) >= new Date(endDate)) {
                showToast('La fecha de inicio debe ser anterior a la fecha de fin.', 'danger');
                return;
            }

            const tuitions = getTuitionMatrix();
            if (tuitions.length === 0) {
                showToast('Agrega al menos un costo de colegiatura en la tabla.', 'danger');
                return;
            }

            try {
                // 1. Guardar ciclo escolar con costos
                const cycleRes = await fetch('/admin/school-cycle', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        period,
                        start_date: startDate + 'T00:00:00',
                        end_date: endDate + 'T23:59:59',
                        monthly_amount: 0,
                        is_active: true,
                        tuitions
                    })
                });
                if (!cycleRes.ok) {
                    showToast('Error al guardar el ciclo escolar.', 'danger');
                    return;
                }

                // 2. Generar pagos mensuales para alumnos activos
                const payRes = await fetch('/admin/school-cycle/generate-payments', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (payRes.ok) {
                    const result = await payRes.json();
                    showToast(`Ciclo guardado. ${result.payments_created} pagos generados para ${result.students_affected} alumnos activos.`, 'success');
                    updateCyclePreview();
                    loadAdminData();
                } else {
                    showToast('Ciclo guardado. Error al generar pagos.', 'warning');
                }
            } catch(e) {
                showToast('Error de conexion con el servidor.', 'danger');
            }
        }
