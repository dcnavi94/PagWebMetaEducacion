        const token = localStorage.getItem('token');






        const API_BASE = window.API_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;






        const apiUrl = (path = '') => `${API_BASE}${path.startsWith(`/') ? path : `/${path}`}`;






        if (!token) window.location.href = 'login.html';













        let allStudents = [];






        let filteredStudents = [];






        let allTeachers = [];






        let filteredTeachers = [];






        let currentViewedStudentUsername = '';






        let allSubjects = [];






        let filteredSubjects = [];






        let allPayments = [];






        let filteredPayments = [];






        let allCharges = [];






        let filteredCharges = [];






        let allServices = [];






        let filteredServices = [];






        let allStudentEnrollments = [];






        let filteredStudentEnrollments = [];






        let allGroupSummaries = [];






        let gradeOutcomeRows = [];






        let financeSummary = null;






        let cycleControlList = [];






        let selectedCycleControlId = null;






        let blockedStudents = [];






        let reportDashboardData = {};






        let adminSupportTickets = [];






        let moodlePendingCounts = { students: 0, teachers: 0, subjects: 0 };






        let selectedGradeRows = [];






        let catalogCareers = [];






        let catalogModalities = [];






        let currentPage = 1;






        const itemsPerPage = 10;






        const DEFAULT_STUDENT_SEMESTERS = [






            { value: '1', label: '1er Semestre' },






            { value: '2', label: '2do Semestre' },






            { value: '3', label: '3er Semestre' },






            { value: '4', label: '4to Semestre' },






            { value: '5', label: '5to Semestre' },






            { value: '6', label: '6to Semestre' },






            { value: '7', label: '7mo Semestre' },






            { value: '8', label: '8vo Semestre' },






            { value: '9', label: '9no Semestre' },






            { value: 'Especial', label: 'Especial' }






        ];






        const DEFAULT_CAREERS = [






            { name: 'Ingeniería en Software' },






            { name: 'Ingeniería en Telemática' },






            { name: 'Preparatoria' }






        ];






        const DEFAULT_MODALITIES = [






            { name: 'Presencial Intensiva' },






            { name: 'Presencial Sabatino' },






            { name: 'Virtual' }






        ];













        async function loadCatalogs() {






            try {






                const [careersResponse, modalitiesResponse] = await Promise.all([






                    fetch(API_BASE + '/catalogs/careers', { headers: { 'Authorization': `Bearer ${token}` } }),






                    fetch(API_BASE + '/catalogs/modalities', { headers: { 'Authorization': `Bearer ${token}` } })






                ]);













                if (careersResponse.ok) {






                    catalogCareers = await careersResponse.json();






                }













                if (modalitiesResponse.ok) {






                    catalogModalities = await modalitiesResponse.json();






                }






            } catch (err) {






                console.error('Error cargando catalogos', err);






            }













            populateCareerSelects();






            populateModalitySelects();






            populateSemesterSelects();






        }













        function mergeCatalogData(primaryItems = [], fallbackItems = []) {






            const merged = [];






            const seenNames = new Set();













            [...primaryItems, ...fallbackItems].forEach(item => {






                if (!item || !item.name) return;






                const normalizedName = item.name.trim().toLowerCase();






                if (seenNames.has(normalizedName)) return;






                seenNames.add(normalizedName);






                merged.push(item);






            });













            return merged;






        }













        function syncCatalogsFromStudents() {






            // Solo usa defaults como fallback si el API aún no devolvió datos






            if (catalogCareers.length === 0) {






                catalogCareers = [...DEFAULT_CAREERS];






            }






            catalogModalities = mergeCatalogData(catalogModalities, DEFAULT_MODALITIES);













            populateCareerSelects();






            populateModalitySelects();






        }













        function populateSelect(selectId, data, options = {}) {






            const select = document.getElementById(selectId);






            if (!select) return;













            const {






                includeEmpty = true,






                emptyLabel = 'Seleccionar...',






                valueGetter = (item) => item.id,






                labelGetter = (item) => item.name






            } = options;













            select.innerHTML = '';






            if (includeEmpty) {






                const opt = document.createElement('option');






                opt.value = '';






                opt.textContent = emptyLabel;






                select.appendChild(opt);






            }













            data.forEach(item => {






                const opt = document.createElement('option');






                const value = valueGetter(item);






                opt.value = value !== undefined && value !== null ? String(value) : '';






                opt.textContent = labelGetter(item);






                select.appendChild(opt);






            });






        }













        function populateCareerSelects() {






            const careerOptions = catalogCareers.length > 0 ? catalogCareers : DEFAULT_CAREERS;






            populateSelect('filterCareer', careerOptions, { includeEmpty: true, emptyLabel: 'Todas las carreras / niveles', valueGetter: (c) => c.name, labelGetter: (c) => c.name });






            populateSelect('newMajor', careerOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (c) => c.id ?? c.name, labelGetter: (c) => c.name });






            populateSelect('editMajor', careerOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (c) => c.id ?? c.name, labelGetter: (c) => c.name });






            populateSelect('filterSubjectCareer', careerOptions, { includeEmpty: true, emptyLabel: 'Todas las Carreras', valueGetter: (c) => c.name, labelGetter: (c) => c.name });






            populateSelect('newSubjectCareer', careerOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (c) => c.name, labelGetter: (c) => c.name });






            populateSelect('editSubjectCareer', careerOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (c) => c.name, labelGetter: (c) => c.name });






        }













        function populateModalitySelects() {






            const modalityOptions = mergeCatalogData(catalogModalities, DEFAULT_MODALITIES);






            populateSelect('newModalidad', modalityOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (m) => m.id ?? m.name, labelGetter: (m) => m.name });






            populateSelect('editModalidad', modalityOptions, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (m) => m.id ?? m.name, labelGetter: (m) => m.name });






        }













        function populateSemesterSelects() {






            populateSelect('newSemester', DEFAULT_STUDENT_SEMESTERS, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (item) => item.value, labelGetter: (item) => item.label });






            populateSelect('editSemester', DEFAULT_STUDENT_SEMESTERS, { includeEmpty: true, emptyLabel: 'Seleccionar...', valueGetter: (item) => item.value, labelGetter: (item) => item.label });






        }













        function isActiveStudent(student) {






            const userStatus = String(student?.user_status || '').toLowerCase();






            const enrollmentStatus = String(student?.enrollment_status || '').toLowerCase();






            return !['baja', 'inactivo', 'egresado'].includes(userStatus) &&






                !['baja', 'baja definitiva', 'baja temporal', 'egresado'].includes(enrollmentStatus);






        }













        function isUnpaidStatus(status) {






            const normalized = String(status || '').toLowerCase();






            return !['pagado', 'paid', 'liquidado', 'completado'].includes(normalized);






        }













        function isOpenStatus(status) {






            const normalized = String(status || '').toLowerCase();






            return !['listo', 'entregado', 'resuelto', 'cerrado', 'cancelado', 'cancelada', 'realizada'].includes(normalized);






        }













        function isPastDue(dateValue) {






            if (!dateValue) return false;






            const date = new Date(dateValue);






            if (Number.isNaN(date.getTime())) return false;






            const today = new Date();






            today.setHours(0, 0, 0, 0);






            date.setHours(0, 0, 0, 0);






            return date < today;






        }













        function countStudentsWithoutGroup() {






            return allStudents.filter(student => isActiveStudent(student) && !String(student.grupo || student.group_name || '').trim()).length;






        }













        function countIncompleteStudentRecords() {






            return allStudents.filter(student => {






                if (!isActiveStudent(student)) return false;






                return !String(student.carrera || student.career || '').trim() ||






                    !String(student.semestre || student.semester || '').trim() ||






                    !String(student.grupo || student.group_name || '').trim();






            }).length;






        }













        function countTeachersWithoutAssignments() {






            if (!Array.isArray(allAssignments) || !allAssignments.length) return 0;






            return allTeachers.filter(teacher => {






                const username = teacher.username;






                const id = String(teacher.id || '');






                return !allAssignments.some(assignment =>






                    assignment.teacher?.username === username ||






                    String(assignment.teacher?.id || '') === id ||






                    assignment.teacher_username === username






                );






            }).length;






        }













        function countSubjectsWithoutTeacher() {






            if (!Array.isArray(allAssignments) || !allAssignments.length) return allSubjects.length;






            return allSubjects.filter(subject => !allAssignments.some(assignment =>






                String(assignment.subject?.id || assignment.subject_id || '') === String(subject.id || '')






            )).length;






        }













        function countEmptyAssignments() {






            if (!Array.isArray(allAssignments)) return 0;






            return allAssignments.filter(assignment => Number(assignment.student_count || 0) === 0).length;






        }













        function countPastDuePayments() {






            const source = allCharges.length ? allCharges : allPayments;






            return source.filter(item => isUnpaidStatus(item.status) && isPastDue(item.due_date || item.payment_date)).length;






        }













        function countOpenServices() {






            return allServices.filter(item => isOpenStatus(item.status)).length;






        }













        function renderAdminCriticalQueue() {






            const queue = document.getElementById('adminCriticalQueue');






            const counter = document.getElementById('adminCriticalCount');






            if (!queue) return;













            const studentsWithoutGroup = countStudentsWithoutGroup();






            const incompleteStudents = countIncompleteStudentRecords();






            const subjectsWithoutTeacher = countSubjectsWithoutTeacher();






            const teachersWithoutAssignments = countTeachersWithoutAssignments();






            const emptyAssignments = countEmptyAssignments();






            const pastDuePayments = countPastDuePayments();






            const openServices = countOpenServices();






            const openTickets = adminSupportTickets.filter(ticket => isOpenStatus(ticket.status)).length;






            const moodlePending = Number(moodlePendingCounts.students || 0) + Number(moodlePendingCounts.teachers || 0) + Number(moodlePendingCounts.subjects || 0);













            const items = [];






            if (studentsWithoutGroup) items.push({






                severity: 'blocker',






                icon: 'bi-person-x-fill',






                color: 'text-danger',






                bg: 'bg-danger-subtle',






                title: `${studentsWithoutGroup} alumnos sin grupo`,






                text: 'Asignar grupo evita errores en carga académica y reportes.',






                action: 'Ir a grupos',






                fn: "switchView('view-grupos')"






            });






            if (incompleteStudents) items.push({






                severity: 'warning',






                icon: 'bi-clipboard2-x-fill',






                color: 'text-warning',






                bg: 'bg-warning-subtle',






                title: `${incompleteStudents} expedientes incompletos`,






                text: 'Falta carrera, semestre o grupo en alumnos activos.',






                action: 'Control escolar',






                fn: "switchView('view-control-escolar')"






            });






            if (subjectsWithoutTeacher) items.push({






                severity: 'blocker',






                icon: 'bi-journal-x',






                color: 'text-danger',






                bg: 'bg-danger-subtle',






                title: `${subjectsWithoutTeacher} materias sin docente`,






                text: 'Completar asignaciones antes de iniciar operación académica.',






                action: 'Asignar docente',






                fn: "switchView('view-asignaciones')"






            });






            if (teachersWithoutAssignments) items.push({






                severity: 'warning',






                icon: 'bi-person-badge',






                color: 'text-warning',






                bg: 'bg-warning-subtle',






                title: `${teachersWithoutAssignments} docentes sin carga`,






                text: 'Revisar disponibilidad o Asignación del ciclo activo.',






                action: 'Ver docentes',






                fn: "switchView('view-docentes')"






            });






            if (emptyAssignments) items.push({






                severity: 'info',






                icon: 'bi-people',






                color: 'text-primary',






                bg: 'bg-primary-subtle',






                title: `${emptyAssignments} asignaciones sin alumnos`,






                text: 'Validar carga académica por grupo o materia.',






                action: 'Revisar asignaciones',






                fn: "switchView('view-asignaciones')"






            });






            if (pastDuePayments) items.push({






                severity: 'blocker',






                icon: 'bi-cash-coin',






                color: 'text-danger',






                bg: 'bg-danger-subtle',






                title: `${pastDuePayments} pagos vencidos`,






                text: 'Priorizar seguimiento de cartera y bloqueos.',






                action: 'Ir a tesorería',






                fn: "switchView('view-finanzas')"






            });






            if (openServices) items.push({






                severity: 'warning',






                icon: 'bi-file-earmark-text-fill',






                color: 'text-warning',






                bg: 'bg-warning-subtle',






                title: `${openServices} Trámites abiertos`,






                text: 'Dar seguimiento antes de que se acumulen solicitudes.',






                action: 'Ver servicios',






                fn: "switchView('view-tramites')"






            });






            if (moodlePending) items.push({






                severity: 'warning',






                icon: 'bi-laptop',






                color: 'text-warning',






                bg: 'bg-warning-subtle',






                title: `${moodlePending} pendientes Moodle`,






                text: 'Sincronizar alumnos, docentes o materias faltantes.',






                action: 'Revisar Moodle',






                fn: "switchView('view-moodle-admin')"






            });






            if (openTickets) items.push({






                severity: 'info',






                icon: 'bi-life-preserver',






                color: 'text-primary',






                bg: 'bg-primary-subtle',






                title: `${openTickets} tickets abiertos`,






                text: 'Atender incidencias de soporte técnico.',






                action: 'Ver soporte',






                fn: "switchView('view-soporte-admin')"






            });













            if (counter) counter.textContent = `${items.length} pendientes`;






            if (!items.length) {






                queue.innerHTML = `






                    <div class="col-12">






                        <div class="notice-row">






                            <div class="fw-semibold text-success"><i class="bi bi-check-circle-fill me-2"></i>Operación sin bloqueos críticos</div>






                            <div class="small text-muted">No hay pendientes detectados con los datos cargados.</div>






                        </div>






                    </div>`;






                return;






            }













            queue.innerHTML = items.map(item => `






                <div class="col-md-6 col-xl-4">






                    <div class="critical-card ${item.severity}">






                        <div class="d-flex align-items-start gap-3">






                            <span class="icon ${item.bg} ${item.color}"><i class="bi ${item.icon}"></i></span>






                            <div class="flex-fill">






                                <div class="fw-bold">${item.title}</div>






                                <div class="small text-muted mb-2">${item.text}</div>






                                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="${item.fn}">${item.action}</button>






                            </div>






                        </div>






                    </div>






                </div>`).join('');






        }













        function normalizeSearchText(value) {






            return String(value || '')






                .normalize('NFD')






                .replace(/[\u0300-\u036f]/g, '')






                .toLowerCase()






                .trim();






        }













        function searchHaystack(...values) {






            return normalizeSearchText(values.filter(Boolean).join(' '));






        }













        function buildGlobalSearchResults(query) {






            const q = normalizeSearchText(query);






            if (q.length < 2) return [];






            const results = [];






            const pushResult = (item) => {






                if (results.length < 24) results.push(item);






            };













            allStudents.forEach(student => {






                const haystack = searchHaystack(student.username, student.full_name, student.email, student.carrera, student.grupo, student.semestre);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Alumno',






                    icon: 'bi-person-fill',






                    tone: 'text-primary bg-primary-subtle',






                    title: student.full_name || student.username,






                    meta: `${student.username || '-'} A‚· ${student.carrera || '-'} A‚· Grupo ${student.grupo || '-'}`,






                    actionLabel: 'Abrir expediente',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-alumnos');






                        openViewStudent(student.username);






                    }






                });






            });













            allTeachers.forEach(teacher => {






                const haystack = searchHaystack(teacher.username, teacher.full_name, teacher.email);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Docente',






                    icon: 'bi-person-badge-fill',






                    tone: 'text-success bg-success-subtle',






                    title: teacher.full_name || teacher.username,






                    meta: `${teacher.username || '-'} A‚· ${teacher.email || '-'}`,






                    actionLabel: 'Ver docente',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-docentes');






                        openViewTeacher(teacher.username);






                    }






                });






            });













            allSubjects.forEach(subject => {






                const haystack = searchHaystack(subject.id, subject.name, subject.career, subject.semester);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Materia',






                    icon: 'bi-journal-bookmark-fill',






                    tone: 'text-info bg-info-subtle',






                    title: subject.name || `Materia #${subject.id}`,






                    meta: `${subject.career || '-'} A‚· Semestre ${subject.semester || '-'} A‚· ${subject.credits || 0} créditos`,






                    actionLabel: 'Ir a oferta',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-materias');






                    }






                });






            });













            (allAssignments || []).forEach(assignment => {






                const subject = assignment.subject || {};






                const teacher = assignment.teacher || {};






                const group = assignment.group || {};






                const haystack = searchHaystack(subject.name, subject.career, subject.semester, teacher.full_name, teacher.username, group.name, assignment.group_name);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Asignación',






                    icon: 'bi-person-check-fill',






                    tone: 'text-primary bg-primary-subtle',






                    title: subject.name || 'Asignación académica',






                    meta: `${teacher.full_name || teacher.username || 'Sin docente'} A‚· Grupo ${group.name || assignment.group_name || '-'}`,






                    actionLabel: 'Ver asignaciones',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-asignaciones');






                    }






                });






            });













            (allGroupSummaries || []).forEach(group => {






                const haystack = searchHaystack(group.grupo, group.name, group.carrera, group.career, group.semester, group.student_count);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Grupo',






                    icon: 'bi-people-fill',






                    tone: 'text-warning bg-warning-subtle',






                    title: `Grupo ${group.grupo || group.name || '-'}`,






                    meta: `${group.carrera || group.career || '-'} A‚· ${group.student_count || 0} alumnos`,






                    actionLabel: 'Abrir grupo',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-grupos');






                        if (group.group_id || group.id) {






                            setTimeout(() => selectGroup(group.group_id || group.id, group.grupo || group.name, group.carrera || group.career || ''), 50);






                        }






                    }






                });






            });













            allServices.forEach(service => {






                const haystack = searchHaystack(service.id, service.student_username, service.student_name, service.type, service.service_type, service.status);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Trámite',






                    icon: 'bi-file-earmark-text-fill',






                    tone: 'text-warning bg-warning-subtle',






                    title: service.type || service.service_type || `Trámite #${service.id}`,






                    meta: `${service.student_name || service.student_username || 'Alumno'} A‚· ${service.status || 'En proceso'}`,






                    actionLabel: 'Ver servicios',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-tramites');






                    }






                });






            });













            [...allCharges, ...allPayments].forEach(payment => {






                const haystack = searchHaystack(payment.id, payment.student_username, payment.student_name, payment.concept, payment.status, payment.amount);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Pago',






                    icon: 'bi-cash-coin',






                    tone: 'text-success bg-success-subtle',






                    title: payment.concept || `Pago #${payment.id}`,






                    meta: `${payment.student_name || payment.student_username || 'Alumno'} A‚· ${payment.status || '-'} A‚· ${formatMoney(payment.amount)}`,






                    actionLabel: 'Ir a tesorería',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-finanzas');






                    }






                });






            });













            adminSupportTickets.forEach(ticket => {






                const haystack = searchHaystack(ticket.id, ticket.student_username, ticket.student_name, ticket.subject, ticket.type, ticket.status);






                if (!haystack.includes(q)) return;






                pushResult({






                    type: 'Soporte',






                    icon: 'bi-life-preserver',






                    tone: 'text-danger bg-danger-subtle',






                    title: ticket.subject || ticket.type || `Ticket #${ticket.id}`,






                    meta: `${ticket.student_name || ticket.student_username || 'Usuario'} A‚· ${ticket.status || '-'}`,






                    actionLabel: 'Ver soporte',






                    action: () => {






                        hideGlobalSearchResults();






                        switchView('view-soporte-admin');






                    }






                });






            });













            return results;






        }













        function renderGlobalSearchResults() {






            const input = document.getElementById('adminGlobalSearch');






            const box = document.getElementById('adminGlobalSearchResults');






            const clear = document.getElementById('adminGlobalSearchClear');






            if (!input || !box) return;






            const query = input.value.trim();






            if (clear) clear.style.display = query ? '' : 'none';






            if (query.length < 2) {






                box.classList.remove('show');






                box.innerHTML = '';






                return;






            }






            const results = buildGlobalSearchResults(query);






            if (!results.length) {






                box.innerHTML = '<div class="p-3 text-muted small">Sin resultados. Prueba con matrícula, nombre, folio, materia o grupo.</div>';






                box.classList.add('show');






                return;






            }






            box.innerHTML = `






                <div class="px-3 py-2 border-bottom small text-muted fw-semibold">${results.length} resultado(s)</div>






                ${results.map((result, index) => `






                    <button type="button" class="global-search-item" data-search-index="${index}">






                        <span class="type-icon ${result.tone}"><i class="bi ${result.icon}"></i></span>






                        <span class="flex-fill min-w-0">






                            <span class="d-flex justify-content-between gap-2">






                                <strong class="text-truncate">${escHtml(result.title)}</strong>






                                <span class="badge bg-light text-dark border">${result.type}</span>






                            </span>






                            <span class="d-block small text-muted text-truncate">${escHtml(result.meta)}</span>






                            <span class="d-block small text-primary fw-semibold mt-1">${result.actionLabel}</span>






                        </span>






                    </button>






                `).join('')}`;






            box.querySelectorAll('[data-search-index]').forEach(button => {






                button.addEventListener('click', () => {






                    const result = results[Number(button.getAttribute('data-search-index'))];






                    if (result?.action) result.action();






                });






            });






            box.classList.add('show');






        }













        function hideGlobalSearchResults() {






            const box = document.getElementById('adminGlobalSearchResults');






            const input = document.getElementById('adminGlobalSearch');






            const clear = document.getElementById('adminGlobalSearchClear');






            if (box) {






                box.classList.remove('show');






                box.innerHTML = '';






            }






            if (input) input.value = '';






            if (clear) clear.style.display = 'none';






        }













        function setupGlobalSearch() {






            const input = document.getElementById('adminGlobalSearch');






            const clear = document.getElementById('adminGlobalSearchClear');






            if (!input) return;






            input.addEventListener('input', renderGlobalSearchResults);






            input.addEventListener('keydown', (event) => {






                if (event.key === 'Escape') hideGlobalSearchResults();






                if (event.key === 'Enter') {






                    const first = document.querySelector('#adminGlobalSearchResults [data-search-index]');






                    if (first) first.click();






                }






            });






            clear?.addEventListener('click', hideGlobalSearchResults);






            document.addEventListener('click', (event) => {






                const wrap = document.querySelector('.global-search-wrap');






                if (wrap && !wrap.contains(event.target)) {






                    const box = document.getElementById('adminGlobalSearchResults');






                    box?.classList.remove('show');






                }






            });






        }













        async function populateRegisterStudentGroupSelect(selectedGroup = '') {






            const select = document.getElementById('newGroup');






            if (!select) return;






            select.innerHTML = '<option value="">Cargando grupos...</option>';






            try {






                await ensureGroupSummariesLoaded(true);






            } catch (error) {






                console.error('Error loading groups for register student modal:', error);






                select.innerHTML = '<option value="">No se pudieron cargar los grupos</option>';






                return;






            }













            const selectedCareerName = document.getElementById('newMajor')?.selectedOptions?.[0]?.textContent?.trim() || '';






            const selectedModalityId = document.getElementById('newModalidad')?.value?.trim() || '';






            const allGroups = Array.isArray(allGroupSummaries) ? allGroupSummaries : [];






            const filteredGroups = allGroups.filter(group => {






                const matchesCareer = !selectedCareerName || selectedCareerName === 'Seleccionar...' || String(group.carrera || '').trim() === selectedCareerName || String(group.carrera || '').trim() === 'Sin carrera';






                const matchesModality = !selectedModalityId || !String(group.modality_id || '').trim() || String(group.modality_id || '') === selectedModalityId;






                return matchesCareer && matchesModality;






            });













            const groupsToShow = filteredGroups.length ? filteredGroups : allGroups;






            const uniqueGroups = [];






            const seen = new Set();






            groupsToShow.forEach(group => {






                const key = `${group.grupo || ''}||${group.carrera || ''}`;






                if (!group.grupo || seen.has(key)) return;






                seen.add(key);






                uniqueGroups.push(group);






            });













            select.innerHTML = '<option value="">Seleccionar...</option>';






            if (!uniqueGroups.length) {






                select.innerHTML += '<option value="" disabled>No hay grupos registrados</option>';






                return;






            }













            uniqueGroups






                .sort((a, b) => `${a.grupo || ''} ${a.carrera || ''}`.localeCompare(`${b.grupo || ''} ${b.carrera || ''}`))






                .forEach(group => {






                    const option = document.createElement('option');






                    option.value = String(group.grupo || '');






                    option.textContent = `${group.grupo} A¢â‚¬" ${group.carrera || 'Sin carrera'} (${group.total || 0} alumnos)`;






                    if (String(group.grupo || '') === String(selectedGroup || '')) {






                        option.selected = true;






                    }






                    select.appendChild(option);






                });






        }













        function getCatalogSelection(selectId) {






            const select = document.getElementById(selectId);






            const rawValue = select?.value?.trim() || '';






            const selectedLabel = select?.selectedOptions?.[0]?.textContent?.trim() || null;













            if (!rawValue) {






                return { id: null, name: null };






            }













            const numericId = Number.parseInt(rawValue, 10);






            return {






                id: Number.isNaN(numericId) ? null : numericId,






                name: selectedLabel






            };






        }













        function formatMoney(amount) {






            return new Intl.NumberFormat('es-MX', {






                style: 'currency',






                currency: 'MXN'






            }).format(Number(amount || 0));






        }













        function formatDateShort(value) {






            if (!value) return '—';






            return new Date(value).toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: 'numeric' });






        }













        function renderPaymentStatusBadge(status) {






            if (status === 'Pagado') return '<span class="badge bg-success">Pagado</span>';






            if (status === 'Vencido') return '<span class="badge bg-danger">Vencido</span>';






            return '<span class="badge bg-warning text-dark">Pendiente</span>';






        }













        function renderSubjectModalityBadge(modality) {






            const normalized = (modality || 'presencial').toLowerCase();






            if (normalized === 'virtual') return '<span class="badge bg-primary">Virtual</span>';






            if (normalized === 'hibrido' || normalized === 'híbrido') return '<span class="badge bg-info text-dark">Hibrido</span>';






            return '<span class="badge bg-secondary">Presencial</span>';






        }













        function normalizeGradeStatus(score, status) {






            if (status && status !== 'Cursando') return status;






            if (score === '' || score === null || score === undefined) return 'Cursando';






            const numericScore = parseFloat(score);






            if (Number.isNaN(numericScore)) return 'Cursando';






            return numericScore > 5 ? 'Aprobada' : 'Reprobada';






        }













        function getActiveEnrollmentForStudent(student) {






            if (!student) return null;






            return allStudentEnrollments.find(enrollment =>






                enrollment.student?.id === student.id ||






                enrollment.student?.username === student.username






            ) || null;






        }













        function applyOperationalEnrollmentData(student, enrollment = null) {






            if (!student) return student;






            const activeEnrollment = enrollment || getActiveEnrollmentForStudent(student);






            if (!activeEnrollment) return { ...student };













            return {






                ...student,






                legacy_carrera: student.carrera,






                legacy_modalidad: student.modalidad,






                legacy_semestre: student.semestre,






                legacy_grupo: student.grupo,






                carrera: activeEnrollment.career?.name || student.carrera,






                career_id: activeEnrollment.career_id ?? student.career_id,






                modalidad: activeEnrollment.modality?.name || student.modalidad,






                modality_id: activeEnrollment.modality_id ?? student.modality_id,






                semestre: activeEnrollment.semester || student.semestre,






                grupo: activeEnrollment.group?.name || student.grupo,






                enrollment_status: activeEnrollment.enrollment_status || student.enrollment_status,






                active_student_enrollment_id: activeEnrollment.id






            };






        }













        function syncStudentsWithActiveEnrollments() {






            allStudents = allStudents.map(student => applyOperationalEnrollmentData(student));






            filteredStudents = filteredStudents.map(student => applyOperationalEnrollmentData(student));






        }













        async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 15000) {






            const controller = new AbortController();






            const timer = setTimeout(() => controller.abort(), timeoutMs);






            try {






                const response = await fetch(url, { ...options, signal: controller.signal });






                if (!response.ok) {






                    throw new Error(`HTTP ${response.status}`);






                }






                return await response.json();






            } finally {






                clearTimeout(timer);






            }






        }













        async function loadAdminData() {






            try {






                // Verificar que sea admin






                const userData = await fetchJsonWithTimeout(API_BASE + '/users/me', {






                    headers: { 'Authorization': `Bearer ${token}` }






                });













                if (userData.role !== 'admin') {






                    window.location.href = 'campus-virtual.html';






                    return;






                }






                const adminDisplayName = userData.full_name || userData.username || 'Administrador';






                const adminInitials = adminDisplayName.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();






                document.getElementById('adminName').textContent = adminDisplayName;






                const sideAdminName = document.getElementById('sideAdminName');






                const sideAdminAvatar = document.getElementById('sideAdminAvatar');






                if (sideAdminName) sideAdminName.textContent = adminDisplayName;






                if (sideAdminAvatar) sideAdminAvatar.textContent = adminInitials || 'AD';













                await loadCatalogs();













                try {






                    const stats = await fetchJsonWithTimeout(API_BASE + '/admin/stats', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    });






                    document.getElementById('totalStudentsCount').textContent = stats.total_students;






                    document.getElementById('totalIncomeCount').textContent = `$${(stats.total_income / 1000).toFixed(1)}k`;






                    document.getElementById('pendingServicesCount').textContent = stats.pending_services;






                    document.getElementById('totalTeachersCount').textContent = stats.total_teachers;






                } catch (error) {






                    console.error('Error loading admin stats:', error);






                }













                try {






                    allStudents = await fetchJsonWithTimeout(API_BASE + '/admin/students', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    }, 20000);






                } catch (error) {






                    console.error('Error loading students:', error);






                    allStudents = [];






                }













                try {






                    allStudentEnrollments = await fetchJsonWithTimeout(API_BASE + '/admin/student-enrollments', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    }, 20000);






                } catch (error) {






                    console.error('Error loading student enrollments:', error);






                    allStudentEnrollments = [];






                }













                syncStudentsWithActiveEnrollments();






                syncCatalogsFromStudents();






                populateGroupFilter();






                filteredStudents = [...allStudents];






                filteredStudentEnrollments = [...allStudentEnrollments];






                renderStudents(filteredStudents);






                renderPagination();






                renderAdminCriticalQueue();













                try {






                    allTeachers = await fetchJsonWithTimeout(API_BASE + '/admin/teachers', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    });






                    filteredTeachers = [...allTeachers];






                    renderTeachers(filteredTeachers);






                    renderAdminCriticalQueue();






                } catch (error) {






                    console.error('Error loading teachers:', error);






                }













                try {






                    allSubjects = await fetchJsonWithTimeout(API_BASE + '/admin/subjects', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    });






                    filteredSubjects = [...allSubjects];






                    renderSubjects(filteredSubjects);






                    populateQuickPanelFilters();






                    renderQuickPanel();






                    renderAdminCriticalQueue();






                    renderDocentesBoard();






                } catch (error) {






                    console.error('Error loading subjects:', error);






                }













                try {






                    allPayments = await fetchJsonWithTimeout(API_BASE + '/admin/payments', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    }, 20000);






                    filteredPayments = [...allPayments];






                    renderPayments(filteredPayments);






                    renderAdminCriticalQueue();






                } catch (error) {






                    console.error('Error loading payments:', error);






                }













                try {






                    allCharges = await fetchJsonWithTimeout(API_BASE + '/admin/charges', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    }, 20000);






                    filteredCharges = [...allCharges];






                    renderCharges(filteredCharges);






                    renderAdminCriticalQueue();






                } catch (error) {






                    console.error('Error loading charges:', error);






                }













                try {






                    allServices = await fetchJsonWithTimeout(API_BASE + '/admin/services', {






                        headers: { 'Authorization': `Bearer ${token}` }






                    }, 20000);






                    filteredServices = [...allServices];






                    renderServices(filteredServices);






                    renderAdminCriticalQueue();






                    renderTramitesKanban();






                } catch (error) {






                    console.error('Error loading services:', error);






                    const t = document.getElementById('allServicesTableBody');






                    if (t) t.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger"><i class="bi bi-exclamation-triangle me-2"></i>Error al cargar Trámites. Recarga la página.</td></tr>';






                }













                try {






                    generateCharts();






                    calculateAcademicStats();






                } catch (error) {






                    console.error('Error generating charts:', error);






                }













                updateOfferSummary();






                try { await loadReportFilterOptions(); } catch (error) { console.error('Error loading report filters:', error); }






                try { await loadControlSchoolData(); } catch (error) { console.error('Error loading control school:', error); }






                try { await loadTreasuryView(); } catch (error) { console.error('Error loading treasury:', error); }






                try { await loadGradeCenter(); } catch (error) { console.error('Error loading grade center:', error); }






                try { await loadReportsDashboard(); } catch (error) { console.error('Error loading reports:', error); }






                try { await loadMoodleAdminView(); } catch (error) { console.error('Error loading Moodle admin:', error); }






                try { await loadAdminSupportTickets(); } catch (error) { console.error('Error loading support tickets:', error); }






                renderAdminCriticalQueue();






                runGlobalAuditor();













            } catch (error) {






                console.error("Error loading admin data:", error);






                if (String(error?.message || '').includes('401')) {






                    logout();






                } else {






                    const queue = document.getElementById('adminCriticalQueue');






                    if (queue) queue.innerHTML = '<div class="col-12"><div class="alert alert-danger rounded-3"><i class="bi bi-exclamation-triangle-fill me-2"></i>Error al cargar datos del sistema. <button class="btn btn-sm btn-danger ms-2" onclick="location.reload()">Recargar</button></div></div>';






                    const adminNameEl = document.getElementById('adminName');






                    if (adminNameEl) adminNameEl.textContent = 'Error de carga';






                    const sideAdminNameEl = document.getElementById('sideAdminName');






                    if (sideAdminNameEl) sideAdminNameEl.textContent = 'Error';






                    const tables = ['recentStudentsTableBody','allStudentsTableBody','allTeachersTableBody','allSubjectsTableBody','allPaymentsTableBody','allServicesTableBody'];






                    tables.forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = '<tr><td colspan="10" class="text-center py-3 text-danger"><i class="bi bi-exclamation-triangle me-1"></i>No se pudo cargar. <a href="#" onclick="loadAdminData();return false;">Reintentar</a></td></tr>'; });






                }






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













            renderSubjects(filteredSubjects);






        }













        function filterPayments() {






            const status = document.getElementById('filterPaymentStatus').value;













            filteredPayments = allPayments.filter(p => status === "" || p.status === status);






            renderPayments(filteredPayments);






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













            renderCharges(filteredCharges);






            filterPayments();






        }













        function filterServices() {






            const search = document.getElementById('filterServiceSearch').value.toLowerCase();






            const status = document.getElementById('filterServiceStatus').value;













            filteredServices = allServices.filter(s => {






                const studentName = s.student && s.student.full_name ? s.student.full_name.toLowerCase() : '';






                const studentUsername = s.student && s.student.username ? s.student.username.toLowerCase() : '';






                const type = s.type ? s.type.toLowerCase() : '';






                






                const matchSearch = studentName.includes(search) || studentUsername.includes(search) || type.includes(search);






                const matchStatus = status === "" || s.status === status;






                






                return matchSearch && matchStatus;






            });













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






                    ? `${student.full_name || 'Sin nombre'} Á€šA‚· ${student.carrera || 'Sin carrera'}`






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


