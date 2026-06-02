        async function loadAdminData() {
            try {
                // Verificar que sea admin
                const userResponse = await fetch('/users/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (userResponse.ok) {
                    const userData = await userResponse.json();
                    if (userData.role !== 'admin') {
                        window.location.href = 'campus-virtual.html';
                        return;
                    }
                    document.getElementById('adminName').textContent = userData.full_name;
                } else {
                    logout();
                    return;
                }

                await loadCatalogs();

                // Cargar estadisticas
                const statsResponse = await fetch('/admin/stats', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    document.getElementById('totalStudentsCount').textContent = stats.total_students;
                    document.getElementById('totalIncomeCount').textContent = `$${(stats.total_income / 1000).toFixed(1)}k`;
                    document.getElementById('pendingServicesCount').textContent = stats.pending_services;
                    document.getElementById('totalTeachersCount').textContent = stats.total_teachers;
                }

                // Cargar alumnos
                const studentsResponse = await fetch('/admin/students', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (studentsResponse.ok) {
                    allStudents = await studentsResponse.json();
                }

                const studentEnrollmentsResponse = await fetch('/admin/student-enrollments', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (studentEnrollmentsResponse.ok) {
                    allStudentEnrollments = await studentEnrollmentsResponse.json();
                }

                syncStudentsWithActiveEnrollments();
                syncCatalogsFromStudents();
                populateGroupFilter();
                filteredStudents = [...allStudents];
                filteredStudentEnrollments = [...allStudentEnrollments];
                renderStudents(filteredStudents);
                renderPagination();

                // Cargar docentes
                const teachersResponse = await fetch('/admin/teachers', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (teachersResponse.ok) {
                    allTeachers = await teachersResponse.json();
                    filteredTeachers = [...allTeachers];
                    renderTeachers(filteredTeachers);
                }

                // Cargar materias
                const subjectsResponse = await fetch('/admin/subjects', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (subjectsResponse.ok) {
                    allSubjects = await subjectsResponse.json();
                    filteredSubjects = [...allSubjects];
                    renderSubjects(filteredSubjects);
                }

                const chargesResponse = await fetch('/admin/charges', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (chargesResponse.ok) {
                    allCharges = await chargesResponse.json();
                    filteredCharges = [...allCharges];
                    renderCharges(filteredCharges);
                }

                // Cargar tramites
                const servicesResponse = await fetch('/admin/services', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });

                if (servicesResponse.ok) {
                    allServices = await servicesResponse.json();
                    filteredServices = [...allServices];
                    renderServices(filteredServices);
                }

                // Generar reportes con los datos cargados
                generateCharts();
                calculateAcademicStats();
                updateOfferSummary();
                await loadReportFilterOptions();
                await loadControlSchoolData();
                await loadTreasuryView();
                await loadGradeCenter();
                await loadReportsDashboard();
                await loadAdminNotifications(false);
            } catch (error) {
                console.error("Error loading admin data:", error);
            }
        }

        function populateGroupFilter() {
            const select = document.getElementById('filterGroup');
            const current = select.value;
            const groups = [...new Set(allStudents.map(s => s.grupo).filter(Boolean))].sort();
            select.innerHTML = '<option value="">Todos los grupos</option>';
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.textContent = `Grupo ${g}`;
                select.appendChild(opt);
            });
            select.value = current;
        }

        function filterStudents() {
            const search = document.getElementById('filterSearch').value.toLowerCase();
            const careerId = document.getElementById('filterCareer').value;
            const grupo = document.getElementById('filterGroup').value;
            const statusVal = document.getElementById('filterStatus').value;

            filteredStudents = allStudents.filter(s => {
                const matchSearch = !search ||
                    (s.full_name && s.full_name.toLowerCase().includes(search)) ||
                    (s.username && s.username.toLowerCase().includes(search));
                const matchCareer = !careerId || (s.carrera || '') === careerId;
                const matchGroup = !grupo || (s.grupo || '') === grupo;
                let matchStatus = true;
                if (statusVal.startsWith('cuenta:')) {
                    matchStatus = (s.user_status || 'Activo') === statusVal.replace('cuenta:', '');
                } else if (statusVal.startsWith('inscripcion:')) {
                    matchStatus = (s.enrollment_status || 'No Inscrito') === statusVal.replace('inscripcion:', '');
                }
                return matchSearch && matchCareer && matchGroup && matchStatus;
            });

            currentPage = 1;
            renderStudents(filteredStudents);
            renderPagination();
        }

        function filterTeachers() {
            const search = document.getElementById('filterTeacherSearch').value.toLowerCase();
            filteredTeachers = allTeachers.filter(t => {
                return (t.full_name && t.full_name.toLowerCase().includes(search)) ||
                       (t.username && t.username.toLowerCase().includes(search));
            });
            teachersPage = 1;
            renderTeachers(filteredTeachers);
        }

        function filterSubjects() {
            const search = document.getElementById('filterSubjectSearch').value.toLowerCase();
            const career = document.getElementById('filterSubjectCareer').value;
            filteredSubjects = allSubjects.filter(s => {
                const matchSearch = s.name.toLowerCase().includes(search);
                const matchCareer = career === "" || s.career === career;
                return matchSearch && matchCareer;
            });
            subjectsPage = 1;
            renderSubjects(filteredSubjects);
        }

        function filterCharges() {
            const search = (document.getElementById('filterChargeSearch')?.value || '').toLowerCase();
            const status = document.getElementById('filterPaymentStatus').value;
            filteredCharges = allCharges.filter(c => {
                const studentName = c.student?.full_name?.toLowerCase() || '';
                const studentUsername = c.student?.username?.toLowerCase() || '';
                const concept = (c.concept || '').toLowerCase();
                const period = (c.period_label || '').toLowerCase();
                const matchSearch = !search || studentName.includes(search) || studentUsername.includes(search) || concept.includes(search) || period.includes(search);
                const matchStatus = status === "" || c.status === status;
                return matchSearch && matchStatus;
            });
            chargesPage = 1;
            renderCharges(filteredCharges);
        }

        function filterServices() {
            const search   = document.getElementById('filterServiceSearch')?.value.toLowerCase() || '';
            const status   = document.getElementById('filterServiceStatus')?.value || '';
            const type     = document.getElementById('filterServiceType')?.value || '';
            const fromVal  = document.getElementById('filterServiceFrom')?.value || '';
            const toVal    = document.getElementById('filterServiceTo')?.value || '';
            const fromDate = fromVal ? new Date(fromVal) : null;
            const toDate   = toVal   ? new Date(toVal + 'T23:59:59') : null;

            filteredServices = allServices.filter(s => {
                const name    = (s.student?.full_name || '').toLowerCase();
                const uname   = (s.student?.username  || '').toLowerCase();
                const stype   = (s.type || '').toLowerCase();
                const sDate   = s.request_date ? new Date(s.request_date) : null;

                const matchSearch = !search || name.includes(search) || uname.includes(search) || stype.includes(search);
                const matchStatus = !status || s.status === status;
                const matchType   = !type   || s.type === type;
                const matchFrom   = !fromDate || (sDate && sDate >= fromDate);
                const matchTo     = !toDate   || (sDate && sDate <= toDate);

                return matchSearch && matchStatus && matchType && matchFrom && matchTo;
            });
            servicesPage = 1;
            renderServices(filteredServices);
        }

        function setTodayDateInputValue(inputId) {
            const input = document.getElementById(inputId);
            if (!input) return;
            input.value = new Date().toISOString().split('T')[0];
        }

        function renderServiceStudentPicker(students) {
            const picker = document.getElementById('serviceStudentPicker');
            const datalist = document.getElementById('serviceStudentOptions');
            if (!picker || !datalist) return;

            datalist.innerHTML = allStudents.map(student =>
                `<option value="${escHtml(student.username)}">${escHtml(student.full_name || student.username)}</option>`
            ).join('');

            if (!students.length) {
                picker.innerHTML = '<div class="list-group-item text-muted small">No se encontraron alumnos.</div>';
                return;
            }

            picker.innerHTML = students.slice(0, 20).map(student => `
                <button type="button" class="list-group-item list-group-item-action" onclick="selectServiceStudent('${escHtml(student.username)}')">
                    <div class="fw-semibold">${escHtml(student.username)}</div>
                    <div class="small text-muted">${escHtml(student.full_name || 'Sin nombre')}</div>
                </button>
            `).join('');
        }

        function selectServiceStudent(username) {
            const input = document.getElementById('newServiceStudent');
            const selectedLabel = document.getElementById('selectedServiceStudent');
            if (input) input.value = username;
            const student = allStudents.find(item => item.username === username);
            if (selectedLabel) {
                selectedLabel.textContent = student
                    ? `${student.full_name || 'Sin nombre'} · ${student.carrera || 'Sin carrera'}`
                    : '';
            }
        }

        function filterServiceStudentPicker() {
            const query = (document.getElementById('newServiceStudent')?.value || '').toLowerCase().trim();
            const filtered = allStudents.filter(student => {
                const username = (student.username || '').toLowerCase();
                const fullName = (student.full_name || '').toLowerCase();
                return !query || username.includes(query) || fullName.includes(query);
            });
            renderServiceStudentPicker(filtered);
            if (query) {
                const exact = allStudents.find(student => (student.username || '').toLowerCase() === query);
                if (exact) selectServiceStudent(exact.username);
            }
        }

        function svcBadge(status) {
            const map = {
                'En Proceso': 'bg-warning text-dark',
                'Listo':      'bg-info text-dark',
                'Entregado':  'bg-success',
            };
            return `<span class="badge ${map[status] || 'bg-secondary'} rounded-pill px-3">${status}</span>`;
        }

        function renderServicesStats(services) {
            document.getElementById('svcStatTotal').textContent     = services.length;
            document.getElementById('svcStatProceso').textContent   = services.filter(s => s.status === 'En Proceso').length;
            document.getElementById('svcStatListo').textContent     = services.filter(s => s.status === 'Listo').length;
            document.getElementById('svcStatEntregado').textContent = services.filter(s => s.status === 'Entregado').length;
        }

        function renderServices(services) {
            const table = document.getElementById('allServicesTableBody');
            if (!table) return;
            renderServicesStats(allServices);
            if (!services.length) {
                table.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No hay trámites que coincidan con los filtros.</td></tr>';
                buildTablePagination('services-pagination', 'services-info', 1, 0, TABLE_PER_PAGE, 'changeServicesPage');
                return;
            }
            const start = (servicesPage - 1) * TABLE_PER_PAGE;
            const page  = services.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(s => {
                const fecha    = new Date(s.request_date).toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: 'numeric' });
                const username = escHtml(s.student?.username || 'N/A');
                const fullName = escHtml(s.student?.full_name || 'Desconocido');
                const type     = escHtml(s.type || '—');
                return `<tr>
                    <td class="text-muted small">${s.id}</td>
                    <td><div class="fw-bold text-primary">${username}</div><div class="small text-muted">${fullName}</div></td>
                    <td>${type}</td>
                    <td class="small">${fecha}</td>
                    <td>
                        <div class="dropdown d-inline">
                            <span class="badge-clickable" data-bs-toggle="dropdown" style="cursor:pointer;" title="Cambiar estatus">${svcBadge(s.status)}</span>
                            <ul class="dropdown-menu dropdown-menu-sm shadow-sm">
                                <li><h6 class="dropdown-header small">Cambiar estatus</h6></li>
                                <li><a class="dropdown-item small" href="#" onclick="quickUpdateServiceStatus(${s.id},'En Proceso');return false;">${svcBadge('En Proceso')}</a></li>
                                <li><a class="dropdown-item small" href="#" onclick="quickUpdateServiceStatus(${s.id},'Listo');return false;">${svcBadge('Listo')}</a></li>
                                <li><a class="dropdown-item small" href="#" onclick="quickUpdateServiceStatus(${s.id},'Entregado');return false;">${svcBadge('Entregado')}</a></li>
                            </ul>
                        </div>
                    </td>
                    <td>${s.attachment_filename ? `<button class="btn btn-sm btn-outline-primary rounded-pill" onclick="downloadAdminServiceAttachment(${s.id})" title="${escHtml(s.attachment_filename)}"><i class="bi bi-paperclip me-1"></i>Ver</button>` : '<span class="text-muted small">—</span>'}</td>
                    <td class="text-nowrap">
                        <button class="btn btn-sm btn-outline-secondary rounded-pill me-1" title="Editar" onclick="openEditGlobalService(${s.id})"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-danger rounded-pill" title="Eliminar" onclick="confirmDeleteService(${s.id})"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>`;
            }).join('');
            buildTablePagination('services-pagination', 'services-info', servicesPage, services.length, TABLE_PER_PAGE, 'changeServicesPage');
        }

        async function quickUpdateServiceStatus(serviceId, newStatus) {
            try {
                const res = await fetch(`/admin/services/${serviceId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });
                if (!res.ok) { showToast('Error al actualizar estatus', 'danger'); return; }
                const idx = allServices.findIndex(s => s.id === serviceId);
                if (idx !== -1) allServices[idx].status = newStatus;
                filterServices();
                showToast(`Estatus cambiado a "${newStatus}"`, 'success');
            } catch { showToast('Error de conexión', 'danger'); }
        }

        function confirmDeleteService(serviceId) {
            const svc = allServices.find(s => s.id === serviceId);
            if (!confirm(`¿Eliminar el trámite #${serviceId} (${svc?.type || ''}) de ${svc?.student?.username || ''}? Esta acción no se puede deshacer.`)) return;
            doDeleteService(serviceId);
        }

        async function doDeleteService(serviceId) {
            try {
                const res = await fetch(`/admin/services/${serviceId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok && res.status !== 204) { showToast('Error al eliminar trámite', 'danger'); return; }
                allServices = allServices.filter(s => s.id !== serviceId);
                filterServices();
                showToast(`Trámite #${serviceId} eliminado`, 'success');
            } catch { showToast('Error de conexión', 'danger'); }
        }

        async function reloadServices() {
            try {
                const res = await fetch('/admin/services', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (res.ok) {
                    allServices = await res.json();
                    filteredServices = [...allServices];
                    filterServices();
                }
            } catch { showToast('Error al recargar trámites', 'danger'); }
        }

        function clearServiceFilters() {
            document.getElementById('filterServiceSearch').value = '';
            document.getElementById('filterServiceType').value   = '';
            document.getElementById('filterServiceStatus').value = '';
            document.getElementById('filterServiceFrom').value   = '';
            document.getElementById('filterServiceTo').value     = '';
            filterServices();
        }

        async function downloadAdminServiceAttachment(serviceId) {
            try {
                const response = await fetch(`/admin/services/${serviceId}/attachment`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const error = await response.json();
                    showToast(error.detail || 'No se pudo descargar el adjunto', 'danger');
                    return;
                }
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `tramite_${serviceId}`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
            } catch (error) {
                showToast('Error de conexion', 'danger');
            }
        }

        function renderCharges(charges) {
            const table = document.getElementById('allChargesTableBody');
            if (!table) return;
            if (charges.length === 0) {
                table.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">No hay cargos registrados.</td></tr>';
                buildTablePagination('charges-pagination', 'charges-info', 1, 0, TABLE_PER_PAGE, 'changeChargesPage');
                return;
            }
            const start = (chargesPage - 1) * TABLE_PER_PAGE;
            const page  = charges.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(c => `
                <tr>
                    <td class="fw-bold">${c.id}</td>
                    <td>
                        <div class="fw-bold">${escHtml(c.student?.username || 'N/A')}</div>
                        <div class="small text-muted">${escHtml(c.student?.full_name || 'Desconocido')}</div>
                    </td>
                    <td>${escHtml(c.charge_type || 'Otro')}</td>
                    <td>${escHtml(c.concept || '?')}</td>
                    <td>${formatMoney(c.amount)}</td>
                    <td>${escHtml(c.period_label || '?')}</td>
                    <td>${formatDateShort(c.due_date)}</td>
                    <td>${renderPaymentStatusBadge(c.status)}</td>
                    <td>
                        <button class="btn btn-sm btn-light" title="Editar" onclick="openEditGlobalPayment(${c.id})"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-danger ms-1" title="Eliminar pago" onclick="deleteGlobalPayment(${c.id})"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>
            `).join('');
            buildTablePagination('charges-pagination', 'charges-info', chargesPage, charges.length, TABLE_PER_PAGE, 'changeChargesPage');
        }

        function updateOfferSummary() {
            const subjectsCount = document.getElementById('offerSubjectsCount');
            const teachersCount = document.getElementById('offerTeachersCount');
            const assignmentsCount = document.getElementById('offerAssignmentsCount');
            if (subjectsCount) subjectsCount.textContent = allSubjects.length;
            if (teachersCount) teachersCount.textContent = allTeachers.length;
            if (assignmentsCount) assignmentsCount.textContent = allAssignments.length;
        }

        function getReportFilters() {
            return {
                cycle_id: document.getElementById('reportFilterCycle')?.value || '',
                career: document.getElementById('reportFilterCareer')?.value || '',
                modality: document.getElementById('reportFilterModality')?.value || '',
                semester: document.getElementById('reportFilterSemester')?.value || '',
                group_name: document.getElementById('reportFilterGroup')?.value || '',
                date_from: document.getElementById('reportFilterDateFrom')?.value || '',
                date_to: document.getElementById('reportFilterDateTo')?.value || ''
            };
        }

        function buildQueryParams(filters) {
            const params = new URLSearchParams();
            Object.entries(filters).forEach(([key, value]) => {
                if (value !== '' && value !== null && value !== undefined) {
                    params.set(key, value);
                }
            });
            return params.toString();
        }

        function setChartPlaceholder(placeholderId, canvasId, message, type = 'muted') {
            const placeholder = document.getElementById(placeholderId);
            const canvas = document.getElementById(canvasId);
            if (!placeholder || !canvas) return;
            placeholder.className = `text-center text-${type}`;
            placeholder.innerHTML = `<i class="bi bi-bar-chart fs-1 d-block mb-2"></i>${escHtml(message)}`;
            placeholder.style.display = 'block';
            canvas.style.display = 'none';
        }

        function setReportDashboardLoading() {
            const loadingMap = [
                ['reportEnrollmentStatusTable', 2],
                ['reportTeacherWorkloadTable', 4],
                ['reportAcademicRiskTable', 5],
                ['reportServiceSummaryTable', 3],
                ['reportGradeOutcomesTable', 5],
                ['reportChargeBreakdownTable', 4]
            ];
            loadingMap.forEach(([id, cols]) => {
                const table = document.getElementById(id);
                if (table) table.innerHTML = `<tr><td colspan="${cols}" class="text-center py-4 text-muted">Cargando...</td></tr>`;
            });
            const overviewIds = [
                'reportOverviewStudents',
                'reportOverviewAverage',
                'reportOverviewApproval',
                'reportOverviewOverdue',
                'reportAvgGpa',
                'reportApprovedRate',
                'reportFailedRate'
            ];
            overviewIds.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '...';
            });
            setChartPlaceholder('chartCareerPlaceholder', 'careerChart', 'Cargando datos...');
            setChartPlaceholder('chartPaymentPlaceholder', 'paymentChart', 'Cargando datos...');
        }

        async function fetchJsonReport(url) {
            const response = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
            if (!response.ok) {
                return { ok: false, status: response.status, data: null };
            }
            return { ok: true, status: response.status, data: await response.json() };
        }

        async function loadReportFilterOptions() {
            const cycleSelect = document.getElementById('reportFilterCycle');
            const careerSelect = document.getElementById('reportFilterCareer');
            const modalitySelect = document.getElementById('reportFilterModality');
            const semesterSelect = document.getElementById('reportFilterSemester');
            const groupSelect = document.getElementById('reportFilterGroup');
            if (!cycleSelect) return;

            try {
                const cyclesRes = await fetch('/admin/school-cycles/all', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (cyclesRes.ok) {
                    const cycles = await cyclesRes.json();
                    const current = cycleSelect.value;
                    cycleSelect.innerHTML = '<option value="">Ciclo activo</option>' +
                        cycles.map(c => `<option value="${c.id}">${escHtml(c.period || `Ciclo ${c.id}`)}</option>`).join('');
                    cycleSelect.value = current;
                }
            } catch (error) {
                console.error('Error loading report cycles', error);
            }

            if (careerSelect) {
                const current = careerSelect.value;
                careerSelect.innerHTML = '<option value="">Todas</option>' +
                    (catalogCareers.length ? catalogCareers : DEFAULT_CAREERS).map(c => `<option value="${escHtml(c.name)}">${escHtml(c.name)}</option>`).join('');
                careerSelect.value = current;
            }
            if (modalitySelect) {
                const options = mergeCatalogData(catalogModalities, DEFAULT_MODALITIES);
                const current = modalitySelect.value;
                modalitySelect.innerHTML = '<option value="">Todas</option>' +
                    options.map(m => `<option value="${escHtml(m.name)}">${escHtml(m.name)}</option>`).join('');
                modalitySelect.value = current;
            }
            if (semesterSelect) {
                const current = semesterSelect.value;
                semesterSelect.innerHTML = '<option value="">Todos</option>' +
                    DEFAULT_STUDENT_SEMESTERS.map(item => `<option value="${escHtml(item.value)}">${escHtml(item.label)}</option>`).join('');
                semesterSelect.value = current;
            }
            if (groupSelect) {
                const current = groupSelect.value;
                const groups = [...new Set(allGroupSummaries.map(g => g.grupo).filter(Boolean))].sort();
                groupSelect.innerHTML = '<option value="">Todos</option>' +
                    groups.map(group => `<option value="${escHtml(group)}">${escHtml(group)}</option>`).join('');
                groupSelect.value = current;
            }
        }

        function resetReportFilters() {
            ['reportFilterCycle', 'reportFilterCareer', 'reportFilterModality', 'reportFilterSemester', 'reportFilterGroup', 'reportFilterDateFrom', 'reportFilterDateTo']
                .forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.value = '';
                });
            loadReportsDashboard();
        }

        async function loadControlSchoolData() {
            try {
                const [enrollmentsRes, auditRes, groupsRes] = await Promise.all([
                    fetch('/admin/student-enrollments', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/admin/migration-audit', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/admin/groups', { headers: { 'Authorization': `Bearer ${token}` } })
                ]);

                if (enrollmentsRes.ok) {
                    allStudentEnrollments = await enrollmentsRes.json();
                    syncStudentsWithActiveEnrollments();
                    filteredStudentEnrollments = [...allStudentEnrollments];
                    renderControlSchoolRows(filteredStudentEnrollments);
                    document.getElementById('controlEnrollmentCount').textContent = allStudentEnrollments.filter(e => e.is_active).length;
                }

                if (groupsRes.ok) {
                    allGroupSummaries = await groupsRes.json();
                    document.getElementById('controlGroupsCount').textContent = allGroupSummaries.length;
                }

                if (auditRes.ok) {
                    const audit = await auditRes.json();
                    document.getElementById('controlCycleLabel').textContent = audit.active_cycle_period || 'Sin ciclo';
                    document.getElementById('controlLegacyMissingCount').textContent = audit.legacy_students_missing_enrollment?.length || 0;
                    document.getElementById('controlAuditLegacyStudents').textContent = audit.legacy_students_with_seed_data || 0;
                    document.getElementById('controlAuditGroupMemberships').textContent = audit.active_cycle_group_memberships || 0;
                    document.getElementById('controlAuditOrphanGrades').textContent = audit.grades_without_course_enrollment || 0;
                    document.getElementById('controlAuditLinkedGrades').textContent = `Calificaciones enlazadas: ${audit.grades_linked_to_course_enrollment || 0}`;
                    const missingList = document.getElementById('controlAuditMissingList');
                    if (audit.legacy_students_missing_enrollment?.length) {
                        missingList.innerHTML = `
                            <div class="alert alert-warning mb-0">
                                <strong>Pendientes de migracion:</strong>
                                ${audit.legacy_students_missing_enrollment.map(username => `<span class="badge bg-dark me-1 mt-1">${escHtml(username)}</span>`).join('')}
                            </div>`;
                    } else {
                        missingList.innerHTML = '<p class="text-muted small mb-0">Sin pendientes detectados.</p>';
                    }
                }
            } catch (error) {
                console.error('Error loading control school data', error);
            }
        }

        function filterControlSchoolRows() {
            const search = (document.getElementById('controlEnrollmentSearch')?.value || '').toLowerCase();
            const status = document.getElementById('controlEnrollmentStatus')?.value || '';

            filteredStudentEnrollments = allStudentEnrollments.filter(enrollment => {
                const username = enrollment.student?.username?.toLowerCase() || '';
                const fullName = enrollment.student?.full_name?.toLowerCase() || '';
                const career = enrollment.career?.name?.toLowerCase() || '';
                const groupName = enrollment.group?.name?.toLowerCase() || '';
                const matchesSearch = !search || username.includes(search) || fullName.includes(search) || career.includes(search) || groupName.includes(search);
                const matchesStatus = !status || enrollment.enrollment_status === status;
                return matchesSearch && matchesStatus;
            });
            controlSchoolPage = 1;
            renderControlSchoolRows(filteredStudentEnrollments);
        }

        function renderControlSchoolRows(rows) {
            const table = document.getElementById('controlSchoolTableBody');
            if (!table) return;
            if (!rows.length) {
                table.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No hay expedientes en el ciclo activo.</td></tr>';
                buildTablePagination('control-school-pagination', 'control-school-info', 1, 0, TABLE_PER_PAGE, 'changeControlSchoolPage');
                return;
            }
            const start = (controlSchoolPage - 1) * TABLE_PER_PAGE;
            const page  = rows.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(enrollment => `
                <tr>
                    <td class="fw-bold">${escHtml(enrollment.student?.username || 'N/A')}</td>
                    <td>${escHtml(enrollment.student?.full_name || 'Sin nombre')}</td>
                    <td>${escHtml(enrollment.career?.name || 'Sin carrera')}</td>
                    <td>${escHtml(enrollment.modality?.name || 'Sin modalidad')}</td>
                    <td>${escHtml(enrollment.semester || '?')}</td>
                    <td>${escHtml(enrollment.group?.name || 'Sin grupo')}</td>
                    <td>${renderEnrollmentBadge(enrollment.enrollment_status || 'No Inscrito')}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openViewStudent('${escHtml(enrollment.student?.username || '')}')">
                            <i class="bi bi-eye"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
            buildTablePagination('control-school-pagination', 'control-school-info', controlSchoolPage, rows.length, TABLE_PER_PAGE, 'changeControlSchoolPage');
        }

        async function loadTreasuryView() {
            try {
                const [financeRes, blockedRes, chargesRes] = await Promise.all([
                    fetch('/admin/reports/finance-summary', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/admin/reports/blocked-students', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/admin/charges', { headers: { 'Authorization': `Bearer ${token}` } })
                ]);

                if (financeRes.ok) {
                    financeSummary = await financeRes.json();
                    document.getElementById('financeTotalCharges').textContent = financeSummary.total_charges || 0;
                    document.getElementById('financePaidAmount').textContent = formatMoney(financeSummary.paid_amount);
                    document.getElementById('financePendingAmount').textContent = formatMoney(financeSummary.pending_amount);
                    document.getElementById('financeOverdueAmount').textContent = formatMoney(financeSummary.overdue_amount);
                }

                if (blockedRes.ok) {
                    blockedStudents = await blockedRes.json();
                    renderBlockedStudents(blockedStudents);
                }

                if (chargesRes.ok) {
                    allCharges = await chargesRes.json();
                    filteredCharges = [...allCharges];
                    renderCharges(filteredCharges);
                }
            } catch (error) {
                console.error('Error loading treasury view', error);
            }
        }

        function renderBlockedStudents(rows) {
            const table = document.getElementById('blockedStudentsTableBody');
            if (!table) return;
            document.getElementById('blockedStudentsCount').textContent = `${rows.length} alumno${rows.length === 1 ? '' : 's'}`;
            if (!rows.length) {
                table.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No hay alumnos bloqueados por adeudo.</td></tr>';
                buildTablePagination('blocked-pagination', 'blocked-info', 1, 0, TABLE_PER_PAGE, 'changeBlockedPage');
                return;
            }
            const start = (blockedPage - 1) * TABLE_PER_PAGE;
            const page  = rows.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(row => `
                <tr>
                    <td class="fw-bold">${escHtml(row.username)}</td>
                    <td>${escHtml(row.full_name || 'Sin nombre')}</td>
                    <td>${row.overdue_charges}</td>
                    <td>${formatMoney(row.overdue_amount)}</td>
                    <td>${formatMoney(row.total_pending_amount)}</td>
                </tr>
            `).join('');
            buildTablePagination('blocked-pagination', 'blocked-info', blockedPage, rows.length, TABLE_PER_PAGE, 'changeBlockedPage');
        }

        async function loadGradeCenter() {
            try {
                const [assignmentsRes, outcomesRes] = await Promise.all([
                    fetch('/admin/subject-assignments', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/admin/reports/grade-outcomes', { headers: { 'Authorization': `Bearer ${token}` } })
                ]);

                if (assignmentsRes.ok) {
                    allAssignments = await assignmentsRes.json();
                    renderAssignments(allAssignments);
                    populateGradeAssignmentSelector();
                }

                if (outcomesRes.ok) {
                    gradeOutcomeRows = await outcomesRes.json();
                    document.getElementById('gradeAssignmentsCount').textContent = gradeOutcomeRows.length;
                    document.getElementById('gradeApprovedCount').textContent = gradeOutcomeRows.reduce((sum, row) => sum + (row.approved_count || 0), 0);
                    document.getElementById('gradeFailedCount').textContent = gradeOutcomeRows.reduce((sum, row) => sum + (row.failed_count || 0), 0);
                    document.getElementById('gradeInProgressCount').textContent = gradeOutcomeRows.reduce((sum, row) => sum + (row.in_progress_count || 0), 0);
                }
            } catch (error) {
                console.error('Error loading grade center', error);
            }
        }

        async function loadReportsDashboard() {
            const filters = getReportFilters();
            const query = buildQueryParams(filters);
            const suffix = query ? `?${query}` : '';
            setReportDashboardLoading();

            try {
                const [
                    overviewRes,
                    enrollmentStatusRes,
                    teacherWorkloadRes,
                    academicRiskRes,
                    serviceSummaryRes,
                    gradeOutcomesRes,
                    chargeBreakdownRes,
                    enrollmentSummaryRes,
                    financeSummaryRes
                ] = await Promise.all([
                    fetchJsonReport(`/admin/reports/overview${suffix}`),
                    fetchJsonReport(`/admin/reports/enrollment-status${suffix}`),
                    fetchJsonReport(`/admin/reports/teacher-workload${suffix}`),
                    fetchJsonReport(`/admin/reports/academic-risk${suffix}`),
                    fetchJsonReport(`/admin/reports/service-summary${suffix}`),
                    fetchJsonReport(`/admin/reports/grade-outcomes${suffix}`),
                    fetchJsonReport(`/admin/reports/charge-breakdown${suffix}`),
                    fetchJsonReport(`/admin/reports/enrollment-summary${suffix}`),
                    fetchJsonReport(`/admin/reports/finance-summary${suffix}`)
                ]);

                const overview = overviewRes.ok ? overviewRes.data : null;
                const enrollmentStatus = enrollmentStatusRes.ok ? enrollmentStatusRes.data : [];
                const teacherWorkload = teacherWorkloadRes.ok ? teacherWorkloadRes.data : [];
                const academicRisk = academicRiskRes.ok ? academicRiskRes.data : [];
                const serviceSummary = serviceSummaryRes.ok ? serviceSummaryRes.data : [];
                const gradeOutcomes = gradeOutcomesRes.ok ? gradeOutcomesRes.data : [];
                const chargeBreakdown = chargeBreakdownRes.ok ? chargeBreakdownRes.data : [];
                const enrollmentSummary = enrollmentSummaryRes.ok ? enrollmentSummaryRes.data : [];
                const finance = financeSummaryRes.ok ? financeSummaryRes.data : null;
                reportDashboardData = {
                    filters,
                    overview,
                    enrollmentStatus,
                    teacherWorkload,
                    academicRisk,
                    serviceSummary,
                    gradeOutcomes,
                    chargeBreakdown,
                    enrollmentSummary,
                    finance
                };

                renderOverviewReport(overview);
                renderEnrollmentStatusReport(enrollmentStatus);
                renderTeacherWorkloadReport(teacherWorkload);
                renderAcademicRiskReport(academicRisk);
                renderServiceSummaryReport(serviceSummary);
                renderGradeOutcomesReport(gradeOutcomes);
                renderChargeBreakdownReport(chargeBreakdown);
                generateReportCharts(enrollmentSummary, finance);
                const failedRequests = [
                    overviewRes,
                    enrollmentStatusRes,
                    teacherWorkloadRes,
                    academicRiskRes,
                    serviceSummaryRes,
                    gradeOutcomesRes,
                    chargeBreakdownRes,
                    enrollmentSummaryRes,
                    financeSummaryRes
                ].filter(result => !result.ok).length;
                if (failedRequests) {
                    showToast(`Se cargaron reportes con ${failedRequests} consulta${failedRequests === 1 ? '' : 's'} incompleta${failedRequests === 1 ? '' : 's'}`, 'warning');
                }
            } catch (error) {
                console.error('Error loading reports dashboard', error);
                setChartPlaceholder('chartCareerPlaceholder', 'careerChart', 'No fue posible cargar la grafica', 'danger');
                setChartPlaceholder('chartPaymentPlaceholder', 'paymentChart', 'No fue posible cargar la grafica', 'danger');
                showToast('No fue posible cargar los reportes', 'danger');
            }
        }

        function escapeCsvValue(value) {
            const stringValue = String(value ?? '');
            return `"${stringValue.replace(/"/g, '""')}"`;
        }

        function normalizeExportValue(value) {
            if (value === null || value === undefined) return '';
            return value;
        }

        function downloadBlobFile(content, filename, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        }

        function buildCsvSection(title, rows) {
            const lines = [title];
            if (!rows.length) {
                lines.push('Sin datos');
                lines.push('');
                return lines.join('\n');
            }
            const headers = Object.keys(rows[0]);
            lines.push(headers.map(escapeCsvValue).join(','));
            rows.forEach(row => {
                lines.push(headers.map(header => escapeCsvValue(normalizeExportValue(row[header]))).join(','));
            });
            lines.push('');
            return lines.join('\n');
        }

        function buildHtmlTable(title, rows) {
            if (!rows.length) {
                return `<h3>${escHtml(title)}</h3><p>Sin datos</p>`;
            }
            const headers = Object.keys(rows[0]);
            return `
                <h3>${escHtml(title)}</h3>
                <table border="1" cellspacing="0" cellpadding="6">
                    <thead>
                        <tr>${headers.map(header => `<th>${escHtml(header)}</th>`).join('')}</tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `<tr>${headers.map(header => `<td>${escHtml(normalizeExportValue(row[header]))}</td>`).join('')}</tr>`).join('')}
                    </tbody>
                </table>
                <br>
            `;
        }

        function getReportExportSections() {
            const overviewRows = reportDashboardData.overview ? [reportDashboardData.overview] : [];
            return [
                { title: 'Resumen Ejecutivo', rows: overviewRows },
                { title: 'Estatus de Inscripcion', rows: reportDashboardData.enrollmentStatus || [] },
                { title: 'Carga Docente', rows: reportDashboardData.teacherWorkload || [] },
                { title: 'Riesgo Academico', rows: reportDashboardData.academicRisk || [] },
                { title: 'Servicios Escolares', rows: reportDashboardData.serviceSummary || [] },
                { title: 'Resultados Academicos', rows: reportDashboardData.gradeOutcomes || [] },
                { title: 'Desglose de Cargos', rows: reportDashboardData.chargeBreakdown || [] },
                { title: 'Matricula por Segmento', rows: reportDashboardData.enrollmentSummary || [] },
                { title: 'Resumen Financiero', rows: reportDashboardData.finance ? [reportDashboardData.finance] : [] }
            ];
        }

        function exportReportsCsv() {
            const sections = getReportExportSections();
            if (!sections.some(section => section.rows.length)) {
                showToast('Primero carga los reportes para exportarlos', 'warning');
                return;
            }
            const filters = reportDashboardData.filters || getReportFilters();
            const filterRows = Object.entries(filters).map(([key, value]) => ({ filtro: key, valor: value || 'Todos' }));
            const content = [
                buildCsvSection('Filtros Aplicados', filterRows),
                ...sections.map(section => buildCsvSection(section.title, section.rows))
            ].join('\n');
            downloadBlobFile(content, `reportes_admin_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8;');
        }

        function exportReportsExcel() {
            const sections = getReportExportSections();
            if (!sections.some(section => section.rows.length)) {
                showToast('Primero carga los reportes para exportarlos', 'warning');
                return;
            }
            const filters = reportDashboardData.filters || getReportFilters();
            const filterRows = Object.entries(filters).map(([key, value]) => ({ filtro: key, valor: value || 'Todos' }));
            const html = `
                <html>
                    <head>
                        <meta charset="utf-8">
                        <link rel="stylesheet" href="assets/admin-page.css">
                    </head>
                    <body>
                        <h2>Reportes Administrativos</h2>
                        ${buildHtmlTable('Filtros Aplicados', filterRows)}
                        ${sections.map(section => buildHtmlTable(section.title, section.rows)).join('')}
                    </body>
                </html>
            `;
            downloadBlobFile(html, `reportes_admin_${new Date().toISOString().slice(0, 10)}.xls`, 'application/vnd.ms-excel');
        }

        function renderOverviewReport(overview) {
            if (!overview) {
                document.getElementById('reportOverviewStudents').textContent = '0';
                document.getElementById('reportOverviewAverage').textContent = '0.0';
                document.getElementById('reportOverviewApproval').textContent = '0.0%';
                document.getElementById('reportOverviewOverdue').textContent = formatMoney(0);
                document.getElementById('reportAvgGpa').textContent = '0.0';
                document.getElementById('reportApprovedRate').textContent = '0.0%';
                document.getElementById('reportFailedRate').textContent = '0.0%';
                return;
            }
            document.getElementById('reportOverviewStudents').textContent = overview.total_students || 0;
            document.getElementById('reportOverviewAverage').textContent = Number(overview.average_final_score || 0).toFixed(1);
            document.getElementById('reportOverviewApproval').textContent = `${Number(overview.approval_rate || 0).toFixed(1)}%`;
            document.getElementById('reportOverviewOverdue').textContent = formatMoney(overview.overdue_amount || 0);
            document.getElementById('reportAvgGpa').textContent = Number(overview.average_final_score || 0).toFixed(1);
            document.getElementById('reportApprovedRate').textContent = `${Number(overview.approval_rate || 0).toFixed(1)}%`;
            document.getElementById('reportFailedRate').textContent = `${Number(overview.failed_rate || 0).toFixed(1)}%`;
        }

        function renderEnrollmentStatusReport(rows) {
            const table = document.getElementById('reportEnrollmentStatusTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.map(row => `<tr><td>${escHtml(row.enrollment_status)}</td><td class="fw-bold">${row.total_students}</td></tr>`).join('')
                : '<tr><td colspan="2" class="text-center py-4 text-muted">Sin datos para el filtro actual.</td></tr>';
        }

        function renderTeacherWorkloadReport(rows) {
            const table = document.getElementById('reportTeacherWorkloadTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.map(row => `<tr><td>${escHtml(row.teacher_name || row.teacher_username || 'Sin docente')}</td><td>${row.assignments_count}</td><td>${row.students_count}</td><td>${row.groups_count}</td></tr>`).join('')
                : '<tr><td colspan="4" class="text-center py-4 text-muted">Sin carga docente para el filtro actual.</td></tr>';
        }

        function renderAcademicRiskReport(rows) {
            const table = document.getElementById('reportAcademicRiskTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.slice(0, 20).map(row => `<tr><td class="fw-bold">${escHtml(row.username)}</td><td>${escHtml(row.full_name || 'Sin nombre')}</td><td>${row.failed_count}</td><td>${row.in_progress_count}</td><td>${Number(row.average_score || 0).toFixed(1)}</td></tr>`).join('')
                : '<tr><td colspan="5" class="text-center py-4 text-muted">Sin alumnos en riesgo con el filtro actual.</td></tr>';
        }

        function renderServiceSummaryReport(rows) {
            const table = document.getElementById('reportServiceSummaryTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.map(row => `<tr><td>${escHtml(row.service_type)}</td><td>${escHtml(row.status)}</td><td class="fw-bold">${row.total_requests}</td></tr>`).join('')
                : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin servicios para el filtro actual.</td></tr>';
        }

        function renderGradeOutcomesReport(rows) {
            const table = document.getElementById('reportGradeOutcomesTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.slice(0, 25).map(row => `<tr><td>${escHtml(row.subject_name || 'Sin materia')}</td><td>${escHtml(row.teacher_name || 'Sin docente')}</td><td>${row.approved_count}</td><td>${row.failed_count}</td><td>${row.in_progress_count}</td></tr>`).join('')
                : '<tr><td colspan="5" class="text-center py-4 text-muted">Sin resultados para el filtro actual.</td></tr>';
        }

        function renderChargeBreakdownReport(rows) {
            const table = document.getElementById('reportChargeBreakdownTable');
            if (!table) return;
            table.innerHTML = rows.length
                ? rows.map(row => `<tr><td>${escHtml(row.charge_type)}</td><td>${escHtml(row.status)}</td><td>${row.total_charges}</td><td>${formatMoney(row.total_amount)}</td></tr>`).join('')
                : '<tr><td colspan="4" class="text-center py-4 text-muted">Sin cargos para el filtro actual.</td></tr>';
        }

        function generateReportCharts(enrollmentSummary, finance) {
            const careerCounts = {};
            (enrollmentSummary || []).forEach(row => {
                const label = row.career || 'Sin carrera';
                careerCounts[label] = (careerCounts[label] || 0) + (row.total_students || 0);
            });

            const careerLabels = Object.keys(careerCounts);
            const careerData = Object.values(careerCounts);

            const ctxCareer = document.getElementById('careerChart');

            if (careerChartInstance) careerChartInstance.destroy();
            if (careerLabels.length) {
                document.getElementById('chartCareerPlaceholder').style.display = 'none';
                ctxCareer.style.display = 'block';
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
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } }
                });
            } else {
                setChartPlaceholder('chartCareerPlaceholder', 'careerChart', 'Sin datos para el filtro actual');
            }

            const paymentCounts = {
                'Pagado': finance?.paid_count || 0,
                'Pendiente': finance?.pending_count || 0,
                'Vencido': finance?.overdue_count || 0
            };

            const ctxPayment = document.getElementById('paymentChart');

            if (paymentChartInstance) paymentChartInstance.destroy();
            if (finance && (paymentCounts['Pagado'] || paymentCounts['Pendiente'] || paymentCounts['Vencido'])) {
                document.getElementById('chartPaymentPlaceholder').style.display = 'none';
                ctxPayment.style.display = 'block';
                paymentChartInstance = new Chart(ctxPayment, {
                    type: 'bar',
                    data: {
                        labels: ['Pagado', 'Pendiente', 'Vencido'],
                        datasets: [{
                            label: 'Cantidad de cargos',
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
            } else {
                setChartPlaceholder('chartPaymentPlaceholder', 'paymentChart', 'Sin datos para el filtro actual');
            }
        }
