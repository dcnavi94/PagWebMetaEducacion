        function renderViewedStudentMoodleStatus(student) {
            const statusEl = document.getElementById('viewStudentMoodleStatus');
            const syncButton = document.getElementById('viewStudentMoodleSyncButton');
            const enrollButton = document.getElementById('viewStudentMoodleEnrollButton');
            if (!statusEl || !syncButton || !enrollButton) return;

            if (student?.moodle_id) {
                statusEl.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle">Vinculado · ID ${student.moodle_id}</span>`;
                syncButton.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Validar vínculo Moodle';
                enrollButton.disabled = false;
            } else {
                statusEl.innerHTML = '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Sin vínculo Moodle</span>';
                syncButton.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Sincronizar con Moodle';
                enrollButton.disabled = true;
            }
        }

        async function syncStudentMoodle(username, reloadAfter = false) {
            try {
                const response = await fetch(`/admin/students/${username}/moodle-sync`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo sincronizar el alumno con Moodle'), true);
                    return false;
                }
                const result = await response.json();
                showToast(result.message || 'Alumno sincronizado con Moodle');
                await reloadStudents();
                if (reloadAfter) await openViewStudent(username);
                return true;
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al sincronizar alumno con Moodle', true);
                return false;
            }
        }

        async function syncViewedStudentMoodle() {
            const username = document.getElementById('viewStudentUsername').textContent;
            if (!username) return;
            await syncStudentMoodle(username, true);
        }

        async function syncTeacherMoodle(username, reloadAfter = false) {
            try {
                const response = await fetch(`/admin/teachers/${username}/moodle-sync`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo sincronizar el docente con Moodle'), true);
                    return false;
                }
                const result = await response.json();
                showToast(result.message || 'Docente sincronizado con Moodle');
                await loadAdminData();
                if (reloadAfter) openViewTeacher(username);
                return true;
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al sincronizar docente con Moodle', true);
                return false;
            }
        }

        async function linkViewedStudentMoodleManual() {
            const username = document.getElementById('viewStudentUsername').textContent;
            if (!username) return;

            const moodleUserIdRaw = prompt(`Ingresa el Moodle User ID existente para vincular al alumno ${username}:`);
            if (!moodleUserIdRaw) return;
            const moodleUserId = parseInt(moodleUserIdRaw, 10);
            if (!moodleUserId) {
                showToast('Moodle User ID inválido', true);
                return;
            }

            try {
                const response = await fetch(`/admin/students/${username}/moodle-link`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ moodle_user_id: moodleUserId }),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo vincular manualmente el alumno con Moodle'), true);
                    return;
                }
                const result = await response.json();
                showToast(result.message || 'Vínculo manual con Moodle completado');
                await reloadStudents();
                await openViewStudent(username);
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al vincular Moodle ID manual', true);
            }
        }

        async function syncSubjectMoodle(subjectId) {
            try {
                const response = await fetch(`/admin/subjects/${subjectId}/moodle-sync`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo sincronizar la materia con Moodle'), true);
                    return;
                }
                const result = await response.json();
                showToast(result.message || 'Materia sincronizada con Moodle');
                loadAdminData();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al sincronizar materia con Moodle', true);
            }
        }

        function openMoodleEnrollModal(username) {
            document.getElementById('moodleEnrollStudentUsername').value = username;
            document.getElementById('moodleEnrollStudentUsernameDisplay').textContent = username;
            const select = document.getElementById('moodleEnrollSubjectId');
            const syncedSubjects = (allSubjects || []).filter(subject => Boolean(subject.moodle_course_id));
            if (!syncedSubjects.length) {
                select.innerHTML = '<option value="">No hay materias sincronizadas con Moodle</option>';
            } else {
                select.innerHTML = '<option value="">Seleccionar materia sincronizada...</option>' + syncedSubjects.map(subject =>
                    `<option value="${subject.id}">${subject.name} · Course #${subject.moodle_course_id}</option>`
                ).join('');
            }
            new bootstrap.Modal(document.getElementById('moodleEnrollModal')).show();
        }

        async function doMoodleEnrollStudent() {
            const username = document.getElementById('moodleEnrollStudentUsername').value;
            const subjectId = parseInt(document.getElementById('moodleEnrollSubjectId').value, 10);
            if (!subjectId) {
                showToast('Selecciona una materia sincronizada con Moodle', true);
                return;
            }

            try {
                const response = await fetch(`/admin/students/${username}/enroll-moodle`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ subject_id: subjectId })
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo inscribir al alumno en Moodle'), true);
                    return;
                }
                const result = await response.json();
                showToast(result.message || 'Alumno inscrito en Moodle');
                bootstrap.Modal.getInstance(document.getElementById('moodleEnrollModal')).hide();
                await openViewStudent(username);
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al inscribir en Moodle', true);
            }
        }

        function switchMoodlePanel(panel) {
            currentMoodlePanel = panel;
            const blocks = {
                overview: ['moodleBlockOverview'],
                tokens: ['moodleBlockTokens', 'moodleBlockTokenFunctions'],
                courses: ['moodleBlockCourses'],
                groups: ['moodleBlockGroups'],
                accounts: ['moodleBlockAccounts'],
                sync: ['moodleBlockSync', 'moodleBlockSyncResults']
            };
            const allBlockIds = [
                'moodleBlockOverview',
                'moodleBlockTokens',
                'moodleBlockCourses',
                'moodleBlockGroups',
                'moodleBlockAccounts',
                'moodleBlockSync',
                'moodleBlockSyncResults',
                'moodleBlockTokenFunctions'
            ];

            allBlockIds.forEach(id => {
                const el = document.getElementById(id);
                if (!el) return;
                const shouldShow = (blocks[panel] || []).includes(id);
                el.style.display = shouldShow ? '' : 'none';
            });

            const searchResultsBlock = document.getElementById('moodleBlockOverviewSearchResults');
            if (searchResultsBlock) {
                searchResultsBlock.style.display = (panel === 'overview' && moodleSearchHasResults) ? '' : 'none';
            }

            document.querySelectorAll('[data-moodle-nav]').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-moodle-nav') === panel);
            });

            if (panel === 'courses') {
                loadMoodleCoursesList();
            } else if (panel === 'groups') {
                loadMoodleGroupsList();
            } else if (panel === 'accounts') {
                loadMoodleAccounts();
            }
        }

        async function loadAdminSupportTickets() {
            const table = document.getElementById('adminSupportTicketsTableBody');
            if (table) {
                table.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">Cargando tickets...</td></tr>';
            }
            try {
                const response = await fetch('/admin/support-tickets', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudieron cargar tickets de soporte');
                    if (table) table.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    return;
                }
                allSupportTickets = await response.json();
                filteredSupportTickets = [...allSupportTickets];
                renderAdminSupportTickets(filteredSupportTickets);
            } catch (error) {
                console.error(error);
                if (table) table.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Error de conexión al cargar tickets.</td></tr>';
            }
        }

        async function loadAdminNotifications(showToastOnSuccess = false) {
            const badge = document.getElementById('adminNoticeCount');
            const list = document.getElementById('adminNotificationList');
            if (list) list.innerHTML = '<div class="small text-muted px-2 py-2">Cargando notificaciones...</div>';
            const systemAlerts = document.getElementById('systemAlertsList');
            if (systemAlerts) systemAlerts.innerHTML = '<div class="small text-muted">Cargando alertas reales del sistema...</div>';
            try {
                const response = await fetch('/admin/notifications', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) throw new Error('No se pudieron cargar notificaciones');
                const payload = await response.json();
                adminNotifications = payload.items || [];
                if (badge) badge.textContent = String(adminNotifications.length);
                renderSystemAlerts(adminNotifications);
                if (list) {
                    list.innerHTML = adminNotifications.length
                        ? adminNotifications.map(item => {
                            const level = item.level || 'info';
                            const levelClass = level === 'danger' ? 'text-danger' : level === 'warning' ? 'text-warning' : level === 'success' ? 'text-success' : 'text-primary';
                            return `
                                <div class="px-2 py-2 border-bottom">
                                    <div class="fw-semibold ${levelClass}">${escapeHtml(item.title || 'Notificacion')}</div>
                                    <div class="small text-muted">${escapeHtml(item.message || '')}</div>
                                    <div class="small text-secondary">${escapeHtml(item.source || 'Sistema')}</div>
                                </div>
                            `;
                        }).join('')
                        : '<div class="small text-muted px-2 py-2">Sin notificaciones por ahora.</div>';
                }
                if (showToastOnSuccess) showToast('Notificaciones actualizadas');
            } catch (error) {
                console.error(error);
                if (badge) badge.textContent = '0';
                if (list) list.innerHTML = '<div class="small text-danger px-2 py-2">Error al cargar notificaciones.</div>';
                if (systemAlerts) {
                    systemAlerts.innerHTML = `
                        <div class="d-flex gap-3 align-items-start">
                            <div class="bg-danger bg-opacity-10 text-danger p-2 rounded-3 h-100">
                                <i class="bi bi-wifi-off fs-5"></i>
                            </div>
                            <div>
                                <h6 class="fw-bold mb-1">No se pudieron cargar las alertas</h6>
                                <p class="text-muted small mb-0">Revisa la conexion con el servidor e intenta actualizar de nuevo.</p>
                            </div>
                        </div>
                    `;
                }
            }
        }

        function renderAdminSupportTickets(tickets) {
            const table = document.getElementById('adminSupportTicketsTableBody');
            if (!table) return;
            if (!tickets.length) {
                table.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No hay tickets de soporte.</td></tr>';
                buildTablePagination('support-tickets-pagination', 'support-tickets-info', 1, 0, TABLE_PER_PAGE, 'changeSupportTicketsPage');
                return;
            }
            const start = (supportTicketsPage - 1) * TABLE_PER_PAGE;
            const page  = tickets.slice(start, start + TABLE_PER_PAGE);
            table.innerHTML = page.map(ticket => {
                let badgeClass = 'bg-secondary';
                if (ticket.status === 'Entregado') badgeClass = 'bg-success';
                if (ticket.status === 'Listo') badgeClass = 'bg-info text-dark';
                if (ticket.status === 'En Proceso') badgeClass = 'bg-warning text-dark';
                const studentUsername = ticket.student?.username || 'N/A';
                const studentName = ticket.student?.full_name || 'Alumno';
                const source  = ticket.source_system || 'Plataforma';
                const subject = ticket.subject || ticket.type || 'Ticket de soporte';
                const date    = ticket.request_date ? new Date(ticket.request_date).toLocaleDateString('es-MX') : '-';
                return `<tr>
                    <td class="fw-bold">${ticket.id}</td>
                    <td><div class="fw-semibold">${studentUsername}</div><div class="small text-muted">${studentName}</div></td>
                    <td>${source}</td>
                    <td>${subject}</td>
                    <td><span class="badge ${badgeClass}">${ticket.status || 'Sin estatus'}</span></td>
                    <td>${date}</td>
                    <td><button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openAdminSupportTicket(${ticket.id})">Atender</button></td>
                </tr>`;
            }).join('');
            buildTablePagination('support-tickets-pagination', 'support-tickets-info', supportTicketsPage, tickets.length, TABLE_PER_PAGE, 'changeSupportTicketsPage');
        }

        function filterAdminSupportTickets() {
            const search = (document.getElementById('supportTicketSearch')?.value || '').toLowerCase().trim();
            const status = document.getElementById('supportTicketStatusFilter')?.value || '';
            const source = document.getElementById('supportTicketSourceFilter')?.value || '';
            filteredSupportTickets = allSupportTickets.filter(ticket => {
                const student = `${ticket.student?.username || ''} ${ticket.student?.full_name || ''}`.toLowerCase();
                const subject = `${ticket.subject || ''} ${ticket.type || ''}`.toLowerCase();
                const ticketSource = (ticket.source_system || '').toLowerCase();
                const matchSearch = !search || student.includes(search) || subject.includes(search) || ticketSource.includes(search);
                const matchStatus = !status || ticket.status === status;
                const matchSource = !source || (ticket.source_system || '') === source;
                return matchSearch && matchStatus && matchSource;
            });
            supportTicketsPage = 1;
            renderAdminSupportTickets(filteredSupportTickets);
        }

        function resetAdminSupportTicketFilters() {
            const search = document.getElementById('supportTicketSearch');
            const status = document.getElementById('supportTicketStatusFilter');
            const source = document.getElementById('supportTicketSourceFilter');
            if (search) search.value = '';
            if (status) status.value = '';
            if (source) source.value = '';
            filteredSupportTickets = [...allSupportTickets];
            renderAdminSupportTickets(filteredSupportTickets);
        }

        function openAdminSupportTicket(ticketId) {
            const ticket = allSupportTickets.find(item => item.id === ticketId);
            if (!ticket) return;
            document.getElementById('adminSupportTicketId').value = String(ticket.id);
            document.getElementById('adminSupportTicketIdView').value = String(ticket.id);
            document.getElementById('adminSupportTicketStudent').value = `${ticket.student?.username || 'N/A'} · ${ticket.student?.full_name || 'Alumno'}`;
            document.getElementById('adminSupportTicketSource').value = ticket.source_system || 'Plataforma';
            document.getElementById('adminSupportTicketSubject').value = ticket.subject || ticket.type || '';
            document.getElementById('adminSupportTicketDescription').value = ticket.description || 'Sin descripción';
            document.getElementById('adminSupportTicketStatus').value = ticket.status || 'En Proceso';
            document.getElementById('adminSupportTicketResponse').value = ticket.admin_response || '';
            document.getElementById('adminSupportTicketClose').checked = false;

            const history = Array.isArray(ticket.history) ? ticket.history : [];
            const historyContainer = document.getElementById('adminSupportTicketHistory');
            if (historyContainer) {
                historyContainer.innerHTML = history.length
                    ? history.map(item => `<div class="mb-2"><div class="fw-semibold">${item.actor || 'Sistema'} · ${item.action || 'evento'}</div><div class="small text-muted">${item.message || '-'}</div><div class="small text-secondary">${item.timestamp ? new Date(item.timestamp).toLocaleString('es-MX') : '-'}</div></div>`).join('')
                    : '<div class="text-muted">Sin historial.</div>';
            }
            bootstrap.Modal.getOrCreateInstance(document.getElementById('adminSupportTicketModal')).show();
        }

        async function saveAdminSupportTicket() {
            const ticketId = Number.parseInt(document.getElementById('adminSupportTicketId')?.value || '', 10);
            if (!ticketId) return;
            const payload = {
                status: document.getElementById('adminSupportTicketStatus')?.value || 'En Proceso',
                admin_response: document.getElementById('adminSupportTicketResponse')?.value?.trim() || null,
                close_ticket: Boolean(document.getElementById('adminSupportTicketClose')?.checked),
            };
            try {
                const response = await fetch(`/admin/support-tickets/${ticketId}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo actualizar el ticket'), true);
                    return;
                }
                showToast('Ticket actualizado correctamente');
                bootstrap.Modal.getInstance(document.getElementById('adminSupportTicketModal'))?.hide();
                await loadAdminSupportTickets();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al actualizar ticket', true);
            }
        }

        function toLowerSafe(value) {
            return (value || '').toString().toLowerCase();
        }

        function escapeJsSingleQuoted(value) {
            return String(value || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        }

        function setOverviewSearchPlaceholder() {
            const studentsBody = document.getElementById('moodleSearchStudentsTableBody');
            const teachersBody = document.getElementById('moodleSearchTeachersTableBody');
            const groupsBody = document.getElementById('moodleSearchGroupsTableBody');
            const coursesBody = document.getElementById('moodleSearchCoursesTableBody');
            if (studentsBody) studentsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin búsqueda aún.</td></tr>';
            if (teachersBody) teachersBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin búsqueda aún.</td></tr>';
            if (groupsBody) groupsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin búsqueda aún.</td></tr>';
            if (coursesBody) coursesBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin búsqueda aún.</td></tr>';
        }

        function goToMoodleSite() {
            const url = moodleHealth?.public_url || 'http://localhost:8080';
            window.open(url, '_blank');
        }

        function renderMoodleKpis() {
            const linkedStudents = (allStudents || []).filter(student => Boolean(student.moodle_id)).length;
            const linkedSubjects = (allSubjects || []).filter(subject => Boolean(subject.moodle_course_id)).length;
            document.getElementById('moodleLinkedStudents').textContent = linkedStudents;
            document.getElementById('moodleLinkedSubjects').textContent = linkedSubjects;
            const groupsCountEl = document.getElementById('moodleGroupsCreatedCount');
            if (groupsCountEl) groupsCountEl.textContent = String((moodleGroupsListCache || []).length);
        }

        async function loadMoodleHealth() {
            try {
                const response = await fetch('/admin/moodle/health', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const errorMessage = await extractApiErrorMessage(response, 'No se pudo validar la conectividad con Moodle');
                    document.getElementById('moodleHealthStatus').textContent = 'Error';
                    const connectionStatusEl = document.getElementById('moodleConnectionStatusText');
                    if (connectionStatusEl) {
                        connectionStatusEl.textContent = 'Error';
                        connectionStatusEl.className = 'fw-bold mb-0 text-danger';
                    }
                    document.getElementById('moodleConnectionInfo').innerHTML = `<span class="text-danger">${errorMessage}</span>`;
                    return;
                }

                moodleHealth = await response.json();
                const status = moodleHealth.connected ? 'Conectado' : 'Sin conexión';
                document.getElementById('moodleHealthStatus').textContent = status;
                document.getElementById('moodleHealthStatus').className = moodleHealth.connected ? 'fw-bold text-success' : 'fw-bold text-danger';
                const connectionStatusEl = document.getElementById('moodleConnectionStatusText');
                if (connectionStatusEl) {
                    connectionStatusEl.textContent = status;
                    connectionStatusEl.className = moodleHealth.connected ? 'fw-bold mb-0 text-success' : 'fw-bold mb-0 text-danger';
                }
                document.getElementById('moodleConnectionInfo').innerHTML = `
                    <div><strong>Base URL:</strong> ${moodleHealth.base_url || '-'}</div>
                    <div><strong>Public URL:</strong> ${moodleHealth.public_url || '-'}</div>
                    <div><strong>Sitio:</strong> ${moodleHealth.site_name || 'No disponible'}</div>
                    <div><strong>Usuario token:</strong> ${moodleHealth.username || 'No disponible'}</div>
                    ${moodleHealth.last_error ? `<div class="text-danger mt-2"><strong>Error:</strong> ${moodleHealth.last_error}</div>` : ''}
                `;
                document.getElementById('moodleFunctionsCount').textContent = moodleHealth.functions_count || 0;
            } catch (error) {
                console.error(error);
                document.getElementById('moodleHealthStatus').textContent = 'Error';
                const connectionStatusEl = document.getElementById('moodleConnectionStatusText');
                if (connectionStatusEl) {
                    connectionStatusEl.textContent = 'Error';
                    connectionStatusEl.className = 'fw-bold mb-0 text-danger';
                }
                document.getElementById('moodleConnectionInfo').innerHTML = '<span class="text-danger">Error de conexión al consultar Moodle</span>';
            }
        }

        async function loadMoodleFunctions() {
            const tbody = document.getElementById('moodleFunctionsTableBody');
            tbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Cargando funciones...</td></tr>';
            try {
                const response = await fetch('/admin/moodle/functions', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudieron cargar funciones de Moodle');
                    tbody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    return;
                }

                const payload = await response.json();
                moodleFunctions = payload.functions || [];
                document.getElementById('moodleFunctionsCount').textContent = payload.count || 0;
                if (!moodleFunctions.length) {
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">El token no devolvió funciones.</td></tr>';
                    return;
                }

                const functionDescriptions = {
                    'core_user_get_users': 'Busca usuarios en Moodle por nombre, usuario o correo.',
                    'core_user_create_users': 'Crea usuarios en Moodle.',
                    'core_user_update_users': 'Actualiza datos de usuario y contraseña en Moodle.',
                    'core_course_search_courses': 'Consulta cursos existentes en Moodle.',
                    'core_course_get_contents': 'Devuelve secciones y módulos de un curso.',
                    'core_enrol_get_enrolled_users': 'Lista los usuarios inscritos en un curso.',
                    'core_course_create_courses': 'Crea cursos nuevos en Moodle.',
                    'core_course_update_courses': 'Actualiza datos de cursos existentes.',
                    'core_course_delete_courses': 'Elimina cursos de Moodle.',
                    'core_group_get_course_groups': 'Consulta grupos creados dentro de un curso.',
                    'core_group_create_groups': 'Crea grupos dentro de un curso.',
                    'core_group_update_groups': 'Edita nombre/descripcion de grupos.',
                    'core_group_delete_groups': 'Elimina grupos de un curso.',
                    'core_group_add_group_members': 'Agrega usuarios a grupos.',
                    'core_group_delete_group_members': 'Quita usuarios de grupos.',
                    'enrol_manual_enrol_users': 'Matrícula manual de usuarios en cursos.',
                    'core_role_assign_roles': 'Asigna roles como estudiante o profesor.',
                };
                const inferFunctionDescription = (name) => {
                    if (!name) return 'No hay información disponible.';
                    if (functionDescriptions[name]) return functionDescriptions[name];
                    if (name.includes('group') && name.includes('create')) return 'Función para crear entidades de grupo en Moodle.';
                    if (name.includes('group') && name.includes('update')) return 'Función para actualizar grupos en Moodle.';
                    if (name.includes('group') && name.includes('delete')) return 'Función para eliminar grupos en Moodle.';
                    if (name.includes('course') && name.includes('create')) return 'Función para crear cursos en Moodle.';
                    if (name.includes('course') && name.includes('update')) return 'Función para editar cursos en Moodle.';
                    if (name.includes('course') && name.includes('delete')) return 'Función para eliminar cursos en Moodle.';
                    if (name.includes('course') && name.includes('get')) return 'Función para consultar información de cursos.';
                    if (name.includes('user') && name.includes('get')) return 'Función para consultar usuarios en Moodle.';
                    if (name.includes('enrol') || name.includes('enroll')) return 'Función relacionada con matrículas de usuarios.';
                    if (name.includes('role')) return 'Función relacionada con asignación o consulta de roles.';
                    return 'No hay información disponible.';
                };

                tbody.innerHTML = moodleFunctions.map((fn, idx) => `
                    <tr>
                        <td>${idx + 1}</td>
                        <td class="fw-semibold">${fn.name || JSON.stringify(fn)}</td>
                        <td>${inferFunctionDescription(fn.name || '')}</td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error(error);
                tbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión al cargar funciones</td></tr>';
            }
        }

        function renderMoodleAccountsTable(items = []) {
            const tbody = document.getElementById('moodleAccountsTableBody');
            if (!tbody) return;
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No hay usuarios para mostrar.</td></tr>';
                return;
            }
            tbody.innerHTML = items.map(item => {
                const roleLabel = item.role === 'teacher' ? 'Docente' : item.role === 'student' ? 'Alumno' : item.role;
                const passText = item.moodle_password ? item.moodle_password : 'No configurada';
                return `
                    <tr>
                        <td><div class="fw-semibold">${item.username || '-'}</div><div class="small text-muted">${item.full_name || '-'}</div></td>
                        <td>${roleLabel || '-'}</td>
                        <td>${item.moodle_id || '-'}</td>
                        <td>${item.moodle_username || '-'}</td>
                        <td><code>${passText}</code></td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="selectMoodleAccount('${escapeJsSingleQuoted(item.username)}')">Configurar</button>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        async function loadMoodleAccounts() {
            const tbody = document.getElementById('moodleAccountsTableBody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">Cargando usuarios Moodle...</td></tr>';
            try {
                const response = await fetch('/admin/moodle/user-credentials?limit=300', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudieron cargar credenciales Moodle');
                    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    return;
                }
                const payload = await response.json();
                moodleAccountsCache = payload.items || [];
                moodleAccountsFiltered = [...moodleAccountsCache];
                renderMoodleAccountsTable(moodleAccountsFiltered);
            } catch (error) {
                console.error(error);
                if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Error de conexión cargando usuarios Moodle.</td></tr>';
            }
        }

        function filterMoodleAccounts() {
            const query = (document.getElementById('moodleAccountsSearch')?.value || '').trim().toLowerCase();
            moodleAccountsFiltered = (moodleAccountsCache || []).filter(item => {
                if (!query) return true;
                const haystack = `${item.username || ''} ${item.full_name || ''} ${item.email || ''} ${item.moodle_username || ''}`.toLowerCase();
                return haystack.includes(query);
            });
            renderMoodleAccountsTable(moodleAccountsFiltered);
        }

        function selectMoodleAccount(username) {
            const selected = (moodleAccountsCache || []).find(item => item.username === username);
            if (!selected) return;
            selectedMoodleAccountUsername = selected.username;
            document.getElementById('moodleCredLocalUsername').value = selected.username || '';
            document.getElementById('moodleCredUsername').value = selected.moodle_username || (selected.username || '').toLowerCase();
            document.getElementById('moodleCredPassword').value = selected.moodle_password || '';
            document.getElementById('moodleCredInfo').textContent = `Usuario ${selected.username} · Moodle ID: ${selected.moodle_id || 'sin vínculo'} · Rol: ${selected.role || '-'}`;
        }

        async function saveMoodleCredential() {
            const localUsername = (document.getElementById('moodleCredLocalUsername')?.value || '').trim();
            const moodleUsername = (document.getElementById('moodleCredUsername')?.value || '').trim();
            const moodlePassword = (document.getElementById('moodleCredPassword')?.value || '').trim();
            const syncIfMissing = Boolean(document.getElementById('moodleCredSyncIfMissing')?.checked);
            const createIfMissing = Boolean(document.getElementById('moodleCredCreateIfMissing')?.checked);
            if (!localUsername) {
                showToast('Selecciona un usuario de la tabla primero', true);
                return;
            }
            if (!moodleUsername || !moodlePassword) {
                showToast('Completa usuario y contraseña Moodle', true);
                return;
            }
            const strongPassword = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])\S{8,72}$/;
            if (!strongPassword.test(moodlePassword)) {
                showToast('La contraseña debe ser fuerte (8+, mayúscula, minúscula, número y símbolo)', true);
                return;
            }
            try {
                const response = await fetch(`/admin/moodle/user-credentials/${encodeURIComponent(localUsername)}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        moodle_username: moodleUsername,
                        moodle_password: moodlePassword,
                        sync_if_missing: syncIfMissing,
                        create_if_missing: createIfMissing,
                    }),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo actualizar credenciales Moodle'), true);
                    return;
                }
                showToast('Credenciales Moodle guardadas correctamente');
                await loadMoodleAccounts();
                selectMoodleAccount(localUsername);
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al guardar credenciales Moodle', true);
            }
        }

        async function runMoodleSearch() {
            const query = document.getElementById('moodleSearchQuery').value.trim();
            const studentsBody = document.getElementById('moodleSearchStudentsTableBody');
            const teachersBody = document.getElementById('moodleSearchTeachersTableBody');
            const groupsBody = document.getElementById('moodleSearchGroupsTableBody');
            const coursesBody = document.getElementById('moodleSearchCoursesTableBody');
            const searchResultsBlock = document.getElementById('moodleBlockOverviewSearchResults');

            if (!query) {
                moodleSearchHasResults = false;
                if (searchResultsBlock) searchResultsBlock.style.display = 'none';
                setOverviewSearchPlaceholder();
                showToast('Escribe un criterio para buscar en Moodle', true);
                return;
            }

            studentsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Consultando alumnos...</td></tr>';
            teachersBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Consultando profesores...</td></tr>';
            groupsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Consultando grupos...</td></tr>';
            coursesBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Consultando cursos...</td></tr>';
            moodleSearchHasResults = true;
            if (currentMoodlePanel === 'overview' && searchResultsBlock) searchResultsBlock.style.display = '';

            try {
                const [usersRes, coursesRes] = await Promise.all([
                    fetch(`/admin/moodle/users?q=${encodeURIComponent(query)}`, { headers: { 'Authorization': `Bearer ${token}` } }),
                    fetch(`/admin/moodle/courses?q=${encodeURIComponent(query)}`, { headers: { 'Authorization': `Bearer ${token}` } }),
                ]);

                let users = [];
                if (usersRes.ok) {
                    const usersPayload = await usersRes.json();
                    users = usersPayload.users || [];
                } else {
                    const msg = await extractApiErrorMessage(usersRes, 'Error consultando usuarios');
                    studentsBody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    teachersBody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-danger">${msg}</td></tr>`;
                }

                let courses = [];
                if (coursesRes.ok) {
                    const coursesPayload = await coursesRes.json();
                    courses = coursesPayload.courses || [];
                } else {
                    coursesBody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-danger">${await extractApiErrorMessage(coursesRes, 'Error consultando cursos')}</td></tr>`;
                }

                if (usersRes.ok) {
                    const studentByMoodleId = new Map((allStudents || []).filter(s => s.moodle_id).map(s => [String(s.moodle_id), s]));
                    const teacherByMoodleId = new Map((allTeachers || []).filter(t => t.moodle_id).map(t => [String(t.moodle_id), t]));
                    const studentUsernames = new Set((allStudents || []).map(s => toLowerSafe(s.username)));
                    const teacherUsernames = new Set((allTeachers || []).map(t => toLowerSafe(t.username)));
                    const studentEmails = new Set((allStudents || []).map(s => toLowerSafe(s.email)));
                    const teacherEmails = new Set((allTeachers || []).map(t => toLowerSafe(t.email)));

                    const studentUsers = users.filter(user => {
                        const key = String(user.id || '');
                        return studentByMoodleId.has(key)
                            || studentUsernames.has(toLowerSafe(user.username))
                            || studentEmails.has(toLowerSafe(user.email));
                    });
                    const teacherUsers = users.filter(user => {
                        const key = String(user.id || '');
                        return teacherByMoodleId.has(key)
                            || teacherUsernames.has(toLowerSafe(user.username))
                            || teacherEmails.has(toLowerSafe(user.email));
                    });

                    studentsBody.innerHTML = studentUsers.length
                        ? studentUsers.map(user => `<tr><td>${user.id || '-'}</td><td>${user.username || '-'}</td><td>${user.fullname || '-'}</td></tr>`).join('')
                        : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin alumnos Moodle para este criterio.</td></tr>';

                    teachersBody.innerHTML = teacherUsers.length
                        ? teacherUsers.map(user => `<tr><td>${user.id || '-'}</td><td>${user.username || '-'}</td><td>${user.fullname || '-'}</td></tr>`).join('')
                        : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin profesores Moodle para este criterio.</td></tr>';
                }

                if (coursesRes.ok) {
                    coursesBody.innerHTML = courses.length
                        ? courses.map(course => `<tr><td>${course.id || '-'}</td><td>${course.displayname || course.fullname || '-'}</td><td>${course.shortname || '-'}</td></tr>`).join('')
                        : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin cursos para este criterio.</td></tr>';
                }

                if (coursesRes.ok && courses.length) {
                    const groupsRequests = courses.map(course =>
                        fetch(`/admin/moodle/courses/${course.id}/groups`, { headers: { 'Authorization': `Bearer ${token}` } })
                            .then(async response => {
                                if (!response.ok) return [];
                                const payload = await response.json();
                                return (payload.groups || []).map(group => ({ ...group, course_name: course.displayname || course.fullname || `Curso ${course.id}` }));
                            })
                            .catch(() => [])
                    );
                    const groupsNested = await Promise.all(groupsRequests);
                    const groups = groupsNested.flat().filter(group => toLowerSafe(group.name).includes(toLowerSafe(query)));
                    groupsBody.innerHTML = groups.length
                        ? groups.map(group => `<tr><td>${group.id || '-'}</td><td>${group.name || '-'}</td><td>${group.course_name || '-'}</td></tr>`).join('')
                        : '<tr><td colspan="3" class="text-center py-4 text-muted">Sin grupos para este criterio.</td></tr>';
                } else if (coursesRes.ok) {
                    groupsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin grupos para este criterio.</td></tr>';
                }
            } catch (error) {
                console.error(error);
                studentsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión</td></tr>';
                teachersBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión</td></tr>';
                groupsBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión</td></tr>';
                coursesBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión</td></tr>';
            }
        }

        function renderMoodleCoursesList(courses = []) {
            const tbody = document.getElementById('moodleCoursesListTableBody');
            if (!tbody) return;
            if (!courses.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">No hay cursos disponibles.</td></tr>';
                return;
            }
            tbody.innerHTML = courses.map(course => {
                const fullname = (course.fullname || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const shortname = (course.shortname || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const summary = (course.summary || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const label = (course.displayname || course.fullname || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                return `
                <tr>
                    <td>${course.id || '-'}</td>
                    <td>${course.displayname || course.fullname || '-'}</td>
                    <td>${course.shortname || '-'}</td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="openMoodleCourseEditorPrompt(${course.id}, '${fullname}', '${shortname}', '${summary}', ${Number(course.categoryid || 1)})">Editar</button>
                        <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="deleteMoodleCoursePrompt(${course.id}, '${label}')">Eliminar</button>
                        <button class="btn btn-sm btn-outline-info rounded-pill ms-1" onclick="showMoodleCourseContents(${course.id})">Ver módulos</button>
                        <button class="btn btn-sm btn-outline-dark rounded-pill ms-1" onclick="openMoodleCourseUrl(${course.id})">Abrir</button>
                    </td>
                </tr>
            `;
            }).join('');
        }

        async function loadMoodleCoursesList() {
            const tbody = document.getElementById('moodleCoursesListTableBody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">Cargando cursos...</td></tr>';
            try {
                const response = await fetch('/admin/moodle/courses?q=', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudieron cargar cursos Moodle');
                    if (tbody) tbody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    return;
                }
                const payload = await response.json();
                moodleCoursesListCache = dedupeMoodleCourses(payload.courses || []);
                renderMoodleCoursesList(moodleCoursesListCache);
                populateMoodleGroupCourseSelect();
            } catch (error) {
                console.error(error);
                if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-danger">Error de conexión cargando cursos.</td></tr>';
            }
        }

        async function loadMoodleGroupsCount() {
            try {
                if (!moodleCoursesListCache.length) return;
                const groupsByCourse = await Promise.all(moodleCoursesListCache.map(async course => {
                    try {
                        const response = await fetch(`/admin/moodle/courses/${course.id}/groups`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                        });
                        if (!response.ok) return [];
                        const payload = await response.json();
                        return payload.groups || [];
                    } catch (error) {
                        console.error(error);
                        return [];
                    }
                }));
                moodleGroupsListCache = groupsByCourse.flat();
                renderMoodleKpis();
            } catch (error) {
                console.error(error);
            }
        }

        function openMoodleCourseUrl(courseId) {
            const base = moodleHealth?.public_url || 'http://localhost:8080';
            window.open(`${base}/course/view.php?id=${courseId}`, '_blank');
        }

        function populateMoodleGroupCourseSelect() {
            renderMoodleGroupCoursesMultiList();
            updateGroupSelectedCoursesInfo();
        }

        function dedupeMoodleCourses(courses = []) {
            const seen = new Map();
            for (const course of courses || []) {
                const courseId = Number(course?.id || 0);
                if (!courseId) continue;
                if (!seen.has(courseId)) seen.set(courseId, course);
            }
            return [...seen.values()];
        }

        function renderMoodleGroupCoursesMultiList(filterText = '') {
            const container = document.getElementById('moodleGroupCoursesMultiList');
            if (!container) return;
            const items = (moodleCoursesListCache || []).filter(course => {
                if (!filterText) return true;
                const name = `${course.displayname || ''} ${course.fullname || ''} ${course.shortname || ''}`.toLowerCase();
                return name.includes(filterText.toLowerCase());
            });
            if (!items.length) {
                container.innerHTML = '<span class="text-muted">No hay cursos que coincidan.</span>';
                return;
            }
            container.innerHTML = items.map(course => {
                const checked = selectedGroupCourseIds.has(Number(course.id)) ? 'checked' : '';
                return `
                    <label class="d-flex align-items-center gap-2 border-bottom py-1">
                        <input type="checkbox" class="form-check-input" ${checked} onchange="toggleGroupCourseSelection(${Number(course.id)}, this.checked)">
                        <span>#${course.id} · ${course.displayname || course.fullname || course.shortname}</span>
                    </label>
                `;
            }).join('');
        }

        function filterMoodleGroupCoursesList() {
            const query = document.getElementById('moodleGroupCourseNameSearch')?.value?.trim() || '';
            renderMoodleGroupCoursesMultiList(query);
        }

        function toggleGroupCourseSelection(courseId, checked) {
            const id = Number(courseId);
            if (!id) return;
            if (checked) {
                selectedGroupCourseIds.add(id);
            } else {
                selectedGroupCourseIds.delete(id);
            }
            updateGroupSelectedCoursesInfo();
        }

        function updateGroupSelectedCoursesInfo() {
            const info = document.getElementById('moodleGroupSelectedCoursesInfo');
            if (!info) return;
            const selectedCourses = dedupeMoodleCourses(moodleCoursesListCache)
                .filter(course => selectedGroupCourseIds.has(Number(course.id)))
                .map(course => course.displayname || course.fullname || course.shortname || `Curso ${course.id}`);
            if (!selectedCourses.length) {
                info.textContent = 'Cursos seleccionados: 0';
                return;
            }
            info.textContent = `Cursos seleccionados (${selectedCourses.length}): ${selectedCourses.join(', ')}`;
        }

        async function linkSubjectWithMoodleCourse(moodleCourseId) {
            const subjectIdRaw = prompt(`Ingresa el ID de materia local para vincular con Moodle Course #${moodleCourseId}:`);
            if (!subjectIdRaw) return;
            const subjectId = parseInt(subjectIdRaw, 10);
            if (!subjectId) {
                showToast('ID de materia inválido', true);
                return;
            }

            try {
                const response = await fetch(`/admin/subjects/${subjectId}/moodle-link`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ moodle_course_id: moodleCourseId }),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo vincular la materia con Moodle'), true);
                    return;
                }
                const result = await response.json();
                showToast(result.message || 'Materia vinculada con Moodle');
                await loadAdminData();
                await loadMoodleAdminView();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al vincular materia con Moodle', true);
            }
        }

        async function showMoodleCourseContents(courseId) {
            const titleEl = document.getElementById('moodleCourseContentsTitle');
            const tbody = document.getElementById('moodleCourseContentsTableBody');
            const modalEl = document.getElementById('moodleCourseContentsModal');
            if (!titleEl || !tbody || !modalEl) {
                showToast('No se encontró la ventana de módulos Moodle', true);
                return;
            }
            titleEl.textContent = `Curso Moodle #${courseId}`;
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-4">Cargando módulos...</td></tr>';
            bootstrap.Modal.getOrCreateInstance(modalEl).show();

            try {
                const response = await fetch(`/admin/moodle/courses/${courseId}/contents`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo consultar el contenido del curso en Moodle'), true);
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger py-4">No se pudo cargar el contenido del curso.</td></tr>';
                    return;
                }
                const payload = await response.json();
                const sections = payload.sections || [];
                if (!sections.length) {
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-4">Sin secciones visibles en este curso.</td></tr>';
                    showToast(`Curso ${courseId}: sin secciones visibles.`, false);
                    return;
                }

                tbody.innerHTML = sections.map((section, idx) => {
                    const modules = Array.isArray(section.modules) ? section.modules : [];
                    const modulesHtml = modules.length
                        ? modules.map(module => `<span class="badge bg-light text-dark border me-1 mb-1">${module.name || 'Módulo'}</span>`).join('')
                        : '<span class="text-muted">Sin módulos</span>';
                    return `
                        <tr>
                            <td>${section.section ?? idx}</td>
                            <td>${section.name || `Sección ${idx}`}</td>
                            <td>${modulesHtml}</td>
                        </tr>
                    `;
                }).join('');
                showToast(`Curso ${courseId}: ${sections.length} secciones cargadas.`, false);
            } catch (error) {
                console.error(error);
                showToast('Error consultando contenidos del curso Moodle', true);
                tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger py-4">Error de conexión al consultar módulos.</td></tr>';
            }
        }

        async function createMoodleCourse() {
            const fullname = document.getElementById('moodleCourseFullname').value.trim();
            const shortname = document.getElementById('moodleCourseShortname').value.trim();
            if (!fullname || !shortname) {
                showToast('Completa nombre y shortname del curso', true);
                return;
            }

            const payload = {
                fullname,
                shortname,
                categoryid: Number(document.getElementById('moodleCourseCategory').value || 1),
                summary: document.getElementById('moodleCourseSummary').value.trim() || null,
                format: document.getElementById('moodleCourseFormat').value || null,
                visible: document.getElementById('moodleCourseVisible').value === 'true',
            };

            try {
                const response = await fetch('/admin/moodle/courses', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo crear el curso en Moodle'), true);
                    return;
                }
                const result = await response.json();
                const course = result.course || {};
                document.getElementById('moodleCourseCreateForm').reset();
                document.getElementById('moodleCourseCategory').value = 1;
                document.getElementById('moodleCourseVisible').value = 'true';
                showToast(`Curso creado en Moodle (ID ${course.id || 'nuevo'})`);
                await loadMoodleCoursesList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al crear curso Moodle', true);
            }
        }

        function openMoodleCourseEditorPrompt(courseId = null, currentFullname = '', currentShortname = '', currentSummary = '', currentCategory = null) {
            const resolvedCourseId = Number.parseInt(courseId || '', 10);
            if (!resolvedCourseId) {
                showToast('No se pudo identificar el curso para editar', true);
                return;
            }
            document.getElementById('moodleEditCourseId').value = String(resolvedCourseId);
            document.getElementById('moodleEditCourseIdDisplay').value = String(resolvedCourseId);
            document.getElementById('moodleEditCourseFullname').value = currentFullname || '';
            document.getElementById('moodleEditCourseShortname').value = currentShortname || '';
            document.getElementById('moodleEditCourseSummary').value = currentSummary || '';
            document.getElementById('moodleEditCourseCategoryId').value = currentCategory || 1;
            ['moodleEditCourseFullname', 'moodleEditCourseShortname', 'moodleEditCourseSummary', 'moodleEditCourseCategoryId'].forEach(id => {
                const input = document.getElementById(id);
                if (input) input.disabled = true;
            });
            bootstrap.Modal.getOrCreateInstance(document.getElementById('moodleCourseEditModal')).show();
        }

        function toggleCourseEditField(fieldId) {
            const input = document.getElementById(fieldId);
            if (!input) return;
            input.disabled = false;
            input.focus();
        }

        async function saveMoodleCourseFromModal() {
            const courseId = Number.parseInt(document.getElementById('moodleEditCourseId')?.value || '', 10);
            if (!courseId) {
                showToast('Curso inválido', true);
                return;
            }
            const payload = {
                fullname: document.getElementById('moodleEditCourseFullname')?.value?.trim() || null,
                shortname: document.getElementById('moodleEditCourseShortname')?.value?.trim() || null,
                summary: document.getElementById('moodleEditCourseSummary')?.value?.trim() || null,
                categoryid: Number.parseInt(document.getElementById('moodleEditCourseCategoryId')?.value || '', 10) || null,
            };
            try {
                const response = await fetch(`/admin/moodle/courses/${courseId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo actualizar el curso Moodle'), true);
                    return;
                }
                showToast(`Curso ${courseId} actualizado correctamente`);
                bootstrap.Modal.getOrCreateInstance(document.getElementById('moodleCourseEditModal')).hide();
                await loadMoodleCoursesList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al actualizar curso Moodle', true);
            }
        }

        async function deleteMoodleCoursePrompt(courseId = null, courseName = '') {
            const resolvedCourseId = Number.parseInt(courseId || '', 10) || Number.parseInt(prompt('Ingresa el ID del curso Moodle a eliminar:') || '', 10);
            if (!resolvedCourseId) return;
            const label = courseName || `#${resolvedCourseId}`;
            if (!confirm(`¿Eliminar curso Moodle ${label}? Esta acción no se puede deshacer.`)) return;

            try {
                const response = await fetch(`/admin/moodle/courses/${resolvedCourseId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo eliminar el curso Moodle'), true);
                    return;
                }
                showToast(`Curso ${label} eliminado correctamente`);
                await loadMoodleCoursesList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al eliminar curso Moodle', true);
            }
        }

        async function loadMoodleGroupsList() {
            const tbody = document.getElementById('moodleGroupsListTableBody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">Cargando grupos...</td></tr>';
            try {
                if (!moodleCoursesListCache.length) {
                    await loadMoodleCoursesList();
                }
                const courses = moodleCoursesListCache || [];
                if (!courses.length) {
                    if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">No hay cursos para consultar grupos.</td></tr>';
                    return;
                }

                const groupsByCourse = await Promise.all(courses.map(async course => {
                    try {
                        const response = await fetch(`/admin/moodle/courses/${course.id}/groups`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                        });
                        if (!response.ok) return [];
                        const payload = await response.json();
                        return (payload.groups || []).map(group => ({
                            ...group,
                            course_name: course.displayname || course.fullname || course.shortname || `Curso ${course.id}`,
                        }));
                    } catch (error) {
                        console.error(error);
                        return [];
                    }
                }));

                moodleGroupsListCache = groupsByCourse.flat().filter((group, index, arr) => {
                    const gid = Number(group?.id || 0);
                    const cid = Number(group?.courseid || 0);
                    return arr.findIndex(item => Number(item?.id || 0) === gid && Number(item?.courseid || 0) === cid) === index;
                });
                renderMoodleGroupsList(moodleGroupsListCache);
            } catch (error) {
                console.error(error);
                if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-danger">Error de conexión cargando grupos.</td></tr>';
            }
        }

        function renderMoodleGroupsList(groups = []) {
            const tbody = document.getElementById('moodleGroupsListTableBody');
            if (!tbody) return;
            if (!groups.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">No hay grupos disponibles.</td></tr>';
                return;
            }
            const groupedByName = new Map();
            for (const group of groups) {
                const key = (group.name || '').trim().toLowerCase() || `id-${group.id}`;
                if (!groupedByName.has(key)) {
                    groupedByName.set(key, {
                        representative: group,
                        courseNames: new Set(),
                        groupIds: new Set(),
                    });
                }
                const entry = groupedByName.get(key);
                entry.courseNames.add(group.course_name || `Curso ${group.courseid || '-'}`);
                if (group.id) entry.groupIds.add(Number(group.id));
            }
            tbody.innerHTML = [...groupedByName.values()].map(entry => {
                const group = entry.representative;
                const name = (group.name || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const description = (group.description || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const idnumber = (group.idnumber || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const courseList = [...entry.courseNames].join(', ');
                const extra = entry.groupIds.size > 1
                    ? `<div class="small text-muted">${entry.groupIds.size} cursos asociados con este mismo nombre.</div>`
                    : '';
                return `
                <tr>
                    <td>${group.id || '-'}</td>
                    <td>${group.name || '-'}</td>
                    <td>${courseList}${extra}</td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="editMoodleGroupPrompt(${group.id}, '${name}', '${description}', '${idnumber}')">Editar</button>
                        <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="deleteMoodleGroupPrompt(${group.id})">Eliminar</button>
                        <button class="btn btn-sm btn-outline-dark rounded-pill ms-1" onclick="openMoodleGroupInSite(${group.id}, ${Number(group.courseid || 0)})">Abrir en Moodle</button>
                    </td>
                </tr>
            `;
            }).join('');
        }

        function openMoodleGroupInSite(groupId, courseId) {
            const base = moodleHealth?.public_url || 'http://localhost:8080';
            const fallbackUrl = `${base}/group/index.php?id=${courseId}`;
            const preferredUrl = `${base}/group/members.php?group=${groupId}`;
            window.open(groupId ? preferredUrl : fallbackUrl, '_blank');
        }

        async function searchMoodleUsersForGroupForm() {
            const query = document.getElementById('moodleGroupMemberSearchQuery')?.value?.trim() || '';
            const container = document.getElementById('moodleGroupMemberSearchResults');
            if (!container) return;
            if (!query) {
                container.innerHTML = '<span class="text-muted">Escribe un criterio para buscar integrantes.</span>';
                return;
            }
            container.innerHTML = '<span class="text-muted">Buscando usuarios...</span>';
            try {
                const response = await fetch(`/admin/moodle/users?q=${encodeURIComponent(query)}&limit=40`, {
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (!response.ok) {
                    container.innerHTML = `<span class="text-danger">${await extractApiErrorMessage(response, 'No se pudo buscar usuarios')}</span>`;
                    return;
                }
                const payload = await response.json();
                const users = payload.users || [];
                if (!users.length) {
                    container.innerHTML = '<span class="text-muted">Sin resultados para ese criterio.</span>';
                    return;
                }
                container.innerHTML = users.map(user => {
                    const id = Number(user.id || 0);
                    const checked = selectedGroupMemberIds.has(id) ? 'checked' : '';
                    return `
                        <label class="d-flex align-items-center gap-2 border-bottom py-1">
                            <input type="checkbox" class="form-check-input" ${checked} onchange="toggleGroupMemberSelection(${id}, this.checked)">
                            <span>#${id} · ${user.fullname || user.username || '-'} <span class="text-muted">(${user.username || '-'})</span></span>
                        </label>
                    `;
                }).join('');
            } catch (error) {
                console.error(error);
                container.innerHTML = '<span class="text-danger">Error de conexión al buscar usuarios.</span>';
            }
        }

        function toggleGroupMemberSelection(userId, checked) {
            const id = Number(userId);
            if (!id) return;
            if (checked) {
                selectedGroupMemberIds.add(id);
            } else {
                selectedGroupMemberIds.delete(id);
            }
            updateGroupSelectedMembersInfo();
        }

        function parseManualGroupMemberIds() {
            const raw = document.getElementById('moodleGroupMemberIdsManual')?.value || '';
            if (!raw.trim()) return [];
            const ids = raw
                .split(',')
                .map(part => Number.parseInt(part.trim(), 10))
                .filter(value => Number.isInteger(value) && value > 0);
            return [...new Set(ids)];
        }

        function updateGroupSelectedMembersInfo() {
            const info = document.getElementById('moodleGroupSelectedMembersInfo');
            if (!info) return;
            const manualIds = parseManualGroupMemberIds();
            const total = new Set([...selectedGroupMemberIds, ...manualIds]).size;
            info.textContent = `Integrantes seleccionados: ${total}`;
        }

        async function createMoodleGroupFromForm() {
            const name = document.getElementById('moodleGroupCreateName')?.value?.trim() || '';
            const description = document.getElementById('moodleGroupCreateDescription')?.value?.trim() || '';
            const idnumber = document.getElementById('moodleGroupCreateIdNumber')?.value?.trim() || null;
            const enrolmentkey = document.getElementById('moodleGroupCreateEnrolKey')?.value?.trim() || null;
            const courseIds = [...selectedGroupCourseIds].filter((value, index, arr) => arr.indexOf(value) === index);
            if (!courseIds.length || !name) {
                showToast('Selecciona uno o más cursos y nombre de grupo', true);
                return;
            }

            const manualIds = parseManualGroupMemberIds();
            const memberIds = [...new Set([...selectedGroupMemberIds, ...manualIds])];
            try {
                let createdCount = 0;
                let assignedCount = 0;
                let skippedCount = 0;
                for (const courseId of courseIds) {
                    try {
                        const existingResponse = await fetch(`/admin/moodle/courses/${courseId}/groups`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                        });
                        if (existingResponse.ok) {
                            const existingPayload = await existingResponse.json();
                            const alreadyExists = (existingPayload.groups || []).some(group =>
                                (group.name || '').trim().toLowerCase() === name.trim().toLowerCase()
                            );
                            if (alreadyExists) {
                                skippedCount += 1;
                                continue;
                            }
                        }
                    } catch (lookupError) {
                        console.error(lookupError);
                    }

                    const response = await fetch('/admin/moodle/groups', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ courseid: courseId, name, description, idnumber, enrolmentkey }),
                    });
                    if (!response.ok) {
                        console.error('Error creando grupo en curso', courseId, await extractApiErrorMessage(response, 'No se pudo crear el grupo Moodle'));
                        continue;
                    }
                    const payload = await response.json();
                    const createdGroupId = Number(payload?.group?.id || 0);
                    createdCount += 1;

                    if (createdGroupId && memberIds.length) {
                        const addResponse = await fetch(`/admin/moodle/groups/${createdGroupId}/members`, {
                            method: 'POST',
                            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                            body: JSON.stringify({ user_ids: memberIds }),
                        });
                        if (addResponse.ok) {
                            assignedCount += 1;
                        }
                    }
                }

                if (!createdCount) {
                    showToast('No se pudo crear el grupo en los cursos seleccionados', true);
                    return;
                }
                const resultMsg = `Grupo "${name}" creado en ${createdCount} curso(s). Integrantes asignados en ${assignedCount} grupo(s).` + (skippedCount ? ` Omitidos por duplicado: ${skippedCount}.` : '');
                showToast(resultMsg);

                document.getElementById('moodleGroupCreateForm')?.reset();
                selectedGroupMemberIds.clear();
                selectedGroupCourseIds.clear();
                updateGroupSelectedMembersInfo();
                updateGroupSelectedCoursesInfo();
                renderMoodleGroupCoursesMultiList();
                document.getElementById('moodleGroupMemberSearchResults').innerHTML = '<span class="text-muted">Busca usuarios para agregarlos como integrantes.</span>';
                await loadMoodleGroupsList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al crear grupo Moodle', true);
            }
        }

        async function loadMoodleGroupsCard() {
            const courseId = Number.parseInt(document.getElementById('moodleGroupsCourseId').value || '', 10);
            if (!courseId) {
                showToast('Ingresa un curso ID para cargar grupos', true);
                return;
            }
            currentMoodleCourseId = courseId;
            document.getElementById('moodleGroupsManagerCourseId').value = String(courseId);

            try {
                const response = await fetch(`/admin/moodle/courses/${courseId}/groups`, {
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (!response.ok) {
                    document.getElementById('moodleGroupsQuickInfo').innerHTML = `<span class="text-danger">${await extractApiErrorMessage(response, 'No se pudieron cargar los grupos')}</span>`;
                    return;
                }
                const payload = await response.json();
                currentMoodleGroups = payload.groups || [];
                document.getElementById('moodleGroupsQuickInfo').textContent = `Curso ${courseId}: ${payload.count || 0} grupo(s) encontrado(s).`;
                renderMoodleGroupsManagerTable();
            } catch (error) {
                console.error(error);
                document.getElementById('moodleGroupsQuickInfo').innerHTML = '<span class="text-danger">Error de conexión al consultar grupos</span>';
            }
        }

        function openMoodleGroupsManager(courseId = null) {
            const resolvedCourseId = courseId || currentMoodleCourseId || Number.parseInt(document.getElementById('moodleGroupsCourseId').value || '', 10);
            if (!resolvedCourseId) {
                showToast('Define primero un curso ID para administrar grupos', true);
                return;
            }
            currentMoodleCourseId = resolvedCourseId;
            document.getElementById('moodleGroupsManagerCourseId').value = String(resolvedCourseId);
            bootstrap.Modal.getOrCreateInstance(document.getElementById('moodleGroupsManagerModal')).show();
            reloadMoodleGroupsManager();
        }

        async function reloadMoodleGroupsManager() {
            const courseId = Number.parseInt(document.getElementById('moodleGroupsManagerCourseId').value || '', 10);
            if (!courseId) {
                showToast('Ingresa un curso ID válido', true);
                return;
            }
            currentMoodleCourseId = courseId;
            document.getElementById('moodleGroupsCourseId').value = String(courseId);
            await loadMoodleGroupsCard();
        }

        function renderMoodleGroupsManagerTable() {
            const tbody = document.getElementById('moodleGroupsManagerTableBody');
            if (!tbody) return;
            if (!currentMoodleGroups.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center py-4 text-muted">Sin grupos en este curso.</td></tr>';
                return;
            }
            tbody.innerHTML = currentMoodleGroups.map(group => `
                <tr>
                    <td>${group.id || '-'}</td>
                    <td class="fw-semibold">${group.name || '-'}</td>
                    <td>${group.description || '-'}</td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="editMoodleGroupPrompt(${group.id}, '${(group.name || '').replace(/'/g, "\\'")}', '${(group.description || '').replace(/'/g, "\\'")}')">
                            Editar
                        </button>
                        <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="deleteMoodleGroupPrompt(${group.id})">
                            Eliminar
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        async function quickCreateMoodleGroup() {
            const courseId = currentMoodleCourseId || Number.parseInt(document.getElementById('moodleGroupsCourseId').value || '', 10);
            if (!courseId) {
                showToast('Primero selecciona un curso ID', true);
                return;
            }
            const name = prompt('Nombre del nuevo grupo Moodle:');
            if (!name || !name.trim()) return;
            const description = prompt('Descripción (opcional):') || '';
            await createMoodleGroup(courseId, name.trim(), description.trim());
        }

        async function createMoodleGroupFromManager() {
            const courseId = Number.parseInt(document.getElementById('moodleGroupsManagerCourseId').value || '', 10);
            if (!courseId) {
                showToast('Ingresa un curso ID', true);
                return;
            }
            const name = prompt('Nombre del nuevo grupo Moodle:');
            if (!name || !name.trim()) return;
            const description = prompt('Descripción (opcional):') || '';
            await createMoodleGroup(courseId, name.trim(), description.trim());
        }

        async function createMoodleGroup(courseId, name, description = '') {
            try {
                const response = await fetch('/admin/moodle/groups', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ courseid: courseId, name, description }),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo crear el grupo Moodle'), true);
                    return;
                }
                showToast(`Grupo "${name}" creado correctamente`);
                await loadMoodleGroupsCard();
                await loadMoodleGroupsList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al crear grupo Moodle', true);
            }
        }

        async function editMoodleGroupPrompt(groupId, currentName = '', currentDescription = '', currentIdNumber = '') {
            const newName = prompt('Nuevo nombre del grupo:', currentName || '') || '';
            const newDescription = prompt('Nueva descripción del grupo:', currentDescription || '') || '';
            const newIdNumber = prompt('Nuevo ID Number del grupo (opcional):', currentIdNumber || '') || '';
            if (!newName.trim() && !newDescription.trim() && !newIdNumber.trim()) return;
            const payload = {};
            if (newName.trim()) payload.name = newName.trim();
            if (newDescription.trim()) payload.description = newDescription.trim();
            if (newIdNumber.trim()) payload.idnumber = newIdNumber.trim();

            try {
                const response = await fetch(`/admin/moodle/groups/${groupId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo editar el grupo Moodle'), true);
                    return;
                }
                showToast(`Grupo ${groupId} actualizado correctamente`);
                await loadMoodleGroupsList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al editar grupo Moodle', true);
            }
        }

        async function deleteMoodleGroupPrompt(groupId) {
            if (!confirm(`¿Eliminar grupo Moodle #${groupId}?`)) return;
            try {
                const response = await fetch(`/admin/moodle/groups/${groupId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo eliminar el grupo Moodle'), true);
                    return;
                }
                showToast(`Grupo ${groupId} eliminado correctamente`);
                await loadMoodleGroupsList();
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al eliminar grupo Moodle', true);
            }
        }

        function getBulkSyncPayload(dryRun = false) {
            const career = document.getElementById('bulkSyncCareer')?.value?.trim() || null;
            const semester = document.getElementById('bulkSyncSemester')?.value?.trim() || null;
            const categoryid = Number.parseInt(document.getElementById('bulkSyncCategoryId')?.value || '1', 10) || 1;
            const limit = Number.parseInt(document.getElementById('bulkSyncLimit')?.value || '50', 10) || 50;
            return {
                career,
                semester,
                categoryid,
                limit: Math.max(1, Math.min(limit, 500)),
                dry_run: dryRun,
            };
        }

        function renderBulkSyncResults(items = []) {
            const tbody = document.getElementById('bulkSyncSubjectsTableBody');
            if (!tbody) return;
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin resultados todavía.</td></tr>';
                return;
            }
            tbody.innerHTML = items.map(item => {
                const status = item.success === false
                    ? '<span class="badge bg-danger">Error</span>'
                    : item.action === 'validate_only'
                        ? '<span class="badge bg-info text-dark">Preview</span>'
                        : '<span class="badge bg-success">OK</span>';
                return `
                    <tr>
                        <td><div class="fw-semibold">${item.name || '-'}</div><div class="small text-muted">ID ${item.subject_id || '-'}</div></td>
                        <td>${item.shortname || '-'}</td>
                        <td>
                            ${status}
                            <div class="small text-muted mt-1">${item.message || item.error || ''}</div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        async function previewBulkSubjectSync() {
            const payload = getBulkSyncPayload(true);
            document.getElementById('bulkSyncSummary').textContent = 'Generando vista previa...';
            try {
                const response = await fetch('/admin/moodle/subjects/bulk-sync', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudo generar la vista previa');
                    document.getElementById('bulkSyncSummary').textContent = msg;
                    showToast(msg, true);
                    return;
                }
                const result = await response.json();
                renderBulkSyncResults(result.results || []);
                document.getElementById('bulkSyncSummary').textContent = `Vista previa: ${result.count || 0} materia(s) evaluadas.`;
                showToast('Vista previa de sync masivo lista');
            } catch (error) {
                console.error(error);
                document.getElementById('bulkSyncSummary').textContent = 'Error de conexión al generar vista previa.';
                showToast('Error de conexión en vista previa', true);
            }
        }

        async function runBulkSubjectSync() {
            const payload = getBulkSyncPayload(false);
            document.getElementById('bulkSyncSummary').textContent = 'Ejecutando sincronización masiva...';
            try {
                const response = await fetch('/admin/moodle/subjects/bulk-sync', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudo ejecutar la sincronización masiva');
                    document.getElementById('bulkSyncSummary').textContent = msg;
                    showToast(msg, true);
                    return;
                }
                const result = await response.json();
                renderBulkSyncResults(result.results || []);
                document.getElementById('bulkSyncSummary').textContent = `Sync completado: ${result.success_count || 0} OK · ${result.failed_count || 0} con error.`;
                showToast('Sincronización masiva de materias completada');
                await loadAdminData();
                await loadMoodleReconciliation(false);
            } catch (error) {
                console.error(error);
                document.getElementById('bulkSyncSummary').textContent = 'Error de conexión en sincronización masiva.';
                showToast('Error de conexión en sync masivo', true);
            }
        }

        async function runBulkAssignmentSync() {
            try {
                const response = await fetch('/admin/moodle/assignments/bulk-sync', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ only_active_cycle: true, limit: 200 }),
                });
                if (!response.ok && response.status !== 207) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo sincronizar asignaciones'), true);
                    return;
                }
                const result = await response.json();
                showToast(`Asignaciones Moodle: ${result.success_count || 0} OK · ${result.failed_count || 0} con error`);
                await loadMoodleReconciliation(false);
            } catch (error) {
                console.error(error);
                showToast('Error de conexión al sincronizar asignaciones', true);
            }
        }

        async function loadMoodleReconciliation(showNotification = true) {
            const reconTbody = document.getElementById('reconciliationAssignmentsTableBody');
            if (reconTbody) {
                reconTbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Cargando reconciliación...</td></tr>';
            }
            try {
                const response = await fetch('/admin/moodle/reconciliation?limit=100&verify_remote=true', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok) {
                    const msg = await extractApiErrorMessage(response, 'No se pudo cargar reconciliación');
                    if (reconTbody) reconTbody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-danger">${msg}</td></tr>`;
                    if (showNotification) showToast(msg, true);
                    return;
                }
                const data = await response.json();
                document.getElementById('reconStudentsCount').textContent = String(data.students_without_moodle_id?.count || 0);
                document.getElementById('reconTeachersCount').textContent = String(data.teachers_without_moodle_id?.count || 0);
                document.getElementById('reconSubjectsCount').textContent = String(data.subjects_without_moodle_course_id?.count || 0);
                document.getElementById('reconAssignmentsCount').textContent = String(data.assignments_not_synced?.count || 0);

                const issues = data.assignments_not_synced?.items || [];
                if (!issues.length) {
                    if (reconTbody) reconTbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-muted">Sin incidencias detectadas en asignaciones.</td></tr>';
                } else if (reconTbody) {
                    reconTbody.innerHTML = issues.map(item => `
                        <tr>
                            <td>
                                <div class="fw-semibold">#${item.assignment_id} · ${item.subject_name || 'Materia'}</div>
                                <div class="small text-muted">Docente: ${item.teacher_username || 'Sin docente'}</div>
                            </td>
                            <td>Course #${item.moodle_course_id || '-'}</td>
                            <td>${(item.issues || []).map(issue => `<span class="badge bg-warning text-dark me-1 mb-1">${issue}</span>`).join('')}</td>
                        </tr>
                    `).join('');
                }

                if (showNotification) showToast('Tablero de reconciliación actualizado');
            } catch (error) {
                console.error(error);
                if (reconTbody) reconTbody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-danger">Error de conexión al consultar reconciliación.</td></tr>';
                if (showNotification) showToast('Error de conexión al cargar reconciliación', true);
            }
        }

        async function loadMoodleAdminView(forceRefresh = false) {
            renderMoodleKpis();
            setOverviewSearchPlaceholder();
            await Promise.all([
                loadMoodleHealth(),
                loadMoodleFunctions(),
                loadMoodleReconciliation(false),
                loadMoodleCoursesList(),
                loadMoodleAccounts()
            ]);
            await loadMoodleGroupsCount();
            if (forceRefresh) currentMoodlePanel = 'overview';
            switchMoodlePanel(currentMoodlePanel);
            fixMojibakeInDom();
        }
