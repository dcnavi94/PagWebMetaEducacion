        async function loadAdminData() {
            try {
                // Verificar que sea admin
                const userResponse = await fetch('/users/me', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                if (userResponse.ok) {
                    const userData = await userResponse.json();
                    if (userData.role !== 'admin') {
                        window.location.href = '/campus-virtual';
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
                table.innerHTML = '<tr><td colspan="10" class="text-center py-4 text-muted">No hay cargos registrados.</td></tr>';
                buildTablePagination('charges-pagination', 'charges-info', 1, 0, TABLE_PER_PAGE, 'changeChargesPage');
                return;
            }
            const start = (chargesPage - 1) * TABLE_PER_PAGE;
            const page  = charges.slice(start, start + TABLE_PER_PAGE);
            
            // Note: In the backend, 'charges' have discount_amount.
            // Payments have is_conciliated, receipt_url. But this table renders Charges and calls them Pagos!
            // Wait, this table renders Charges... we need to fetch the associated payment to show the receipt/conciliation?
            // Actually, my backend update for get_all_charges doesn't return payment info, but wait...
            
            table.innerHTML = page.map(c => {
                // If backend does not send is_conciliated in get_all_charges, we might not be able to toggle it here directly unless we change backend.
                // Let's add the UI first.
                return `
                <tr>
                    <td class="fw-bold">${c.id}</td>
                    <td>
                        <div class="fw-bold">${escHtml(c.student?.username || 'N/A')}</div>
                        <div class="small text-muted">${escHtml(c.student?.full_name || 'Desconocido')}</div>
                    </td>
                    <td>${escHtml(c.charge_type || 'Otro')}</td>
                    <td>
                        ${escHtml(c.concept || '?')}
                        ${c.discount_amount ? `<br><small class="text-success border border-success rounded px-1">Desc: ${formatMoney(c.discount_amount)}</small>` : ''}
                    </td>
                    <td>${formatMoney(c.amount)}</td>
                    <td>${escHtml(c.period_label || '?')}</td>
                    <td>${formatDateShort(c.due_date)}</td>
                    <td>${renderPaymentStatusBadge(c.status)}</td>
                    <td>
                        <button class="btn btn-sm btn-light" title="Editar" onclick="openEditGlobalPayment(${c.id})"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm btn-outline-danger ms-1" title="Eliminar cargo" onclick="deleteGlobalPayment(${c.id})"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>
            `}).join('');
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
                
                // Load our new treasury reports
                await loadAgingBalancesReport();
                await loadIncomeFlowReport();
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

        async function loadAgingBalancesReport() {
            try {
                const response = await fetch('/admin/reports/aging-balances', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    const tbody = document.getElementById('agingBalancesTableBody');
                    if (!tbody) return;
                    tbody.innerHTML = data.length
                        ? data.map(row => `<tr>
                            <td>
                                <div><strong>${escHtml(row.username)}</strong></div>
                                <div class="text-muted small">${escHtml(row.full_name || 'Sin nombre')}</div>
                            </td>
                            <td>${formatMoney(row.days_1_30)}</td>
                            <td>${formatMoney(row.days_31_60)}</td>
                            <td>${formatMoney(row.days_61_90)}</td>
                            <td>${formatMoney(row.days_90_plus)}</td>
                            <td class="text-danger fw-bold">${formatMoney(row.total_overdue)}</td>
                        </tr>`).join('')
                        : '<tr><td colspan="6" class="text-center py-4 text-muted">No hay saldos vencidos.</td></tr>';
                }
            } catch (error) {
                console.error('Error loading aging balances', error);
            }
        }

        async function loadIncomeFlowReport() {
            try {
                const response = await fetch('/admin/reports/income-flow', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    const data = await response.json();
                    const tbody = document.getElementById('incomeFlowTableBody');
                    if (!tbody) return;
                    tbody.innerHTML = data.length
                        ? data.map(row => `<tr>
                            <td>${escHtml(row.payment_date)}</td>
                            <td><span class="badge bg-secondary">${escHtml(row.payment_method)}</span></td>
                            <td>${row.count}</td>
                            <td class="text-success fw-bold">${formatMoney(row.total_amount)}</td>
                        </tr>`).join('')
                        : '<tr><td colspan="4" class="text-center py-4 text-muted">No hay ingresos registrados en el sistema.</td></tr>';
                }
            } catch (error) {
                console.error('Error loading income flow', error);
            }
        }

                function exportAccountingReport() {
            if (!allCharges || allCharges.length === 0) {
                showToast('No hay datos financieros para exportar', 'warning');
                return;
            }

            // 1. Build career mapping for students
            const studentCareerMap = {};
            if (allStudents) {
                allStudents.forEach(s => {
                    studentCareerMap[s.username] = s.carrera || '';
                });
            }

            // Helper to clean and escape HTML
            const esc = (val) => {
                if (val === null || val === undefined) return '';
                return String(val)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
            };

            // Helper to format currency and percentages
            const formatCurr = (val) => Number(val || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            const formatPct = (val) => `${Number(val || 0).toFixed(2)}%`;

            // Helper to get Month-Year label (e.g. "Enero 2026")
            const getMonthYearKey = (dateStr) => {
                if (!dateStr) return 'Sin Fecha';
                const d = new Date(dateStr);
                if (isNaN(d.getTime())) return 'Sin Fecha';
                let mName = d.toLocaleString('es-MX', { month: 'long' });
                mName = mName.charAt(0).toUpperCase() + mName.slice(1);
                return `${mName} ${d.getFullYear()}`;
            };

            // Grouping lists for Uni and Prep
            const uniCharges = [];
            const prepCharges = [];

            allCharges.forEach(c => {
                const username = c.student ? c.student.username : '';
                const career = studentCareerMap[username] || '';
                const isPrep = career.toLowerCase().includes('preparatoria');
                if (isPrep) {
                    prepCharges.push(c);
                } else {
                    uniCharges.push(c);
                }
            });

            // Helper to group by month and sort keys chronologically
            const groupAndSortMonths = (charges) => {
                const groups = {};
                charges.forEach(c => {
                    const mKey = getMonthYearKey(c.due_date);
                    if (!groups[mKey]) groups[mKey] = [];
                    groups[mKey].push(c);
                });

                const sortedKeys = Object.keys(groups).sort((a, b) => {
                    if (a === 'Sin Fecha') return 1;
                    if (b === 'Sin Fecha') return -1;
                    const parseKey = (k) => {
                        const parts = k.split(' ');
                        const mNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
                        const mIdx = mNames.indexOf(parts[0]);
                        const yr = parseInt(parts[1]) || 0;
                        return yr * 12 + (mIdx >= 0 ? mIdx : 0);
                    };
                    return parseKey(a) - parseKey(b);
                });

                return { groups, sortedKeys };
            };

            const uniData = groupAndSortMonths(uniCharges);
            const prepData = groupAndSortMonths(prepCharges);

            // Calculate level statistics for resumes
            const calculateLevelStats = (charges) => {
                let totalBruto = 0;
                let totalDescuentos = 0;
                let totalNeto = 0;
                let totalCobrado = 0;
                let totalPendiente = 0;

                const conceptGroup = {};
                const conceptTypes = ['Colegiatura', 'Inscripcion', 'Reinscripcion', 'Tramite', 'Recargo', 'Beca', 'Otro'];
                conceptTypes.forEach(t => {
                    conceptGroup[t] = { count: 0, bruto: 0, descuentos: 0, neto: 0, cobrado: 0, pendiente: 0 };
                });

                const agingBrackets = {
                    'Vigente (Al corriente)': { count: 0, amount: 0 },
                    'Vencido 1-30 días': { count: 0, amount: 0 },
                    'Vencido 31-60 días': { count: 0, amount: 0 },
                    'Vencido 61-90 días': { count: 0, amount: 0 },
                    'Vencido +90 días': { count: 0, amount: 0 }
                };

                const today = new Date();
                today.setHours(0,0,0,0);

                charges.forEach(c => {
                    const amount = Number(c.amount || 0);
                    const discount = Number(c.discount_amount || 0);
                    const net = amount - discount;
                    const status = (c.status || '').toLowerCase();

                    let paid = 0;
                    if (status === 'pagado') {
                        paid = net;
                    } else {
                        paid = (c.payments || []).reduce((sum, p) => p.status === 'pagado' ? sum + Number(p.amount || 0) : sum, 0);
                        paid = Math.min(net, paid);
                    }
                    const pending = Math.max(0, net - paid);

                    totalBruto += amount;
                    totalDescuentos += discount;
                    totalNeto += net;
                    totalCobrado += paid;
                    totalPendiente += pending;

                    const type = c.charge_type || 'Otro';
                    if (!conceptGroup[type]) {
                        conceptGroup[type] = { count: 0, bruto: 0, descuentos: 0, neto: 0, cobrado: 0, pendiente: 0 };
                    }
                    conceptGroup[type].count += 1;
                    conceptGroup[type].bruto += amount;
                    conceptGroup[type].descuentos += discount;
                    conceptGroup[type].neto += net;
                    conceptGroup[type].cobrado += paid;
                    conceptGroup[type].pendiente += pending;

                    if (pending > 0) {
                        const dueDate = new Date(c.due_date);
                        dueDate.setHours(0,0,0,0);

                        if (dueDate >= today) {
                            agingBrackets['Vigente (Al corriente)'].count += 1;
                            agingBrackets['Vigente (Al corriente)'].amount += pending;
                        } else {
                            const diffTime = Math.abs(today - dueDate);
                            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                            if (diffDays <= 30) {
                                agingBrackets['Vencido 1-30 días'].count += 1;
                                agingBrackets['Vencido 1-30 días'].amount += pending;
                            } else if (diffDays <= 60) {
                                agingBrackets['Vencido 31-60 días'].count += 1;
                                agingBrackets['Vencido 31-60 días'].amount += pending;
                            } else if (diffDays <= 90) {
                                agingBrackets['Vencido 61-90 días'].count += 1;
                                agingBrackets['Vencido 61-90 días'].amount += pending;
                            } else {
                                agingBrackets['Vencido +90 días'].count += 1;
                                agingBrackets['Vencido +90 días'].amount += pending;
                            }
                        }
                    }
                });

                const efficiency = totalNeto > 0 ? (totalCobrado / totalNeto) * 100 : 0;

                return {
                    totalBruto,
                    totalDescuentos,
                    totalNeto,
                    totalCobrado,
                    totalPendiente,
                    conceptGroup,
                    agingBrackets,
                    efficiency
                };
            };

            const uniStats = calculateLevelStats(uniCharges);
            const prepStats = calculateLevelStats(prepCharges);

            // Build all worksheets data
            const sheets = [];

            // 1. Universidad Resumen
            sheets.push({
                name: 'Uni - Resumen',
                html: generateResumenHTML('Universidad', uniStats, uniCharges.length)
            });

            // 2. Universidad Months
            uniData.sortedKeys.forEach(mKey => {
                sheets.push({
                    name: `Uni - ${mKey}`.substring(0, 30),
                    html: generateMonthHTML('Universidad', mKey, uniData.groups[mKey])
                });
            });

            // 3. Preparatoria Resumen
            sheets.push({
                name: 'Prep - Resumen',
                html: generateResumenHTML('Preparatoria', prepStats, prepCharges.length)
            });

            // 4. Preparatoria Months
            prepData.sortedKeys.forEach(mKey => {
                sheets.push({
                    name: `Prep - ${mKey}`.substring(0, 30),
                    html: generateMonthHTML('Preparatoria', mKey, prepData.groups[mKey])
                });
            });

            // Helper to generate Resumen HTML
            function generateResumenHTML(levelTitle, stats, totalCount) {
                return `
                <table>
                    <tr>
                        <td colspan="8" class="header-title" style="border:none; font-size: 16pt; font-weight: bold; color: #1F4E79;">UNIVES - AUDITORÍA DE TESORERÍA (${levelTitle.toUpperCase()})</td>
                    </tr>
                    <tr>
                        <td colspan="8" class="header-subtitle" style="border:none; font-size: 10pt; color: #595959; font-style: italic;">Estado Financiero Ejecutivo | Fecha de Emisión: ${new Date().toLocaleString('es-MX')}</td>
                    </tr>
                </table>
                <br>
                
                <div class="table-title" style="font-size: 12pt; font-weight: bold; color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 3px; margin-top: 15px;">1. KPIs FINANCIEROS (RESUMEN OPERATIVO)</div>
                <table cellspacing="0" cellpadding="0">
                    <tr>
                        <th colspan="2" style="background-color: #2F5597; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 10pt;">Facturación y Cobranza</th>
                        <th colspan="2" style="background-color: #2F5597; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 10pt;">Cuentas por Cobrar</th>
                        <th colspan="2" style="background-color: #2F5597; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 10pt;">Eficiencia Administrativa</th>
                    </tr>
                    <tr>
                        <td class="kpi-label" style="color: #595959; font-size: 9pt; border: 1px solid #D9D9D9; padding: 5px 10px; font-weight: normal;">Facturación Bruta (Ingresos Brutos)</td>
                        <td class="number" style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalBruto)}</td>
                        <td class="kpi-label" style="color: #595959; font-size: 9pt; border: 1px solid #D9D9D9; padding: 5px 10px; font-weight: normal;">Cartera Pendiente (Cuentas por Cobrar)</td>
                        <td class="number" style="color: #C65911; font-weight: bold; border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalPendiente)}</td>
                        <td class="kpi-label" style="color: #595959; font-size: 9pt; border: 1px solid #D9D9D9; padding: 5px 10px; font-weight: normal;">Tasa de Recuperación (Collection Rate)</td>
                        <td class="pct" style="color: #385723; font-weight:bold; border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '0\\.00%';">${formatPct(stats.efficiency)}</td>
                    </tr>
                    <tr>
                        <td class="kpi-label" style="color: #595959; font-size: 9pt; border: 1px solid #D9D9D9; padding: 5px 10px; font-weight: normal;">Descuentos / Becas Aplicados</td>
                        <td class="number" style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalDescuentos)}</td>
                        <td style="border:none;"></td>
                        <td style="border:none;"></td>
                        <td style="border:none;"></td>
                        <td style="border:none;"></td>
                    </tr>
                    <tr class="total-row" style="background-color: #FFF2CC; font-weight: bold; border-top: 1.5px solid #1F4E79; border-bottom: 2.5px double #1F4E79;">
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px;">Facturación Neta (Ingresos Netos)</td>
                        <td class="number" style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalNeto)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px;">Total Recaudado (Efectivo Cobrado)</td>
                        <td class="number" style="color: #385723; border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalCobrado)}</td>
                        <td colspan="2" style="border:none;"></td>
                    </tr>
                </table>
                <br>
                
                <div class="table-title" style="font-size: 12pt; font-weight: bold; color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 3px; margin-top: 15px;">2. DESGLOSE DE INGRESOS POR CONCEPTO DE CARGO</div>
                <table cellspacing="0" cellpadding="0">
                    <thead>
                        <tr>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Concepto / Tipo de Cargo</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Cant. Cargos</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Facturado Bruto</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Descuentos</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Facturado Neto</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Recaudado</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Saldo Pendiente</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">% Tasa Cobranza</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${Object.entries(stats.conceptGroup).map(([concept, data], idx) => {
                            if (data.count === 0) return '';
                            const eff = data.neto > 0 ? (data.cobrado / data.neto) * 100 : 0;
                            return `
                            <tr style="${idx % 2 === 1 ? 'background-color: #F9F9F9;' : ''}">
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">${concept}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\#,##0';">${data.count}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(data.bruto)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(data.descuentos)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(data.neto)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(data.cobrado)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: ${data.pendiente > 0 ? '#C00000' : '#333333'};">${formatCurr(data.pendiente)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '0\\.00%';">${formatPct(eff)}</td>
                            </tr>`;
                        }).join('')}
                        <tr style="background-color: #FFF2CC; font-weight: bold; border-top: 1.5px solid #1F4E79; border-bottom: 2.5px double #1F4E79;">
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">TOTAL GENERAL</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\#,##0';">${totalCount}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalBruto)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalDescuentos)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalNeto)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalCobrado)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalPendiente)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '0\\.00%';">${formatPct(stats.efficiency)}</td>
                        </tr>
                    </tbody>
                </table>
                <br>
                
                <div class="table-title" style="font-size: 12pt; font-weight: bold; color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 3px; margin-top: 15px;">3. ANÁLISIS DE ANTIGÜEDAD DE SALDOS (CARTERA POR COBRAR)</div>
                <table cellspacing="0" cellpadding="0">
                    <thead>
                        <tr>
                            <th style="background-color: #833C0C; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Intervalo de Vencimiento</th>
                            <th style="background-color: #833C0C; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Cargos Vencidos</th>
                            <th style="background-color: #833C0C; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Monto Cartera Vencida</th>
                            <th style="background-color: #833C0C; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">% Concentración de Riesgo</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${Object.entries(stats.agingBrackets).map(([bracket, data], idx) => {
                            const part = stats.totalPendiente > 0 ? (data.amount / stats.totalPendiente) * 100 : 0;
                            return `
                            <tr style="${idx % 2 === 1 ? 'background-color: #F9F9F9;' : ''}">
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">${bracket}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\#,##0';">${data.count}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: ${data.amount > 0 && bracket !== 'Vigente (Al corriente)' ? '#C00000' : '#333333'};">${formatCurr(data.amount)}</td>
                                <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '0\\.00%';">${formatPct(part)}</td>
                            </tr>`;
                        }).join('')}
                        <tr style="background-color: #FFF2CC; font-weight: bold; border-top: 1.5px solid #1F4E79; border-bottom: 2.5px double #1F4E79;">
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">TOTAL CARTERA AUDITADA</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\#,##0';">${Object.values(stats.agingBrackets).reduce((sum, d) => sum + d.count, 0)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(stats.totalPendiente)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '0\\.00%';">100.00%</td>
                        </tr>
                    </tbody>
                </table>
                `;
            }

            // Helper to generate Month details HTML
            function generateMonthHTML(levelTitle, monthKey, charges) {
                let monthBruto = 0;
                let monthDescuentos = 0;
                let monthNeto = 0;
                let monthCobrado = 0;
                let monthPendiente = 0;

                const today = new Date();
                today.setHours(0,0,0,0);

                const rowsHtml = charges.map((c, idx) => {
                    const amount = Number(c.amount || 0);
                    const discount = Number(c.discount_amount || 0);
                    const net = amount - discount;
                    const status = (c.status || '').toLowerCase();

                    let paid = 0;
                    if (status === 'pagado') {
                        paid = net;
                    } else {
                        paid = (c.payments || []).reduce((sum, p) => p.status === 'pagado' ? sum + Number(p.amount || 0) : sum, 0);
                        paid = Math.min(net, paid);
                    }
                    const pending = Math.max(0, net - paid);

                    monthBruto += amount;
                    monthDescuentos += discount;
                    monthNeto += net;
                    monthCobrado += paid;
                    monthPendiente += pending;

                    let statusLabel = 'Pendiente';
                    let badgeStyle = 'color: #C65911; background-color: #FCE4D6;';
                    if (status === 'pagado') {
                        statusLabel = 'Pagado';
                        badgeStyle = 'color: #385723; background-color: #E2EFDA;';
                    } else if (status === 'vencido' || new Date(c.due_date) < today) {
                        statusLabel = 'Vencido';
                        badgeStyle = 'color: #C00000; background-color: #F8CBAD;';
                    }

                    const username = c.student ? c.student.username : 'N/A';
                    const full_name = c.student ? c.student.full_name : 'Desconocido';
                    const paymentDetail = (c.payments || []).map(p => `${p.concept}: $${p.amount} (${p.status})`).join(' | ') || 'Sin pagos';

                    return `
                    <tr style="${idx % 2 === 1 ? 'background-color: #F9F9F9;' : ''}">
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: center;">${c.id}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: center;">${esc(username)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">${esc(full_name)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">${esc(c.charge_type)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left;">${esc(c.concept)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: center; mso-number-format: 'yyyy-mm-dd';">${c.due_date ? new Date(c.due_date).toISOString().split('T')[0] : '—'}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: center; font-weight: bold; ${badgeStyle}">${statusLabel}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(amount)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(discount)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; font-weight: bold;">${formatCurr(net)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: #385723;">${formatCurr(paid)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: ${pending > 0 ? '#C00000' : '#333333'};">${formatCurr(pending)}</td>
                        <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: left; font-size: 8pt; color: #595959;">${esc(paymentDetail)}</td>
                    </tr>
                    `;
                }).join('');

                return `
                <table>
                    <tr>
                        <td colspan="13" class="header-title" style="border:none; font-size: 16pt; font-weight: bold; color: #1F4E79;">UNIVES - REGISTRO DE TRANSACCIONES DETALLADO</td>
                    </tr>
                    <tr>
                        <td colspan="13" class="header-subtitle" style="border:none; font-size: 10pt; color: #595959; font-style: italic;">Nivel Académico: ${levelTitle.toUpperCase()} | Periodo: ${monthKey.toUpperCase()}</td>
                    </tr>
                </table>
                <br>
                
                <div class="table-title" style="font-size: 12pt; font-weight: bold; color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 3px; margin-top: 15px;">LIBRO DIARIO AUXILIAR - CUENTAS Y COBROS</div>
                <table cellspacing="0" cellpadding="0">
                    <thead>
                        <tr>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">ID</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Matrícula</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Alumno</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Tipo</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Concepto</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Límite Pago</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Estado</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Importe</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Descuento</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Neto</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Recaudado</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Pendiente</th>
                            <th style="background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; font-size: 9pt;">Bitácora Transacciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rowsHtml}
                        <tr style="background-color: #FFF2CC; font-weight: bold; border-top: 1.5px solid #1F4E79; border-bottom: 2.5px double #1F4E79;">
                            <td colspan="7" style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right;">SUMA TOTAL DE LA PÁGINA:</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(monthBruto)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(monthDescuentos)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00';">${formatCurr(monthNeto)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: #385723;">${formatCurr(monthCobrado)}</td>
                            <td style="border: 1px solid #D9D9D9; padding: 5px 10px; text-align: right; mso-number-format: '\\$\\#,##0\\.00'; color: ${monthPendiente > 0 ? '#C00000' : '#333333'};">${formatCurr(monthPendiente)}</td>
                            <td style="border:none;"></td>
                        </tr>
                    </tbody>
                </table>
                `;
            }

            // 5. Generate final combined document
            const workbookName = `reporte_contable_${new Date().toISOString().split('T')[0]}.xls`;
            
            const xmlWorksheetsBlock = sheets.map(sheet => `
                            <x:ExcelWorksheet>
                                <x:Name>${sheet.name}</x:Name>
                                <x:WorksheetOptions>
                                    <x:DisplayGridlines/>
                                </x:WorksheetOptions>
                            </x:ExcelWorksheet>
            `).join('');

            const bodyWorksheetsBlock = sheets.map((sheet, index) => `
                <!-- Start of Sheet: ${sheet.name} -->
                ${sheet.html}
                ${index < sheets.length - 1 ? '<br style="mso-data-placement:same-cell;" /><div style="page-break-before:always"></div>' : ''}
            `).join('
');

            let html = `
            <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
            <head>
                <meta charset="utf-8">
                <!--[if gte mso 9]>
                <xml>
                    <x:ExcelWorkbook>
                        <x:ExcelWorksheets>
                            ${xmlWorksheetsBlock}
                        </x:ExcelWorksheets>
                    </x:ExcelWorkbook>
                </xml>
                <![endif]-->
                <style>
                    body { font-family: 'Segoe UI', Arial, sans-serif; color: #333333; }
                    .header-title { font-size: 16pt; font-weight: bold; color: #1F4E79; }
                    .header-subtitle { font-size: 11pt; color: #595959; font-style: italic; }
                    .table-title { font-size: 12pt; font-weight: bold; color: #1F4E79; margin-top: 20px; border-bottom: 2px solid #1F4E79; padding-bottom: 3px; }
                    table { border-collapse: collapse; margin-bottom: 20px; font-size: 10pt; }
                    th { background-color: #1F4E79; color: #FFFFFF; font-weight: bold; border: 1px solid #D9D9D9; padding: 6px 12px; }
                    td { border: 1px solid #D9D9D9; padding: 5px 10px; }
                    .text-left { text-align: left; }
                    .text-center { text-align: center; }
                    .text-right { text-align: right; }
                    .number { mso-number-format: "\\$\\#,##0\\.00"; text-align: right; }
                    .pct { mso-number-format: "0\\.00%"; text-align: right; }
                    .qty { mso-number-format: "\\#,##0"; text-align: right; }
                    .kpi-label { color: #595959; font-size: 9pt; }
                    .total-row { background-color: #FFF2CC; font-weight: bold; border-top: 1.5px solid #1F4E79; border-bottom: 2.5px double #1F4E79; }
                    .zebra { background-color: #F9F9F9; }
                    .badge-pagado { color: #385723; background-color: #E2EFDA; text-align: center; font-weight: bold; }
                    .badge-pendiente { color: #C65911; background-color: #FCE4D6; text-align: center; font-weight: bold; }
                    .badge-vencido { color: #C00000; background-color: #F8CBAD; text-align: center; font-weight: bold; }
                </style>
            </head>
            <body>
                ${bodyWorksheetsBlock}
            </body>
            </html>
            `;

            const blob = new Blob([html], { type: 'application/vnd.ms-excel' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = workbookName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        }

        // Initialize reports when dom is ready
        document.addEventListener('DOMContentLoaded', () => {
            if(document.getElementById('report-aging-balances')) loadAgingBalancesReport();
            if(document.getElementById('report-income-flow')) loadIncomeFlowReport();
        });
