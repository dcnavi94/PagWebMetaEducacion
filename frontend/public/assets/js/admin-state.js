const token = localStorage.getItem('token');
        if (!token) window.location.href = 'login.html';

        let allStudents = [];
        let filteredStudents = [];
        let allTeachers = [];
        let filteredTeachers = [];
        let allSubjects = [];
        let filteredSubjects = [];
        let allCharges = [];
        let filteredCharges = [];
        let allServices = [];
        let filteredServices = [];
        let allSupportTickets = [];
        let filteredSupportTickets = [];
        let adminNotifications = [];
        let allStudentEnrollments = [];
        let filteredStudentEnrollments = [];
        let allGroupSummaries = [];
        let gradeOutcomeRows = [];
        let financeSummary = null;
        let blockedStudents = [];
        let reportDashboardData = {};
        let selectedGradeRows = [];
        let catalogCareers = [];
        let catalogModalities = [];
        let moodleHealth = null;
        let moodleFunctions = [];
        let currentMoodleCourseId = null;
        let currentMoodleGroups = [];
        let currentMoodlePanel = 'overview';
        let moodleCoursesListCache = [];
        let moodleGroupsListCache = [];
        let moodleAccountsCache = [];
        let moodleAccountsFiltered = [];
        let selectedMoodleAccountUsername = null;
        let webAdminData = {
            portfolioProjects: [],
            testimonialReels: [],
            successStories: [],
            communities: []
        };
        let moodleSearchHasResults = false;
        const selectedGroupMemberIds = new Set();
        const selectedGroupCourseIds = new Set();
        let currentPage = 1;
        const itemsPerPage = 10;
        const TABLE_PER_PAGE = 15;
        let teachersPage = 1, subjectsPage = 1, assignmentsPage = 1;
        let controlSchoolPage = 1, blockedPage = 1, chargesPage = 1;
        let servicesPage = 1, gradeRowsPage = 1, supportTicketsPage = 1;
        let filteredAssignments = [];
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
            { name: 'Ingenieria en Software' },
            { name: 'Ingenieria en Telematica' },
            { name: 'Bachillerato' },
            { name: 'Cursos' },
            { name: 'Capacitacion' }
        ];
        const DEFAULT_MODALITIES = [
            { name: 'Presencial Intensiva' },
            { name: 'Presencial Sabatino' },
            { name: 'Virtual' }
        ];

        async function loadCatalogs() {
            try {
                const [careersResponse, modalitiesResponse] = await Promise.all([
                    fetch('/catalogs/careers', { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch('/catalogs/modalities', { headers: { 'Authorization': `Bearer ${token}` } })
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
            // Solo usa defaults como fallback si el API aun no devolvio datos
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

        function normalizeCareerToTrack(careerName) {
            const key = (careerName || '').toLowerCase();
            if (key.includes('software')) return 'Ingeniería en Software';
            if (key.includes('telem')) return 'Ingeniería en Telemática';
            if (key.includes('prep') || key.includes('bach')) return 'Bachillerato';
            if (key.includes('capacit')) return 'Capacitación';
            if (key.includes('curso')) return 'Cursos';
            return '';
        }

        function syncTrackSelectWithCareer(careerSelectId, trackSelectId) {
            const careerSelect = document.getElementById(careerSelectId);
            const trackSelect = document.getElementById(trackSelectId);
            if (!careerSelect || !trackSelect) return;
            const current = trackSelect.value?.trim();
            if (current) return;
            const mapped = normalizeCareerToTrack(careerSelect.selectedOptions?.[0]?.textContent || '');
            if (mapped) {
                trackSelect.value = mapped;
            }
        }

        function formatMoney(amount) {
            return new Intl.NumberFormat('es-MX', {
                style: 'currency',
                currency: 'MXN'
            }).format(Number(amount || 0));
        }

        function formatDateShort(value) {
            if (!value) return '?';
            return new Date(value).toLocaleDateString('es-MX', { year: 'numeric', month: 'short', day: 'numeric' });
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, (char) => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }[char]));
        }

        function getNotificationUiMeta(item = {}) {
            const type = item.type || '';
            const level = item.level || 'info';
            const byType = {
                finance: { icon: 'bi-wallet2', tone: 'warning' },
                services: { icon: 'bi-folder-check', tone: 'warning' },
                support: { icon: 'bi-headset', tone: 'warning' },
                admin_message: { icon: 'bi-megaphone', tone: 'primary' }
            };
            const fallbackTone = level === 'danger' ? 'danger' : level === 'warning' ? 'warning' : level === 'success' ? 'success' : 'primary';
            return byType[type] || { icon: level === 'danger' ? 'bi-exclamation-octagon' : 'bi-info-circle', tone: fallbackTone };
        }

        function renderSystemAlerts(items = []) {
            const container = document.getElementById('systemAlertsList');
            if (!container) return;
            if (!items.length) {
                container.innerHTML = `
                    <div class="d-flex gap-3 align-items-start">
                        <div class="bg-success bg-opacity-10 text-success p-2 rounded-3 h-100">
                            <i class="bi bi-check-circle fs-5"></i>
                        </div>
                        <div>
                            <h6 class="fw-bold mb-1">Sin alertas activas</h6>
                            <p class="text-muted small mb-0">No hay tramites, cartera vencida, tickets o mensajes recientes que requieran atencion.</p>
                        </div>
                    </div>
                `;
                return;
            }
            container.innerHTML = items.slice(0, 5).map((item, index) => {
                const meta = getNotificationUiMeta(item);
                const marginClass = index === Math.min(items.length, 5) - 1 ? '' : 'mb-4';
                const source = item.source ? `<div class="small text-secondary mt-1">${escapeHtml(item.source)}</div>` : '';
                let statusBadge = '';
                if (item.deleted_by_recipient) {
                    statusBadge = '<span class="badge bg-danger-subtle text-danger border ms-2">Eliminado por alumno</span>';
                } else if (item.read_by_recipient) {
                    statusBadge = '<span class="badge bg-success-subtle text-success border ms-2">Leído</span>';
                }
                return `
                    <div class="d-flex gap-3 ${marginClass}">
                        <div class="bg-${meta.tone} bg-opacity-10 text-${meta.tone} p-2 rounded-3 h-100">
                            <i class="bi ${meta.icon} fs-5"></i>
                        </div>
                        <div>
                            <h6 class="fw-bold mb-1">${escapeHtml(item.title || 'Alerta del sistema')}${statusBadge}</h6>
                            <p class="text-muted small mb-0">${escapeHtml(item.message || '')}</p>
                            ${source}
                        </div>
                    </div>
                `;
            }).join('');
        }

        function fixMojibakeString(input) {
            if (typeof input !== 'string' || !input) return input;
            if (!/[\u00c3\u00c2\u00e2]/.test(input)) return input;
            try {
                return decodeURIComponent(escape(input));
            } catch (_) {
                return input;
            }
        }

        function fixMojibakeInDom(root = document.body) {
            if (!root) return;
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            const textNodes = [];
            while (walker.nextNode()) textNodes.push(walker.currentNode);
            textNodes.forEach((node) => {
                const fixed = fixMojibakeString(node.nodeValue);
                if (fixed !== node.nodeValue) node.nodeValue = fixed;
            });

            root.querySelectorAll('[title], [placeholder], [aria-label]').forEach((el) => {
                ['title', 'placeholder', 'aria-label'].forEach((attr) => {
                    const value = el.getAttribute(attr);
                    if (!value) return;
                    const fixed = fixMojibakeString(value);
                    if (fixed !== value) el.setAttribute(attr, fixed);
                });
            });
        }

        function renderPaymentStatusBadge(status) {
            if (status === 'Pagado') return '<span class="badge bg-success">Pagado</span>';
            if (status === 'Vencido') return '<span class="badge bg-danger">Vencido</span>';
            return '<span class="badge bg-warning text-dark">Pendiente</span>';
        }

        function normalizeGradeStatus(score, status) {
            if (status && status !== 'Cursando') return status;
            if (score === '' || score === null || score === undefined) return 'Cursando';
            const numericScore = parseFloat(score);
            if (Number.isNaN(numericScore)) return 'Cursando';
            return numericScore >= 6 ? 'Aprobada' : 'Reprobada';
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
