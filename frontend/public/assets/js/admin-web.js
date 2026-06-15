        const webAdminResources = {
            portfolioProjects: {
                endpoint: 'projects',
                query: '?category=portfolio',
                bodyId: 'webPortfolioTableBody',
                countId: 'webPortfolioCount',
                activeId: 'webPortfolioActive',
                empty: 'Sin proyectos de portafolio registrados.',
                activeLabel: 'activos',
                defaults: { category: 'portfolio' },
                fields: [
                    { key: 'title', label: 'Titulo', required: true },
                    { key: 'short_description', label: 'Descripcion corta' },
                    { key: 'image_url', label: 'URL de imagen' },
                    { key: 'location', label: 'Lugar o equipo' }
                ],
                columns: [
                    item => item.title,
                    item => item.short_description || '-',
                    item => item.image_url ? 'Con imagen' : '-'
                ]
            },
            testimonialReels: {
                endpoint: 'testimonial-reels',
                bodyId: 'webReelsTableBody',
                countId: 'webReelsCount',
                activeId: 'webReelsActive',
                empty: 'Sin reels registrados.',
                activeLabel: 'activos',
                fields: [
                    { key: 'badge_text', label: 'Etiqueta', required: true },
                    { key: 'badge_color', label: 'Color de etiqueta', fallback: 'pink' },
                    { key: 'quote', label: 'Frase principal', required: true },
                    { key: 'description', label: 'Descripcion' },
                    { key: 'video_url', label: 'URL de video', required: true },
                    { key: 'poster_url', label: 'URL de portada' },
                    { key: 'sort_order', label: 'Orden', type: 'number', fallback: 0 }
                ],
                columns: [
                    item => item.badge_text,
                    item => item.quote,
                    item => item.sort_order ?? 0
                ]
            },
            successStories: {
                endpoint: 'success-stories',
                bodyId: 'webSuccessTableBody',
                countId: 'webSuccessCount',
                activeId: 'webSuccessActive',
                empty: 'Sin egresados registrados.',
                activeLabel: 'activos',
                fields: [
                    { key: 'name', label: 'Nombre', required: true },
                    { key: 'role', label: 'Rol o carrera', required: true },
                    { key: 'company', label: 'Empresa o logro' },
                    { key: 'quote', label: 'Testimonio', required: true },
                    { key: 'photo_url', label: 'URL de foto' },
                    { key: 'sort_order', label: 'Orden', type: 'number', fallback: 0 }
                ],
                columns: [
                    item => item.name,
                    item => item.role || item.company || '-',
                    item => item.sort_order ?? 0
                ]
            },
            communities: {
                endpoint: 'communities',
                bodyId: 'webCommunitiesTableBody',
                countId: 'webCommunitiesCount',
                activeId: 'webCommunitiesActive',
                empty: 'Sin comunidades registradas.',
                activeLabel: 'activas',
                fields: [
                    { key: 'name', label: 'Nombre', required: true },
                    { key: 'description', label: 'Descripcion', required: true },
                    { key: 'icon', label: 'Icono Bootstrap', fallback: 'bi-people-fill' },
                    { key: 'color', label: 'Color', fallback: 'blue' },
                    { key: 'frequency', label: 'Frecuencia' },
                    { key: 'image_url', label: 'URL de imagen' },
                    { key: 'member_count', label: 'Numero de miembros', type: 'number' },
                    { key: 'sort_order', label: 'Orden', type: 'number', fallback: 0 }
                ],
                columns: [
                    item => item.name,
                    item => item.frequency || '-',
                    item => item.sort_order ?? 0
                ]
            }
        };

        function setWebAdminLoading() {
            Object.values(webAdminResources).forEach((config) => {
                const body = document.getElementById(config.bodyId);
                if (body) body.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">Cargando...</td></tr>';
            });
        }

        async function loadWebManagementView() {
            setWebAdminLoading();
            try {
                const entries = Object.entries(webAdminResources);
                const responses = await Promise.all(entries.map(([, config]) =>
                    fetch(`/admin/${config.endpoint}${config.query || ''}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    })
                ));

                for (let i = 0; i < responses.length; i++) {
                    if (!responses[i].ok) {
                        throw new Error(await extractApiErrorMessage(responses[i], 'No se pudo cargar la gestion web'));
                    }
                    const [key] = entries[i];
                    webAdminData[key] = await responses[i].json();
                }

                renderWebManagementView();
            } catch (error) {
                console.error(error);
                showToast(error.message || 'Error al cargar gestion web', true);
                Object.values(webAdminResources).forEach((config) => {
                    const body = document.getElementById(config.bodyId);
                    if (body) body.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-danger">No se pudo cargar.</td></tr>';
                });
            }
        }

        function renderWebManagementView() {
            Object.entries(webAdminResources).forEach(([key, config]) => {
                const items = webAdminData[key] || [];
                const activeItems = items.filter(item => item.is_active).length;
                const countEl = document.getElementById(config.countId);
                const activeEl = document.getElementById(config.activeId);
                const body = document.getElementById(config.bodyId);

                if (countEl) countEl.textContent = items.length;
                if (activeEl) activeEl.textContent = `${activeItems} ${config.activeLabel}`;
                if (!body) return;

                if (!items.length) {
                    body.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${config.empty}</td></tr>`;
                    return;
                }

                body.innerHTML = items.map((item) => {
                    const cells = config.columns.map((getter) => `<td>${escapeHtml(getter(item))}</td>`).join('');
                    const status = item.is_active
                        ? '<span class="badge bg-success-subtle text-success">Activo</span>'
                        : '<span class="badge bg-secondary-subtle text-secondary">Oculto</span>';
                    return `
                        <tr>
                            ${cells}
                            <td>${status}</td>
                            <td>
                                <button class="btn btn-sm btn-outline-secondary rounded-pill" onclick="editWebAdminItem('${key}', ${item.id})">
                                    Editar
                                </button>
                                <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="toggleWebAdminItem('${key}', ${item.id}, ${item.is_active ? 'false' : 'true'})">
                                    ${item.is_active ? 'Ocultar' : 'Activar'}
                                </button>
                                <button class="btn btn-sm btn-outline-danger rounded-pill ms-1" onclick="deleteWebAdminItem('${key}', ${item.id})">
                                    Eliminar
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            });
        }


        async function createWebAdminItem(resourceKey) {
            openWebAdminModal(resourceKey);
        }

        async function editWebAdminItem(resourceKey, itemId) {
            const currentItem = (webAdminData[resourceKey] || []).find(item => Number(item.id) === Number(itemId));
            if (!currentItem) return;
            openWebAdminModal(resourceKey, currentItem);
        }

        function openWebAdminModal(resourceKey, item = null) {
            const config = webAdminResources[resourceKey];
            if (!config) return;

            document.getElementById('webAdminResourceKey').value = resourceKey;
            document.getElementById('webAdminItemId').value = item ? item.id : '';
            document.getElementById('webAdminEditModalTitle').innerHTML = (item ? '<i class="bi bi-pencil-square me-2"></i>Editar ' : '<i class="bi bi-plus-circle me-2"></i>Nuevo ') + (config.fields.find(f => f.key === 'name')?.label || 'Contenido');
            
            const container = document.getElementById('webAdminFieldsContainer');
            container.innerHTML = '';

            config.fields.forEach(field => {
                const value = item ? (item[field.key] ?? field.fallback ?? '') : (field.fallback ?? '');
                const colClass = (field.type === 'number' || field.key === 'color' || field.key === 'icon') ? 'col-md-6' : 'col-12';
                
                let inputHtml = '';
                if (field.key === 'image_url' || field.key === 'icon') {
                    inputHtml = `
                        <div class="input-group">
                            <input type="${field.type === 'number' ? 'number' : 'text'}" class="form-control rounded-start-3" id="field_${field.key}" name="${field.key}" value="${escapeHtml(value)}" placeholder="${field.label}">
                            ${field.key === 'image_url' ? `
                                <input type="file" id="file_${field.key}" class="d-none" onchange="handleWebAdminFileUpload('${field.key}')" accept="image/*">
                                <button class="btn btn-outline-primary" type="button" onclick="document.getElementById('file_${field.key}').click()" title="Subir imagen">
                                    <i class="bi bi-upload"></i>
                                </button>
                            ` : ''}
                        </div>
                    `;
                } else if (field.key === 'description' || field.key === 'message') {
                    inputHtml = `<textarea class="form-control rounded-3" id="field_${field.key}" name="${field.key}" rows="3">${escapeHtml(value)}</textarea>`;
                } else {
                    inputHtml = `<input type="${field.type === 'number' ? 'number' : 'text'}" class="form-control rounded-3" id="field_${field.key}" name="${field.key}" value="${escapeHtml(value)}">`;
                }

                container.innerHTML += `
                    <div class="${colClass}">
                        <label class="form-label small fw-bold text-muted mb-1">${field.label}${field.required ? ' <span class="text-danger">*</span>' : ''}</label>
                        ${inputHtml}
                    </div>
                `;
            });

            bootstrap.Modal.getOrCreateInstance(document.getElementById('webAdminEditModal')).show();
        }

        async function handleWebAdminFileUpload(fieldKey) {
            const fileInput = document.getElementById(`file_${fieldKey}`);
            if (!fileInput.files.length) return;

            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('file', file);

            try {
                showToast('Subiendo imagen...');
                const response = await fetch('/admin/web/upload', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });

                if (!response.ok) throw new Error('Error al subir imagen');
                
                const data = await response.json();
                document.getElementById(`field_${fieldKey}`).value = data.image_url;
                showToast('Imagen subida correctamente', 'success');
            } catch (error) {
                console.error(error);
                showToast('Error al subir imagen', 'danger');
            }
        }

        async function saveWebAdminItem() {
            const resourceKey = document.getElementById('webAdminResourceKey').value;
            const itemId = document.getElementById('webAdminItemId').value;
            const config = webAdminResources[resourceKey];
            if (!config) return;

            const payload = { ...(config.defaults || {}) };
            for (const field of config.fields) {
                const el = document.getElementById(`field_${field.key}`);
                let val = el.value.trim();
                if (field.required && !val) {
                    showToast(`${field.label} es obligatorio`, 'warning');
                    el.focus();
                    return;
                }
                payload[field.key] = field.type === 'number' ? (val === '' ? null : Number(val)) : (val || null);
            }

            const btn = document.getElementById('webAdminSaveBtn');
            const textEl = document.getElementById('webAdminSaveBtnText');
            const spinner = document.getElementById('webAdminSaveBtnSpinner');

            try {
                btn.disabled = true;
                if (textEl) textEl.textContent = 'Guardando...';
                if (spinner) spinner.style.display = 'inline-block';

                const url = itemId 
                    ? `/admin/${config.endpoint}/${itemId}`
                    : `/admin/${config.endpoint}`;
                const method = itemId ? 'PUT' : 'POST';
                
                if (!itemId) payload.is_active = true;

                const response = await fetch(url, {
                    method: method,
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo guardar el contenido'), 'danger');
                    return;
                }

                showToast(itemId ? 'Contenido actualizado' : 'Contenido creado', 'success');
                bootstrap.Modal.getInstance(document.getElementById('webAdminEditModal')).hide();
                await loadWebManagementView();
            } catch (error) {
                console.error(error);
                showToast('Error de conexion', 'danger');
            } finally {
                btn.disabled = false;
                if (textEl) textEl.textContent = 'Guardar Cambios';
                if (spinner) spinner.style.display = 'none';
            }
        }

        async function toggleWebAdminItem(resourceKey, itemId, isActive) {
            const config = webAdminResources[resourceKey];
            if (!config) return;
            try {
                const response = await fetch(`/admin/${config.endpoint}/${itemId}`, {
                    method: 'PUT',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: isActive })
                });
                if (!response.ok) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo actualizar el contenido'), true);
                    return;
                }
                showToast(isActive ? 'Contenido activado' : 'Contenido oculto');
                await loadWebManagementView();
            } catch (error) {
                console.error(error);
                showToast('Error de conexion al actualizar contenido', true);
            }
        }

        async function deleteWebAdminItem(resourceKey, itemId) {
            const config = webAdminResources[resourceKey];
            if (!config || !confirm('Eliminar este contenido de la pagina web?')) return;
            try {
                const response = await fetch(`/admin/${config.endpoint}/${itemId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!response.ok && response.status !== 204) {
                    showToast(await extractApiErrorMessage(response, 'No se pudo eliminar el contenido'), true);
                    return;
                }
                showToast('Contenido eliminado');
                await loadWebManagementView();
            } catch (error) {
                console.error(error);
                showToast('Error de conexion al eliminar contenido', true);
            }
        }
