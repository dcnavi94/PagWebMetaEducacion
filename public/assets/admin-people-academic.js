        function renderSubjects(subjects) {
            const table = document.getElementById('allSubjectsTableBody');
            if (subjects.length === 0) {
                table.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No hay materias registradas.</td></tr>';
                buildTablePagination('subjects-pagination', 'subjects-info', 1, 0, TABLE_PER_PAGE, 'changeSubjectsPage');
                return;
            }
            const start = (subjectsPage - 1) * TABLE_PER_PAGE;
            const page  = subjects.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(s => {
                const moodleBadge = s.moodle_course_id
                    ? `<span class="badge bg-success-subtle text-success border border-success-subtle">Course #${s.moodle_course_id}</span>`
                    : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Pendiente</span>';
                return `<tr>
                    <td class="fw-bold">${s.id}</td>
                    <td>${s.name}</td>
                    <td><span class="badge bg-secondary">${s.career}</span></td>
                    <td>${s.semester}</td>
                    <td>${s.credits}</td>
                    <td>${moodleBadge}</td>
                    <td>
                        <button class="btn btn-sm ${s.moodle_course_id ? 'btn-outline-success' : 'btn-outline-primary'}" title="${s.moodle_course_id ? 'Validar o recrear vínculo Moodle' : 'Sincronizar materia con Moodle'}" onclick="syncSubjectMoodle(${s.id})"><i class="bi bi-arrow-repeat"></i></button>
                        <button class="btn btn-sm btn-light" title="Editar" onclick="openEditSubject(${s.id})"><i class="bi bi-pencil"></i></button>
                    </td>
                </tr>`;
            }).join('');
            buildTablePagination('subjects-pagination', 'subjects-info', subjectsPage, subjects.length, TABLE_PER_PAGE, 'changeSubjectsPage');
        }

        function renderTeachers(teachers) {
            const table = document.getElementById('allTeachersTableBody');
            if (teachers.length === 0) {
                table.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No hay docentes registrados.</td></tr>';
                buildTablePagination('teachers-pagination', 'teachers-info', 1, 0, TABLE_PER_PAGE, 'changeTeachersPage');
                return;
            }
            const start = (teachersPage - 1) * TABLE_PER_PAGE;
            const page  = teachers.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(t => `
                <tr>
                    <td class="fw-bold">${t.username}</td>
                    <td>${t.full_name || 'Sin nombre'}</td>
                    <td>${t.email || 'N/A'}</td>
                    <td>
                        <span class="badge bg-info me-1">Activo</span>
                        ${t.moodle_id ? `<span class="badge bg-success-subtle text-success border border-success-subtle">Moodle ID ${t.moodle_id}</span>` : `<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Sin Moodle</span>`}
                    </td>
                    <td>
                        <button class="btn btn-sm ${t.moodle_id ? 'btn-outline-success' : 'btn-outline-secondary'}" title="${t.moodle_id ? 'Validar vínculo Moodle (ID: '+t.moodle_id+')' : 'Sincronizar docente con Moodle'}" onclick="syncTeacherMoodle('${t.username}', true)"><i class="bi bi-laptop"></i></button>
                        <button class="btn btn-sm btn-light" title="Ver Perfil" onclick="openViewTeacher('${t.username}')"><i class="bi bi-eye"></i></button>
                        <button class="btn btn-sm btn-light" title="Editar" onclick="openEditTeacher('${t.username}')"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-primary" title="Asignar Materia" onclick="openAssignSubjectForTeacher('${t.username}')"><i class="bi bi-journal-plus"></i></button>
                    </td>
                </tr>
            `).join('');
            buildTablePagination('teachers-pagination', 'teachers-info', teachersPage, teachers.length, TABLE_PER_PAGE, 'changeTeachersPage');
        }

        function getInitials(name) {
            if (!name) return "NN";
            const parts = name.split(' ');
            if (parts.length >= 2) {
                return (parts[0][0] + parts[1][0]).toUpperCase();
            }
            return name.substring(0, 2).toUpperCase();
        }

        function getRandomColorClass() {
            const colors = ['bg-primary', 'bg-pink', 'bg-secondary', 'bg-info', 'bg-success', 'bg-warning'];
            return colors[Math.floor(Math.random() * colors.length)];
        }

        async function quickUpdateStatus(username, field, value) {
            const student = allStudents.find(s => s.username === username);
            if (!student) return;
            const payload = { [field]: value };
            try {
                const res = await fetch(`/admin/students/${username}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    student[field] = value;
                    renderStudents(filteredStudents);
                    showToast(`Actualizado: ${value}`, 'success');
                } else {
                    showToast('Error al actualizar', 'danger');
                }
            } catch(e) {
                showToast('Error de conexion', 'danger');
            }
        }

        function renderStatusBadge(userStatus) {
            const st = userStatus || 'Activo';
            if (st === 'Baja') return '<span class="badge bg-danger">Baja</span>';
            if (st === 'Bloqueado') return '<span class="badge bg-warning text-dark">Bloqueado</span>';
            return '<span class="badge bg-success">Activo</span>';
        }

        function renderEnrollmentBadge(es) {
            const st = es || 'No Inscrito';
            if (st === 'Inscrito') return '<span class="badge bg-primary">Inscrito</span>';
            if (st === 'Baja Temporal') return '<span class="badge bg-warning text-dark">Baja Temp.</span>';
            if (st === 'Baja Definitiva') return '<span class="badge bg-danger">Baja Def.</span>';
            if (st === 'Graduado') return '<span class="badge bg-success">Graduado</span>';
            return '<span class="badge bg-secondary">No Inscrito</span>';
        }

        function renderStudents(students) {
            const recentTable = document.getElementById('recentStudentsTableBody');
            const allTable = document.getElementById('allStudentsTableBody');
            
            // Ya no actualizamos totalStudentsCount aqui, se hace con /admin/stats
            
            if (students.length === 0) {
                recentTable.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No hay alumnos registrados.</td></tr>';
                allTable.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay alumnos registrados.</td></tr>';
                return;
            }

            let recentHtml = '';
            let allHtml = '';

            // Mostrar los ultimos 4 en el dashboard
            const recentStudents = [...students].reverse().slice(0, 4);
            
            recentStudents.forEach(s => {
                const initials = getInitials(s.full_name);
                const colorClass = getRandomColorClass();
                
                let displayCareer = s.carrera || 'N/A';

                recentHtml += `
                    <tr>
                        <td class="fw-bold">${s.username}</td>
                        <td>
                            <div class="d-flex align-items-center gap-2">
                                <div class="${colorClass} text-white rounded-circle d-flex align-items-center justify-content-center" style="width: 30px; height: 30px; font-size: 0.8rem;">${initials}</div>
                                ${s.full_name || 'Sin nombre'}
                            </div>
                        </td>
                        <td>${displayCareer}</td>
                        <td>${renderStatusBadge(s.user_status)}</td>
                        <td>
                            <button class="btn btn-sm btn-light rounded-pill" onclick="openEditStudent('${s.username}')"><i class="bi bi-pencil"></i></button>
                        </td>
                    </tr>
                `;
            });

            // Mostrar todos en la tabla de gestion con paginacion
            const startIndex = (currentPage - 1) * itemsPerPage;
            const endIndex = startIndex + itemsPerPage;
            const paginatedStudents = students.slice(startIndex, endIndex);

            paginatedStudents.forEach(s => {
                const gpa = s.average_score != null ? Number(s.average_score).toFixed(1) : '—';
                const gpaColor = s.average_score == null ? 'text-muted' : s.average_score >= 7 ? 'text-success' : s.average_score >= 6 ? 'text-warning' : 'text-danger';
                const displayCareer = s.carrera || 'N/A';

                allHtml += `
                    <tr>
                        <td class="fw-bold">${s.username}</td>
                        <td>${s.full_name || 'Sin nombre'}</td>
                        <td>${displayCareer}</td>
                        <td>${s.semestre || 'N/A'}</td>
                        <td class="fw-bold ${gpaColor}">${gpa}</td>
                        <td>
                            <div class="dropdown d-inline">
                                <span class="badge-clickable" data-bs-toggle="dropdown" style="cursor:pointer;" title="Cambiar estatus de cuenta">
                                    ${renderStatusBadge(s.user_status)}
                                </span>
                                <ul class="dropdown-menu dropdown-menu-sm shadow-sm">
                                    <li><h6 class="dropdown-header small">Estatus de Cuenta</h6></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','user_status','Activo');return false;"><span class="badge bg-success me-1">Activo</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','user_status','Baja');return false;"><span class="badge bg-danger me-1">Baja</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','user_status','Bloqueado');return false;"><span class="badge bg-warning text-dark me-1">Bloqueado</span></a></li>
                                </ul>
                            </div>
                        </td>
                        <td>
                            <div class="dropdown d-inline">
                                <span class="badge-clickable" data-bs-toggle="dropdown" style="cursor:pointer;" title="Cambiar estatus de inscripcion">
                                    ${renderEnrollmentBadge(s.enrollment_status)}
                                </span>
                                <ul class="dropdown-menu dropdown-menu-sm shadow-sm">
                                    <li><h6 class="dropdown-header small">Estatus de Inscripcion</h6></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','enrollment_status','Inscrito');return false;"><span class="badge bg-primary me-1">Inscrito</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','enrollment_status','No Inscrito');return false;"><span class="badge bg-secondary me-1">No Inscrito</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','enrollment_status','Baja Temporal');return false;"><span class="badge bg-warning text-dark me-1">Baja Temporal</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','enrollment_status','Baja Definitiva');return false;"><span class="badge bg-danger me-1">Baja Definitiva</span></a></li>
                                    <li><a class="dropdown-item small" href="#" onclick="quickUpdateStatus('${s.username}','enrollment_status','Graduado');return false;"><span class="badge bg-success me-1">Graduado</span></a></li>
                                </ul>
                            </div>
                        </td>
                        <td class="text-nowrap">
                            <button class="btn btn-sm ${s.moodle_id ? 'btn-outline-success' : 'btn-outline-secondary'}" onclick="syncStudentMoodle('${s.username}', true)" title="${s.moodle_id ? 'Validar vínculo Moodle (ID: '+s.moodle_id+')' : 'Sincronizar alumno con Moodle'}">
                                <i class="bi bi-laptop"></i>
                            </button>
                            <button class="btn btn-sm btn-light" onclick="openViewStudent('${s.username}')" title="Ver Perfil"><i class="bi bi-eye"></i></button>
                            <button class="btn btn-sm btn-light" onclick="openEditStudent('${s.username}')" title="Editar"><i class="bi bi-pencil"></i></button>
                            <button class="btn btn-sm btn-outline-warning" onclick="openResetPassword('${s.username}')" title="Restablecer Contraseña"><i class="bi bi-key"></i></button>
                            <button class="btn btn-sm btn-outline-primary" onclick="openEnrollStudent('${s.username}')" title="Inscribir en Materia"><i class="bi bi-journal-plus"></i></button>
                            <button class="btn btn-sm btn-outline-info" onclick="openAssignAdvisorModal('${s.username}')" title="Asignar Asesor Virtual"><i class="bi bi-person-video3"></i></button>
                            <button class="btn btn-sm btn-outline-danger" onclick="confirmDeleteStudent('${escHtml(s.username)}','${escHtml(s.full_name||s.username)}')" title="Eliminar alumno"><i class="bi bi-trash"></i></button>
                        </td>
                    </tr>
                `;
            });

            recentTable.innerHTML = recentHtml;
            allTable.innerHTML = allHtml;
        }

        function renderPagination() {
            const totalPages = Math.ceil(filteredStudents.length / itemsPerPage);
            const paginationContainer = document.getElementById('students-pagination');
            if (!paginationContainer) {
                // Create pagination container if it doesn't exist
                const allTableContainer = document.getElementById('allStudentsTableBody').closest('.table-responsive');
                const nav = document.createElement('nav');
                nav.className = 'mt-3 d-flex justify-content-end';
                nav.innerHTML = '<ul class="pagination pagination-sm" id="students-pagination"></ul>';
                allTableContainer.parentNode.insertBefore(nav, allTableContainer.nextSibling);
            }
            
            const ul = document.getElementById('students-pagination');
            let html = '';
            
            // Previous button
            html += `<li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="changePage(${currentPage - 1}); return false;" aria-label="Previous">
                    <span aria-hidden="true">&laquo;</span>
                </a>
            </li>`;
            
            // Page numbers
            for (let i = 1; i <= totalPages; i++) {
                html += `<li class="page-item ${currentPage === i ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="changePage(${i}); return false;">${i}</a>
                </li>`;
            }
            
            // Next button
            html += `<li class="page-item ${currentPage === totalPages || totalPages === 0 ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="changePage(${currentPage + 1}); return false;" aria-label="Next">
                    <span aria-hidden="true">&raquo;</span>
                </a>
            </li>`;
            
            ul.innerHTML = html;
        }

        function changePage(page) {
            const totalPages = Math.ceil(filteredStudents.length / itemsPerPage);
            if (page < 1 || page > totalPages) return;
            currentPage = page;
            renderStudents(filteredStudents);
            renderPagination();
        }

        function buildTablePagination(ulId, infoId, page, total, perPage, changeFn) {
            const totalPages = Math.ceil(total / perPage) || 1;
            const ulEl = document.getElementById(ulId);
            if (!ulEl) return;
            const infoEl = document.getElementById(infoId);
            const from = total === 0 ? 0 : (page - 1) * perPage + 1;
            const to   = Math.min(page * perPage, total);
            if (infoEl) infoEl.textContent = total > 0 ? `${from}–${to} de ${total}` : '';
            if (totalPages <= 1) { ulEl.innerHTML = ''; return; }
            let pages = [];
            if (totalPages <= 7) {
                for (let i = 1; i <= totalPages; i++) pages.push(i);
            } else {
                pages.push(1);
                if (page > 3) pages.push('…');
                for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
                if (page < totalPages - 2) pages.push('…');
                pages.push(totalPages);
            }
            let html = `<li class="page-item ${page===1?'disabled':''}"><a class="page-link" href="#" onclick="event.preventDefault();${changeFn}(${page-1})">&laquo;</a></li>`;
            pages.forEach(p => {
                if (typeof p === 'string') {
                    html += `<li class="page-item disabled"><span class="page-link">${p}</span></li>`;
                } else {
                    html += `<li class="page-item ${p===page?'active':''}"><a class="page-link" href="#" onclick="event.preventDefault();${changeFn}(${p})">${p}</a></li>`;
                }
            });
            html += `<li class="page-item ${page===totalPages?'disabled':''}"><a class="page-link" href="#" onclick="event.preventDefault();${changeFn}(${page+1})">&raquo;</a></li>`;
            ulEl.innerHTML = html;
        }

        function changeTeachersPage(p)      { teachersPage = p;      renderTeachers(filteredTeachers); }
        function changeSubjectsPage(p)      { subjectsPage = p;      renderSubjects(filteredSubjects); }
        function changeAssignmentsPage(p)   { assignmentsPage = p;   renderAssignments(filteredAssignments.length ? filteredAssignments : allAssignments); }
        function changeControlSchoolPage(p) { controlSchoolPage = p; renderControlSchoolRows(filteredStudentEnrollments); }
        function changeBlockedPage(p)       { blockedPage = p;       renderBlockedStudents(blockedStudents); }
        function changeChargesPage(p)       { chargesPage = p;       renderCharges(filteredCharges); }
        function changeServicesPage(p)      { servicesPage = p;      renderServices(filteredServices); }
        function changeGradeRowsPage(p)     { gradeRowsPage = p;     renderGradeAssignmentRows(selectedGradeRows); }
        function changeSupportTicketsPage(p){ supportTicketsPage = p; renderAdminSupportTickets(filteredSupportTickets); }

        async function openViewStudent(username) {
            try {
                const response = await fetch(`/admin/students/${username}/full`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (response.ok) {
                    const rawStudent = await response.json();
                    const student = applyOperationalEnrollmentData(rawStudent);

                    // Normalize flat grade fields from /full endpoint to nested structure
                    student.grades = (student.grades || []).map(g => ({
                        ...g,
                        subject: { name: g.subject_name, semester: g.subject_semester, credits: g.subject_credits }
                    }));

                    // Compute display status by comparing subject semester vs student's current semester
                    const studentSemNum = getSemesterSortValue(student.semestre);
                    student.grades = student.grades.map(g => {
                        const hasScore = g.score !== null && g.score !== undefined;
                        const hasFinalStatus = g.status === 'Aprobada' || g.status === 'Reprobada';
                        if (hasScore || hasFinalStatus) return g;
                        const subSemNum = getSemesterSortValue(g.subject?.semester || g.subject_semester || '');
                        let displayStatus;
                        if (subSemNum > studentSemNum)       displayStatus = 'Proximamente';
                        else if (subSemNum === studentSemNum) displayStatus = 'Cursando';
                        else                                  displayStatus = 'Sin calificacion';
                        return { ...g, status: displayStatus };
                    });

                    // Info Personal
                    document.getElementById('viewStudentName').textContent = student.full_name || 'Sin nombre';
                    document.getElementById('viewStudentUsername').textContent = student.username;
                    document.getElementById('viewStudentCareer').textContent = student.carrera || 'N/A';
                    document.getElementById('viewStudentSemester').textContent = student.semestre || 'N/A';
                    document.getElementById('viewStudentGroup').textContent = student.grupo || 'N/A';
                    document.getElementById('viewStudentEmail').textContent = student.email || 'N/A';
                    
                    // Agregar modalidad si existe
                    let modalidadHtml = '';
                    if (student.modalidad) {
                        modalidadHtml = `<div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Modalidad</small><span class="fw-medium">${student.modalidad}</span></div>`;
                    }
                    
                    // Reconstruir la tarjeta de info personal
                    const infoContainer = document.querySelector('#viewStudentModal .card-body .text-start');
                    
                    let displayCareer = student.carrera || 'N/A';
                    if (displayCareer === '0' || displayCareer === 0) {
                        displayCareer = 'Preparatoria';
                    }

                    infoContainer.innerHTML = `
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Carrera</small><span id="viewStudentCareer" class="fw-medium">${displayCareer}</span></div>
                        ${modalidadHtml}
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Semestre</small><span id="viewStudentSemester" class="fw-medium">${student.semestre || 'N/A'}</span></div>
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Grupo</small><span id="viewStudentGroup" class="fw-medium">${student.grupo || 'N/A'}</span></div>
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Email</small><span id="viewStudentEmail" class="fw-medium text-break">${student.email || 'N/A'}</span></div>
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">CURP</small><span id="viewStudentCurp" class="fw-medium text-break">${escHtml(student.curp || 'N/A')}</span></div>
                        <div class="mb-3"><small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Clave unica SEG</small><span id="viewStudentSegUniqueKey" class="fw-medium text-break">${escHtml(student.seg_unique_key || 'N/A')}</span></div>
                        <div class="mb-3">
                            <small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Asesor virtual</small>
                            <div class="small text-muted mb-2">${student.advisor?.teacher_full_name || student.advisor?.teacher_username || 'Sin asesor asignado'} ${student.advisor?.period_label ? `· ${student.advisor.period_label}` : ''}</div>
                            <button class="btn btn-sm btn-outline-info rounded-pill" onclick="openAssignAdvisorModal('${student.username}')">
                                <i class="bi bi-person-video3 me-1"></i>Asignar/Actualizar asesor
                            </button>
                        </div>
                        <div class="mb-3 d-grid">
                            <button class="btn btn-sm btn-outline-dark rounded-pill" onclick="openStudentDocumentsTab()">
                                <i class="bi bi-folder2-open me-1"></i>Ver documentos escaneados
                            </button>
                        </div>
                        <div class="mb-0">
                            <small class="text-muted d-block text-uppercase fw-bold" style="font-size: 0.7rem;">Moodle</small>
                            <div id="viewStudentMoodleStatus" class="small text-muted mb-2">Sin verificar</div>
                            <div class="d-grid gap-2">
                                <button class="btn btn-sm btn-outline-primary rounded-pill" id="viewStudentMoodleSyncButton" onclick="syncViewedStudentMoodle()">
                                    <i class="bi bi-arrow-repeat me-1"></i>Sincronizar con Moodle
                                </button>
                                <button class="btn btn-sm btn-outline-dark rounded-pill" onclick="linkViewedStudentMoodleManual()">
                                    <i class="bi bi-link-45deg me-1"></i>Vincular Moodle ID manual
                                </button>
                                <button class="btn btn-sm btn-outline-success rounded-pill" id="viewStudentMoodleEnrollButton" onclick="openMoodleEnrollModal(document.getElementById('viewStudentUsername').textContent)">
                                    <i class="bi bi-mortarboard me-1"></i>Inscribir en Moodle Course
                                </button>
                            </div>
                        </div>
                    `;
                    renderViewedStudentMoodleStatus(student);
                    
                    const avatar = document.getElementById('viewStudentAvatar');
                    avatar.textContent = getInitials(student.full_name);
                    avatar.className = `rounded-circle d-inline-flex align-items-center justify-content-center text-white mb-3 shadow-sm ${getRandomColorClass()}`;

                    // Calificaciones
                    const currentGradesContainer = document.getElementById('viewStudentCurrentGrades');
                    const historyGradesContainer = document.getElementById('viewStudentHistoryGrades');
                    const paginationContainer = document.getElementById('viewStudentGradesPagination');

                    if (student.grades && student.grades.length > 0) {
                        const currentGrades = student.grades.filter(g => g.status === 'Cursando');
                        const historyGrades = student.grades.filter(g => g.status !== 'Cursando');

                        // Render Current Grades
                        if (currentGrades.length > 0) {
                            currentGradesContainer.innerHTML = renderCurriculumSummary(student.grades) + renderStudentGradeGroups(groupGradesBySemester(currentGrades));
                        } else {
                            currentGradesContainer.innerHTML = '<div class="alert alert-light text-center mb-0 py-3 text-muted">No hay materias en curso actualmente.</div>';
                        }

                        // Render History Grades (Grouped by Period, paginated to 15)
                        window.currentStudentHistoryGrades = historyGrades;
                        window.currentStudentHistoryPage = 1;
                        renderHistoryGrades();
                    } else {
                        currentGradesContainer.innerHTML = renderCurriculumSummary([]) + '<div class="alert alert-light text-center mb-0 py-3 text-muted">No hay calificaciones registradas.</div>';
                        historyGradesContainer.innerHTML = '';
                        paginationContainer.innerHTML = '';
                    }

                    // Pagos
                    const paymentsTbody = document.getElementById('viewStudentPayments');
                    if (student.payments && student.payments.length > 0) {
                        paymentsTbody.innerHTML = student.payments.map(p => `
                            <tr>
                                <td>${p.concept}</td>
                                <td>$${p.amount.toFixed(2)}</td>
                                <td>${new Date(p.due_date).toLocaleDateString()}</td>
                                <td><span class="badge ${p.status === 'Pagado' ? 'bg-success' : (p.status === 'Vencido' ? 'bg-danger' : 'bg-warning')}">${p.status}</span></td>
                                <td>
                                    <button class="btn btn-sm btn-light rounded-pill" onclick="openEditPayment(${p.id}, '${p.status}')"><i class="bi bi-pencil"></i></button>
                                </td>
                            </tr>
                        `).join('');
                    } else {
                        paymentsTbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">No hay pagos registrados</td></tr>';
                    }

                    // Servicios
                    const servicesTbody = document.getElementById('viewStudentServices');
                    if (student.service_requests && student.service_requests.length > 0) {
                        servicesTbody.innerHTML = student.service_requests.map(s => `
                            <tr>
                                <td>${s.type}</td>
                                <td>${new Date(s.request_date).toLocaleDateString()}</td>
                                <td><span class="badge ${s.status === 'Entregado' ? 'bg-success' : (s.status === 'En Proceso' ? 'bg-warning' : 'bg-secondary')}">${s.status}</span></td>
                                <td>
                                    <button class="btn btn-sm btn-light rounded-pill" onclick="openEditService(${s.id}, '${s.status}')"><i class="bi bi-pencil"></i></button>
                                </td>
                            </tr>
                        `).join('');
                    } else {
                        servicesTbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-3">No hay tramites registrados</td></tr>';
                    }

                    renderStudentDocuments(student.documents || []);

                    const viewModal = new bootstrap.Modal(document.getElementById('viewStudentModal'));
                    viewModal.show();
                } else {
                    showToast('Error al cargar la informacion del alumno', true);
                }
            } catch (error) {
                console.error('Error:', error);
                showToast('Error de conexion', true);
            }
        }

        function renderStudentDocuments(documents = []) {
            const container = document.getElementById('viewStudentDocuments');
            if (!container) return;
            if (!documents.length) {
                container.innerHTML = '<div class="alert alert-light text-center mb-0 py-3 text-muted">No hay documentos escaneados registrados.</div>';
                return;
            }
            container.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead class="table-light">
                            <tr>
                                <th>Tipo</th>
                                <th>Archivo</th>
                                <th>Subido</th>
                                <th class="text-end">Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${documents.map(doc => `
                                <tr>
                                    <td>${escHtml(doc.document_type || 'Documento')}</td>
                                    <td class="text-break">${escHtml(doc.filename || '-')}</td>
                                    <td>${doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString('es-MX') : '-'}</td>
                                    <td class="text-end">
                                        <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="downloadStudentDocument(${doc.id})"><i class="bi bi-download me-1"></i>Descargar</button>
                                        <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="deleteStudentDocument(${doc.id})"><i class="bi bi-trash"></i></button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }

        function openStudentDocumentsTab() {
            const trigger = document.querySelector('#studentTabs [data-bs-target="#tab-documents"]');
            if (trigger) {
                bootstrap.Tab.getOrCreateInstance(trigger).show();
            }
            reloadStudentDocuments();
        }

        async function reloadStudentDocuments() {
            const username = document.getElementById('viewStudentUsername')?.textContent?.trim();
            const container = document.getElementById('viewStudentDocuments');
            if (!username || !container) return;
            container.innerHTML = '<div class="text-muted text-center py-3">Cargando documentos...</div>';
            try {
                const response = await fetch(`/admin/students/${encodeURIComponent(username)}/documents`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    container.innerHTML = '<div class="alert alert-danger mb-0">No se pudieron cargar los documentos.</div>';
                    return;
                }
                const payload = await response.json();
                renderStudentDocuments(payload.items || []);
            } catch (error) {
                console.error(error);
                container.innerHTML = '<div class="alert alert-danger mb-0">Error de conexion al cargar documentos.</div>';
            }
        }

        async function uploadStudentDocument(event) {
            event.preventDefault();
            const username = document.getElementById('viewStudentUsername')?.textContent?.trim();
            const fileInput = document.getElementById('studentDocumentFile');
            const typeInput = document.getElementById('studentDocumentType');
            if (!username || !fileInput?.files?.length) {
                showToast('Selecciona un archivo para subir', true);
                return;
            }
            const formData = new FormData();
            formData.append('document_type', (typeInput?.value || 'Documento').trim() || 'Documento');
            formData.append('file', fileInput.files[0]);
            try {
                const response = await fetch(`/admin/students/${encodeURIComponent(username)}/documents`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo subir el documento'), true);
                    return;
                }
                showToast('Documento guardado en expediente');
                document.getElementById('studentDocumentUploadForm')?.reset();
                await reloadStudentDocuments();
            } catch (error) {
                console.error(error);
                showToast('Error de conexion al subir documento', true);
            }
        }

        async function downloadStudentDocument(documentId) {
            const username = document.getElementById('viewStudentUsername')?.textContent?.trim();
            if (!username) return;
            try {
                const response = await fetch(`/admin/students/${encodeURIComponent(username)}/documents/${documentId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo descargar el documento'), true);
                    return;
                }
                const blob = await response.blob();
                const disposition = response.headers.get('content-disposition') || '';
                const match = disposition.match(/filename="?([^"]+)"?/i);
                const filename = match ? match[1] : `documento_${documentId}`;
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
            } catch (error) {
                console.error(error);
                showToast('Error de conexion al descargar documento', true);
            }
        }

        async function deleteStudentDocument(documentId) {
            const username = document.getElementById('viewStudentUsername')?.textContent?.trim();
            if (!username || !confirm('Eliminar este documento escaneado del expediente?')) return;
            try {
                const response = await fetch(`/admin/students/${encodeURIComponent(username)}/documents/${documentId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo eliminar el documento'), true);
                    return;
                }
                showToast('Documento eliminado');
                await reloadStudentDocuments();
            } catch (error) {
                console.error(error);
                showToast('Error de conexion al eliminar documento', true);
            }
        }

        function openEditGrade(id, score, status) {
            document.getElementById('editGradeId').value = id;
            document.getElementById('editGradeScore').value = score !== null && score !== undefined ? score : '';
            document.getElementById('editGradeStatus').value = '';
            new bootstrap.Modal(document.getElementById('editGradeModal')).show();
        }

        function openResetPassword(username) {
            document.getElementById('resetPasswordUsername').value = username;
            document.getElementById('resetPasswordUsernameDisplay').textContent = username;
            document.getElementById('resetPasswordValue').value = 'Unives12345';
            new bootstrap.Modal(document.getElementById('resetPasswordModal')).show();
        }

        async function doResetPassword() {
            const username = document.getElementById('resetPasswordUsername').value;
            const password = document.getElementById('resetPasswordValue').value.trim();
            if (!password || password.length < 6) { showToast('La contrasena debe tener al menos 6 caracteres', true); return; }
            try {
                const res = await fetch(`/admin/students/${username}/password`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                if (res.ok) {
                    showToast(`Contrasena de ${username} restablecida`);
                    bootstrap.Modal.getInstance(document.getElementById('resetPasswordModal')).hide();
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Error al restablecer', true);
                }
            } catch (e) { showToast('Error de conexion', true); }
        }

        function openEnrollStudent(username) {
            document.getElementById('enrollStudentUsername').value = username;
            document.getElementById('enrollStudentUsernameDisplay').textContent = username;
            // Populate assignments dropdown
            const sel = document.getElementById('enrollAssignmentId');
            sel.innerHTML = '<option value="">Seleccionar asignacion...</option>' +
                allAssignments.map(a => {
                    const sub = a.subject || {};
                    const tch = a.teacher || {};
                    return `<option value="${a.id}">${sub.name || '?'} - ${tch.full_name || 'Sin docente'} (${sub.career || '?'})</option>`;
                }).join('');
            new bootstrap.Modal(document.getElementById('enrollStudentModal')).show();
        }

        async function doEnrollStudent() {
            const username = document.getElementById('enrollStudentUsername').value;
            const assignmentId = parseInt(document.getElementById('enrollAssignmentId').value);
            if (!assignmentId) { showToast('Selecciona una asignacion', true); return; }
            try {
                const res = await fetch('/admin/enrollments', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, assignment_id: assignmentId })
                });
                if (res.ok) {
                    const data = await res.json();
                    const msg = data.reassigned
                        ? `${username} reasignado al nuevo docente`
                        : `${username} inscrito exitosamente`;
                    showToast(msg);
                    bootstrap.Modal.getInstance(document.getElementById('enrollStudentModal')).hide();
                    openViewStudent(username);
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Error al inscribir', true);
                }
            } catch (e) { showToast('Error de conexion', true); }
        }

        function openAssignAdvisorModal(username) {
            document.getElementById('advisorStudentUsername').value = username;
            document.getElementById('advisorStudentUsernameView').value = username;
            document.getElementById('advisorPeriodLabel').value = '';
            document.getElementById('advisorNotes').value = '';
            const teacherSelect = document.getElementById('advisorTeacherUsername');
            teacherSelect.innerHTML = '<option value="">Selecciona docente...</option>' + (allTeachers || []).map(t => `
                <option value="${t.username}">${t.full_name || t.username} (${t.username})</option>
            `).join('');
            bootstrap.Modal.getOrCreateInstance(document.getElementById('assignAdvisorModal')).show();
        }

        async function saveAdvisorAssignment() {
            const username = document.getElementById('advisorStudentUsername')?.value || '';
            const teacherUsername = document.getElementById('advisorTeacherUsername')?.value || '';
            const periodLabel = document.getElementById('advisorPeriodLabel')?.value?.trim() || '';
            const notes = document.getElementById('advisorNotes')?.value?.trim() || '';
            if (!username || !teacherUsername || !periodLabel) {
                showToast('Selecciona docente y periodo para asignar asesoría', true);
                return;
            }
            try {
                const response = await fetch(`/admin/students/${encodeURIComponent(username)}/advisor`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        teacher_username: teacherUsername,
                        period_label: periodLabel,
                        notes
                    })
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo asignar asesor virtual'), true);
                    return;
                }
                bootstrap.Modal.getInstance(document.getElementById('assignAdvisorModal'))?.hide();
                showToast('Asesor virtual asignado correctamente');
                await openViewStudent(username);
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al asignar asesor', true);
            }
        }

        function getSemesterSortValue(label) {
            const text = String(label || '').trim();
            const match = text.match(/\d+/);
            if (match) return parseInt(match[0], 10);
            if (text.toLowerCase() === 'especial') return 999;
            return Number.MAX_SAFE_INTEGER;
        }

        function getSemesterTheme(label) {
            const themes = [
                { bg: 'linear-gradient(135deg, #1d4ed8, #1e3a8a)', chip: 'rgba(255,255,255,0.16)' },
                { bg: 'linear-gradient(135deg, #0f766e, #115e59)', chip: 'rgba(255,255,255,0.16)' },
                { bg: 'linear-gradient(135deg, #7c3aed, #5b21b6)', chip: 'rgba(255,255,255,0.16)' },
                { bg: 'linear-gradient(135deg, #c2410c, #9a3412)', chip: 'rgba(255,255,255,0.16)' },
                { bg: 'linear-gradient(135deg, #be123c, #881337)', chip: 'rgba(255,255,255,0.16)' }
            ];
            const index = Math.max(0, getSemesterSortValue(label) - 1) % themes.length;
            return themes[index] || themes[0];
        }

        function formatAverageLabel(grades) {
            const scored = (grades || []).filter(g => g.score !== null && g.score !== undefined && Number(g.score) > 0);
            if (!scored.length) return 'Sin promedio';
            const total = scored.reduce((sum, g) => sum + Number(g.score), 0);
            return (total / scored.length).toFixed(1);
        }

        function getGradeCredits(g) {
            return Number(g.subject?.credits || g.subject_credits || 0);
        }

        function getTotalCredits(grades) {
            return (grades || []).reduce((sum, g) => sum + getGradeCredits(g), 0);
        }

        function getCompletedCredits(grades) {
            return (grades || []).reduce((sum, g) => {
                return sum + (g.status === 'Aprobada' ? getGradeCredits(g) : 0);
            }, 0);
        }

        function getInProgressCredits(grades) {
            return (grades || []).reduce((sum, g) => {
                return sum + (g.status === 'Cursando' ? getGradeCredits(g) : 0);
            }, 0);
        }

        function countGradesByStatus(grades) {
            return (grades || []).reduce((acc, g) => {
                if (g.status === 'Aprobada') acc.approved += 1;
                else if (g.status === 'Reprobada') acc.failed += 1;
                else acc.inProgress += 1;
                return acc;
            }, { approved: 0, failed: 0, inProgress: 0 });
        }

        function getProgressBarClass(progress) {
            if (progress >= 80) return 'bg-success';
            if (progress >= 50) return 'bg-info';
            if (progress >= 25) return 'bg-warning';
            return 'bg-danger';
        }

        function renderCurriculumSummary(grades) {
            const totalCredits = getTotalCredits(grades);
            const completedCredits = getCompletedCredits(grades);
            const inProgressCredits = getInProgressCredits(grades);
            const counters = countGradesByStatus(grades);
            const average = formatAverageLabel(grades);
            const progress = totalCredits > 0 ? Math.round((completedCredits / totalCredits) * 100) : 0;
            const progressBarClass = getProgressBarClass(progress);
            const statCards = [
                { icon: 'bi-graph-up-arrow', label: 'Promedio general', value: average, tone: 'rgba(255,255,255,0.16)' },
                { icon: 'bi-award-fill', label: 'Créditos completados', value: completedCredits, tone: 'rgba(34,197,94,0.24)' },
                { icon: 'bi-hourglass-split', label: 'Créditos en curso', value: inProgressCredits, tone: 'rgba(250,204,21,0.24)' },
                { icon: 'bi-stack', label: 'Créditos totales', value: totalCredits, tone: 'rgba(96,165,250,0.24)' },
                { icon: 'bi-check-circle-fill', label: 'Aprobadas', value: counters.approved, tone: 'rgba(34,197,94,0.24)' },
                { icon: 'bi-x-circle-fill', label: 'Reprobadas', value: counters.failed, tone: 'rgba(248,113,113,0.24)' },
                { icon: 'bi-journal-bookmark-fill', label: 'Cursando', value: counters.inProgress, tone: 'rgba(250,204,21,0.24)' },
                { icon: 'bi-bar-chart-fill', label: 'Avance total', value: `${progress}%`, tone: 'rgba(255,255,255,0.16)' }
            ];
            return `
                <div class="rounded-4 overflow-hidden shadow-sm border mb-4">
                    <div class="p-4 text-white" style="background: linear-gradient(135deg, #0f172a, #1d4ed8 55%, #d81b60);">
                        <div class="d-flex flex-wrap justify-content-between align-items-center gap-3 mb-3">
                            <div>
                                <div class="text-uppercase small fw-bold opacity-75 mb-1">Resumen acumulado</div>
                                <h5 class="fw-bold mb-0">Avance general de la currícula</h5>
                            </div>
                            <span class="badge rounded-pill px-3 py-2 bg-light text-dark"><i class="bi bi-stars me-2"></i>Vista ejecutiva</span>
                        </div>
                        <div class="row g-3 mb-4">
                            ${statCards.map(card => `
                                <div class="col-12 col-sm-6 col-xl-3">
                                    <div class="h-100 rounded-4 p-3 border border-light border-opacity-25" style="background:${card.tone}; -webkit-backdrop-filter: blur(4px); backdrop-filter: blur(4px);">
                                        <div class="d-flex align-items-start justify-content-between gap-3">
                                            <div>
                                                <div class="text-uppercase small fw-semibold opacity-75 mb-1">${card.label}</div>
                                                <div class="fs-4 fw-bold lh-1">${card.value}</div>
                                            </div>
                                            <div class="rounded-circle d-inline-flex align-items-center justify-content-center" style="width:44px; height:44px; background:rgba(255,255,255,0.16);">
                                                <i class="bi ${card.icon} fs-5"></i>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        <div class="d-flex justify-content-between align-items-center small fw-semibold opacity-75 mb-2">
                            <span><i class="bi bi-flag-fill me-2"></i>Progreso por créditos aprobados</span>
                            <span>${completedCredits} de ${totalCredits} créditos</span>
                        </div>
                        <div class="progress" style="height: 14px; background: rgba(255,255,255,0.18); border-radius: 999px;">
                            <div class="progress-bar ${progressBarClass}" role="progressbar" style="width: ${progress}%;" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100"></div>
                        </div>
                    </div>
                </div>
            `;
        }

        function groupGradesBySemester(grades) {
            const grouped = {};
            (grades || []).forEach(g => {
                const period = (g.subject && g.subject.semester) ? g.subject.semester
                    : (g.subject_semester || 'Sin Periodo');
                if (!grouped[period]) grouped[period] = [];
                grouped[period].push(g);
            });
            return Object.entries(grouped).sort((a, b) => getSemesterSortValue(a[0]) - getSemesterSortValue(b[0]));
        }

        function renderStudentGradeGroups(groups) {
            return groups.map(([period, grades]) => {
                const theme = getSemesterTheme(period);
                const average = formatAverageLabel(grades);
                const totalCredits = getTotalCredits(grades);
                return `
                <div class="mb-4 rounded-4 overflow-hidden border shadow-sm">
                    <div class="p-3 p-md-4 text-white" style="background: ${theme.bg};">
                        <div class="d-flex flex-wrap align-items-center justify-content-between gap-3">
                            <div>
                                <div class="text-uppercase small fw-bold opacity-75 mb-1">Trayecto academico</div>
                                <h5 class="fw-bold mb-0">Periodo ${period}</h5>
                            </div>
                            <div class="d-flex flex-wrap gap-2">
                                <span class="badge rounded-pill px-3 py-2" style="background:${theme.chip}; color:#fff;">${grades.length} materias</span>
                                <span class="badge rounded-pill px-3 py-2" style="background:${theme.chip}; color:#fff;">${totalCredits} creditos</span>
                                <span class="badge rounded-pill px-3 py-2" style="background:${theme.chip}; color:#fff;">Promedio ${average}</span>
                            </div>
                        </div>
                    </div>
                    <div class="table-responsive bg-white">
                        <table class="table table-hover align-middle mb-0 small">
                            <thead class="table-light">
                                <tr>
                                    <th>Materia</th>
                                    <th>Crd.</th>
                                    <th>Docente</th>
                                    <th>Ciclo</th>
                                    <th>Calif.</th>
                                    <th>Tipo</th>
                                    <th>Estatus</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                ${grades.map(g => {
                                    const subjectName = g.subject ? g.subject.name : (g.subject_name || 'Materia Desconocida');
                                    const credits = g.subject && g.subject.credits ? g.subject.credits : (g.subject_credits || '-');
                                    const teacher = g.teacher || '<span class="text-muted">?</span>';
                                    const cycle = g.cycle || '?';
                                    const scoreVal = g.score !== null && g.score !== undefined ? g.score : null;
                                    const isApproved = scoreVal !== null && scoreVal >= 6;
                                    const scoreTxt = scoreVal !== null ? scoreVal : '?';
                                    const scoreClass = scoreVal !== null ? (isApproved ? 'text-success fw-bold' : 'text-danger fw-bold') : 'text-muted';
                                    const statusBadge = g.status === 'Aprobada' ? 'bg-success'
                                        : g.status === 'Reprobada'       ? 'bg-danger'
                                        : g.status === 'Proximamente'    ? 'bg-info text-dark'
                                        : g.status === 'Sin calificacion'? 'bg-secondary'
                                        : 'bg-warning text-dark';
                                    const attemptBadge = g.attempt_type === 'Extemporaneo' ? '<span class="badge bg-warning text-dark">Extemp.</span>' : '<span class="badge bg-secondary">Regular</span>';
                                    return `
                                        <tr>
                                            <td class="fw-medium">${subjectName}</td>
                                            <td>${credits}</td>
                                            <td>${teacher}</td>
                                            <td class="text-muted">${cycle}</td>
                                            <td class="${scoreClass}">${scoreTxt}</td>
                                            <td>${attemptBadge}</td>
                                            <td><span class="badge ${statusBadge}">${g.status}</span></td>
                                            <td>
                                                <button class="btn btn-sm btn-light rounded-pill" title="Editar calificacion" onclick="openEditGrade(${g.id}, ${scoreVal !== null ? scoreVal : 'null'})"><i class="bi bi-pencil"></i></button>
                                            </td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;}).join('');
        }

        function renderHistoryGrades() {
            const container = document.getElementById('viewStudentHistoryGrades');
            const pagination = document.getElementById('viewStudentGradesPagination');
            const grades = window.currentStudentHistoryGrades || [];
            
            if (grades.length === 0) {
                container.innerHTML = '<div class="alert alert-light text-center mb-0 py-3 text-muted">No hay historial académico.</div>';
                if (pagination) pagination.innerHTML = '';
                return;
            }

            container.innerHTML = renderStudentGradeGroups(groupGradesBySemester(grades));
            if (pagination) pagination.innerHTML = '';
        }

        function changeHistoryPage(page) {
            // Funcion mantenida por compatibilidad pero ya no se usa
        }

        async function downloadBoleta() {
            const username = document.getElementById('viewStudentUsername').textContent.trim();
            if (!username) { showToast('No se identifico el alumno', 'warning'); return; }
            showToast('Generando boleta PDF...', 'info');
            try {
                const res = await fetch(`/admin/students/${encodeURIComponent(username)}/boleta`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) { showToast('Error al generar la boleta', 'danger'); return; }
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `boleta_${username}.pdf`;
                a.click();
                URL.revokeObjectURL(url);
                showToast('Boleta descargada correctamente', 'success');
            } catch (e) {
                showToast('Error de conexion al generar boleta', 'danger');
            }
        }

        async function saveGrade() {
            const id = document.getElementById('editGradeId').value;
            const score = document.getElementById('editGradeScore').value;
            const manualStatus = document.getElementById('editGradeStatus').value;

            const payload = {};
            if (score !== '') {
                payload.score = parseFloat(score);
            } else if (manualStatus) {
                payload.status = manualStatus;
            }

            if (!('score' in payload) && !payload.status) {
                showToast('Ingresa una calificacion o selecciona un estatus', true);
                return;
            }

            try {
                const response = await fetch(`/admin/grades/${id}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    showToast('Calificacion actualizada');
                    bootstrap.Modal.getInstance(document.getElementById('editGradeModal')).hide();
                    openViewStudent(document.getElementById('viewStudentUsername').textContent);
                } else {
                    showToast('Error al actualizar', true);
                }
            } catch (e) {
                showToast('Error de conexion', true);
            }
        }

        function openEditPayment(id, status) {
            document.getElementById('editPaymentId').value = id;
            document.getElementById('editPaymentStatus').value = status;
            new bootstrap.Modal(document.getElementById('editPaymentModal')).show();
        }

        async function savePayment() {
            const id = document.getElementById('editPaymentId').value;
            const status = document.getElementById('editPaymentStatus').value;

            try {
                const response = await fetch(`/admin/payments/${id}`, {
                    method: 'PUT',
                    headers: { 
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ status: status })
                });

                if (response.ok) {
                    showToast('Pago actualizado');
                    bootstrap.Modal.getInstance(document.getElementById('editPaymentModal')).hide();
                    openViewStudent(document.getElementById('viewStudentUsername').textContent);
                } else {
                    showToast('Error al actualizar', true);
                }
            } catch (e) {
                showToast('Error de conexion', true);
            }
        }

        function openEditService(id, status) {
            document.getElementById('editServiceId').value = id;
            document.getElementById('editServiceStatus').value = status;
            new bootstrap.Modal(document.getElementById('editServiceModal')).show();
        }

        async function saveService() {
            const id = document.getElementById('editServiceId').value;
            const status = document.getElementById('editServiceStatus').value;

            try {
                const response = await fetch(`/admin/services/${id}`, {
                    method: 'PUT',
                    headers: { 
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ status: status })
                });

                if (response.ok) {
                    showToast('Tramite actualizado');
                    bootstrap.Modal.getInstance(document.getElementById('editServiceModal')).hide();
                    openViewStudent(document.getElementById('viewStudentUsername').textContent);
                } else {
                    showToast('Error al actualizar', true);
                }
            } catch (e) {
                showToast('Error de conexion', true);
            }
        }

        function openEditTeacher(username) {
            const teacher = allTeachers.find(t => t.username === username);
            if (teacher) {
                document.getElementById('editTeacherUsername').value = teacher.username;
                document.getElementById('editTeacherName').value = teacher.full_name || '';
                document.getElementById('editTeacherEmail').value = teacher.email || '';
                document.getElementById('editTeacherPassword').value = '';
                
                const modal = new bootstrap.Modal(document.getElementById('editTeacherModal'));
                modal.show();
            }
        }

        async function updateTeacher(event) {
            event.preventDefault();
            const username = document.getElementById('editTeacherUsername').value;
            
            const updateData = {
                full_name: document.getElementById('editTeacherName').value,
                email: document.getElementById('editTeacherEmail').value
            };

            const password = document.getElementById('editTeacherPassword').value;
            if (password) {
                updateData.password = password;
            }

            try {
                const response = await fetch(`/admin/teachers/${username}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    showToast('Docente actualizado exitosamente', 'success');
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editTeacherModal'));
                    modal.hide();
                    loadAdminData(); // Recargar lista
                } else {
                    const error = await response.json();
                    showToast(error.detail || 'Error al actualizar docente', 'danger');
                }
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        // ? Ciclos y Pagos ?

        async function loadCyclesPaymentTable() {
            try {
                const res = await fetch('/admin/school-cycles/all', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) return;
                const cycles = await res.json();
                const container = document.getElementById('cyclesPaymentTable');
                if (!container) return;
                if (!cycles || cycles.length === 0) {
                    container.innerHTML = '<p class="text-muted small">No hay ciclos registrados.</p>';
                    return;
                }
                let html = '<div class="table-responsive"><table class="table table-sm table-hover align-middle"><thead class="table-light"><tr>';
                html += '<th>Periodo</th><th>Inicio</th><th>Fin</th><th>Monto Mensual</th><th>Meses</th><th>Pagos</th><th>Activo</th></tr></thead><tbody>';
                cycles.forEach(c => {
                    const months = [];
                    if (c.start_date && c.end_date) {
                        let cur = new Date(c.start_date + 'T00:00:00');
                        const end = new Date(c.end_date + 'T00:00:00');
                        while (cur <= end) {
                            months.push(cur.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' }));
                            cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
                        }
                    }
                    const activeBadge = c.is_active
                        ? '<span class="badge bg-success">Activo</span>'
                        : '<span class="badge bg-secondary">Inactivo</span>';
                    const amount = c.monthly_amount !== null && c.monthly_amount !== undefined ? `$${parseFloat(c.monthly_amount).toFixed(2)}` : '?';
                    html += `<tr>
                        <td class="fw-bold">${c.period || '?'}</td>
                        <td>${c.start_date || '?'}</td>
                        <td>${c.end_date || '?'}</td>
                        <td>${amount}</td>
                        <td><small class="text-muted">${months.join(', ') || '?'}</small></td>
                        <td><span class="badge bg-info text-dark rounded-pill">${c.payment_count ?? 0}</span></td>
                        <td>${activeBadge}</td>
                    </tr>`;
                });
                html += '</tbody></table></div>';
                container.innerHTML = html;
            } catch (e) { /* silencioso */ }
        }

        async function generateCyclePayments() {
            if (!confirm('¿Generar los pagos del ciclo activo para TODOS los alumnos inscritos? Esto puede tardar unos segundos.')) return;
            try {
                const res = await fetch('/admin/school-cycle/generate-payments', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    const data = await res.json();
                    showToast(`Pagos generados: ${data.payments_created || 0} nuevos registros`);
                    loadAdminData();
                } else {
                    const err = await res.json();
                    showToast(err.detail || 'Error al generar pagos', true);
                }
            } catch (e) { showToast('Error de conexion', true); }
        }

        // ======= Asignaciones de Docentes =============================================
