document.addEventListener('DOMContentLoaded', () => {
    const navbar = document.querySelector('.navbar');

    // Smooth scroll for nav links
    document.querySelectorAll('a.nav-link').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });

    // Add class on scroll for navbar styling
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('shadow-lg');
            navbar.style.opacity = '0.98';
        } else {
            navbar.classList.remove('shadow-lg');
            navbar.style.opacity = '1';
        }
    });

    // Simple observer for reveal animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('reveal-active');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.card, .hero img').forEach(el => observer.observe(el));

    // ============================================
    // AXO CHATBOT
    // ============================================

    const AXO_KNOWLEDGE = [
        {
            keywords: ['carrera', 'carreras', 'programa', 'programas', 'oferta', 'educativa', 'que estudiar', 'que puedo estudiar', 'opciones'],
            answer: '🎓 ¡Tenemos excelentes opciones para ti!\n\n<b>Ingenierías (3 años, planes cuatrimestrales):</b>\n• <b>Ingeniería en Software</b> — Presencial Intensiva, Presencial Sabatina o Virtual. Con certificaciones internacionales.\n• <b>Ingeniería en Telemática</b> — Presencial Intensiva o Presencial Sabatina. Con certificaciones internacionales.\n\n<b>Preparatorias (2 años):</b>\n• General — Informática\n• General — Automotriz\n• General — Presencial Sabatino\n\n¿Te interesa alguno en particular? 😊'
        },
        {
            keywords: ['software', 'programacion', 'programar', 'desarrollo', 'fullstack', 'ia', 'inteligencia artificial'],
            answer: '💻 <b>Ingeniería en Software</b> es una de nuestras carreras estrella.\n\n📅 <b>Duración:</b> 3 años (planes cuatrimestrales)\n🎯 <b>Modalidades:</b> Presencial Intensiva, Presencial Sabatina o Virtual\n🏅 <b>Incluye:</b> Certificaciones internacionales\n\nAprenderás:\n• Desarrollo Fullstack (frontend + backend)\n• Inteligencia Artificial\n• Cloud Computing\n• Proyectos reales desde el primer cuatrimestre\n\nNuestros egresados trabajan en empresas como Intel y startups tech. ¿Quieres más detalles? Escríbenos por <a href="https://wa.me/524191070127?text=Quiero%20info%20sobre%20Ingeniería%20en%20Software" target="_blank">WhatsApp</a> 📱'
        },
        {
            keywords: ['telematica', 'redes', 'ciberseguridad', 'iot', 'telecomunicaciones', 'internet'],
            answer: '🌐 <b>Ingeniería en Telemática</b> te conecta con el futuro.\n\n📅 <b>Duración:</b> 3 años (planes cuatrimestrales)\n🎯 <b>Modalidades:</b> Presencial Intensiva o Presencial Sabatina\n🏅 <b>Incluye:</b> Certificaciones internacionales\n\nÁreas de enfoque:\n• Redes Inteligentes\n• Ciberseguridad\n• IoT (Internet de las Cosas)\n\nPerfecto si te apasiona la tecnología de redes y comunicaciones. ¿Te gustaría conocer el plan de estudios? <a href="https://wa.me/524191070127?text=Quiero%20info%20sobre%20Ingeniería%20en%20Telemática" target="_blank">Contáctanos</a> 🚀'
        },
        {
            keywords: ['Preparatoria', 'prepa', 'preparatoria', 'bachiller', '2 años', 'dos años', 'sabatino', 'presencial sabatino'],
            answer: '📚 ¡Nuestros <b>Preparatorias</b> son los más rápidos de la zona!\n\n<b>Opciones disponibles (2 años):</b>\n• General — Informática\n• General — Automotriz\n• General — Presencial Sabatino (ideal si trabajas)\n\nTodos con validez oficial (RVOE). ¡Termina tu prepa en solo 2 años y salta a la uni! 🎯'
        },
        {
            keywords: ['beca', 'becas', 'descuento', 'descuentos', 'apoyo', 'ayuda economica'],
            answer: '💰 ¡Sí tenemos <b>becas por mérito académico</b>!\n\nDependiendo de tu promedio puedes obtener un porcentaje de beca.\n\nTambién hay descuentos por pronto pago y convenios empresariales.\n\nUsa nuestra <a href="#calculadora">Calculadora de Beca</a> para estimar tu colegiatura con descuento. 🧮'
        },
        {
            keywords: ['costo', 'costos', 'precio', 'precios', 'cuanto cuesta', 'colegiatura', 'mensualidad', 'pago', 'pagos', 'inversion'],
            answer: '💵 Los costos varían según el programa:\n\n• <b>Ing. en Software:</b> desde $4,500/mes\n• <b>Ing. en Telemática:</b> desde $4,200/mes\n• <b>Preparatoria:</b> desde $2,800/mes\n\n¡Y con tu promedio estos precios pueden bajar aún más! 🎉\n\nPrueba la <a href="#calculadora">Calculadora de Beca</a> para estimar tu inversión real. Para costos exactos y planes de pago, <a href="https://wa.me/524191070127?text=Quiero%20info%20sobre%20costos" target="_blank">escríbenos por WhatsApp</a>.'
        },
        {
            keywords: ['inscripcion', 'inscribirme', 'inscribir', 'inscripciones', 'como me inscribo', 'registro', 'registrarme', 'proceso'],
            answer: '📝 ¡Es muy fácil inscribirte! Son <b>4 pasos</b>:\n\n<b>1. Contáctanos</b> — Mándanos un <a href="https://wa.me/524191070127?text=Hola%2C%20quiero%20info%20de%20inscripción" target="_blank">WhatsApp</a> o llámanos\n<b>2. Agenda tu Visita</b> — Conoce nuestras instalaciones\n<b>3. Entrega tus Documentos</b> — CURP, Acta, Certificado, 4 fotos, comprobante de domicilio\n<b>4. ¡Bienvenido a la Legión!</b> — Realiza tu pago y recibe tu kit 🎒\n\n¡Las inscripciones en Septiembre ya están abiertas! 🚀'
        },
        {
            keywords: ['documento', 'documentos', 'requisitos', 'requisito', 'papeles', 'necesito', 'curp', 'acta', 'certificado', 'fotos'],
            answer: '📄 Los <b>documentos</b> que necesitas para inscribirte son:\n\n• ✅ CURP\n• ✅ Acta de Nacimiento\n• ✅ Certificado de estudios anteriores\n• ✅ 4 fotografías tamaño infantil\n• ✅ Comprobante de domicilio\n\n¿Ya los tienes listos? ¡Contáctanos para agendar tu visita! 📞'
        },
        {
            keywords: ['horario', 'horarios', 'turno', 'turnos', 'mañana', 'matutino', 'vespertino', 'tarde', 'noche'],
            answer: '🕐 ¡Tenemos horarios flexibles!\n\n• <b>Matutino</b> — Para ingenierías\n• <b>Vespertino</b> — Para ingenierías\n• <b>Presencial Sabatino</b> — Preparatoria (ideal si trabajas entre semana)\n• <b>Híbrido</b> — Clases online + prácticas presenciales\n• <b>Virtual</b> — 100% desde cualquier lugar\n\n¿Cuál se adapta mejor a tu estilo de vida? 🤔'
        },
        {
            keywords: ['modalidad', 'modalidades', 'presencial', 'hibrida', 'hibrido', 'virtual', 'online', 'en linea', 'distancia', 'semipresencial', 'intensiva', 'intensivo'],
            answer: '🏫 ¡Tenemos varias <b>modalidades</b> según tu carrera!\n\n<b>Ing. en Software:</b> Presencial Intensiva, Presencial Sabatina o Virtual\n<b>Ing. en Telemática:</b> Presencial Intensiva o Presencial Sabatina\n<b>Preparatoria:</b> Presencial Intensiva, Presencial Sabatino o Virtual\n\nAmbas ingenierías son a <b>3 años</b> con planes cuatrimestrales y <b>certificaciones internacionales</b>. 🏅\n\n¡Todas con la misma calidad y validez oficial! ✨'
        },
        {
            keywords: ['rvoe', 'validez', 'oficial', 'reconocimiento', 'sep', 'seg', 'valido', 'titulo', 'certificacion'],
            answer: '✅ ¡Sí! Todos nuestros programas cuentan con <b>RVOE</b> (Reconocimiento de Validez Oficial de Estudios) ante la <b>SEG (Secretaría de Educación de Guanajuato)</b>.\n\nTu título es <b>100% válido a nivel nacional</b>. Puedes estar tranquilo, tu inversión está respaldada. 🎓'
        },
        {
            keywords: ['ubicacion', 'donde', 'direccion', 'como llegar', 'mapa', 'san jose', 'iturbide', 'guanajuato'],
            answer: '📍 Estamos en:\n\n<b>Manuel Capetillo #40, Loma de Guadalupe</b>\nSan José Iturbide, Guanajuato\n\n📞 Tel: <a href="tel:+524191070127">419 107 0127</a>\n📧 Email: metaeducacionsanjose@gmail.com\n\n<a href="https://www.google.com/maps/dir//Manuel+Capetillo+40" target="_blank">Ver en Google Maps 🗺️</a>\n\n¡Te esperamos! Agenda una visita para conocer nuestras instalaciones.'
        },
        {
            keywords: ['contacto', 'contactar', 'telefono', 'llamar', 'whatsapp', 'email', 'correo', 'comunicar', 'hablar'],
            answer: '📞 ¡Contáctanos por el medio que prefieras!\n\n• 📱 <b>WhatsApp:</b> <a href="https://wa.me/524191070127?text=Hola%2C%20me%20interesa%20información%20sobre%20MetaEducación" target="_blank">419 107 0127</a> (¡la forma más rápida!)\n• 📞 <b>Teléfono:</b> <a href="tel:+524191070127">419 107 0127</a>\n• 📧 <b>Email:</b> metaeducacionsanjose@gmail.com\n\nNuestro equipo te responde en minutos por WhatsApp. ¡Estamos para ayudarte! 💬'
        },
        {
            keywords: ['trabajo', 'trabajar', 'empleo', 'campo laboral', 'egresados', 'salida', 'salidas', 'donde trabajar', 'sueldo'],
            answer: '🚀 ¡Nuestros egresados tienen un futuro brillante!\n\n<b>Campos laborales:</b>\n• 💻 Empresas de tecnología (desarrollo de software)\n• 🏭 Manufactura (automatización industrial)\n• 🔒 Ciberseguridad (protección de datos)\n• 🚀 Emprendimiento (tu propia startup)\n\n¡Algunos de nuestros egresados ya trabajan en empresas como Intel y Ubisoft! 🌟'
        },
        {
            keywords: ['laboratorio', 'laboratorios', 'instalaciones', 'campus', 'equipo', 'tecnologia'],
            answer: '🔬 Contamos con <b>laboratorios equipados con tecnología de punta</b>:\n\n• Laboratorio de computación\n• Taller de electrónica\n• Equipos de red y telecomunicaciones\n• Simuladores especializados\n\n¡Ven a conocerlos! Agenda una visita guiada. 🏫'
        },
        {
            keywords: ['hola', 'hi', 'hey', 'buenos dias', 'buenas tardes', 'buenas noches', 'que tal', 'saludos'],
            answer: '¡Hola! 👋 Soy <b>Axo</b>, tu asistente de MetaEducación.\n\n¿En qué puedo ayudarte hoy? Puedo contarte sobre:\n• 🎓 Nuestras carreras y Preparatorias\n• 💰 Becas y costos\n• 📝 Proceso de inscripción\n• 🕐 Horarios y modalidades\n• 📍 Ubicación y contacto\n\n¡Pregúntame lo que quieras! 😊'
        },
        {
            keywords: ['gracias', 'thank', 'agradezco', 'muchas gracias', 'excelente', 'genial', 'perfecto'],
            answer: '¡De nada! 😊 Me alegra poder ayudarte. Si tienes más preguntas, ¡aquí estaré! 🎉\n\nRecuerda que para atención personalizada puedes escribirnos directo por <a href="https://wa.me/524191070127" target="_blank">WhatsApp</a>. ¡Éxito! 🚀'
        },
        {
            keywords: ['adios', 'bye', 'chao', 'hasta luego', 'nos vemos', 'me voy'],
            answer: '¡Hasta pronto! 👋 Fue un gusto ayudarte. Recuerda que MetaEducación siempre está aquí para ti.\n\n¡Te esperamos en la <b>Legión Axolot</b>! 🦎💚'
        },
        {
            keywords: ['axo', 'axolot', 'axolote', 'mascota', 'quien eres', 'que eres'],
            answer: '🦎 ¡Soy <b>Axo</b>! La mascota oficial de MetaEducación y líder de la <b>Legión Axolot</b>.\n\nAsí como el axolote se regenera y evoluciona, en MetaEducación <b>tú también evolucionas</b> profesionalmente. ¡Soy tu guía en este camino! 🌟\n\n¿Qué quieres saber sobre MetaEducación? 😊'
        }
    ];

    const FALLBACK_RESPONSES = [
        '🤔 No estoy muy seguro de esa pregunta, pero puedo ayudarte con info sobre <b>carreras, becas, inscripción, costos y más</b>.\n\n¿Qué te gustaría saber? O si prefieres, escríbenos directo por <a href="https://wa.me/524191070127" target="_blank">WhatsApp</a> para atención personalizada.',
        '¡Buena pregunta! 😅 Para darte la mejor respuesta, te recomiendo contactar a nuestro equipo por <a href="https://wa.me/524191070127" target="_blank">WhatsApp</a>.\n\nMientras tanto, puedo ayudarte con info sobre <b>programas, becas, costos o inscripción</b>. ¿Qué prefieres?',
        'Mmm, eso no lo tengo en mi base de datos 🧐 Pero puedo ayudarte con todo sobre MetaEducación.\n\nIntenta preguntarme sobre: <b>carreras, becas, costos, inscripción, horarios o contacto</b>. ¡O escribe por <a href="https://wa.me/524191070127" target="_blank">WhatsApp</a>!'
    ];

    // DOM Elements
    const chatToggle = document.getElementById('axoChatToggle');
    const chatWindow = document.getElementById('axoChatWindow');
    const chatClose = document.getElementById('axoChatClose');
    const chatMessages = document.getElementById('axoChatMessages');
    const chatInput = document.getElementById('axoChatInput');
    const chatSend = document.getElementById('axoChatSend');
    const quickActions = document.querySelectorAll('.axo-quick-btn');
    const chatBadge = document.querySelector('.axo-toggle-badge');

    let isChatOpen = false;
    let hasOpenedOnce = false;
    let tooltipEl = null;

    // Show welcome tooltip after 3 seconds
    setTimeout(() => {
        if (!isChatOpen && !hasOpenedOnce) {
            showWelcomeTooltip();
        }
    }, 3000);

    function showWelcomeTooltip() {
        if (tooltipEl) return;
        tooltipEl = document.createElement('div');
        tooltipEl.className = 'axo-welcome-tooltip';
        tooltipEl.innerHTML = '👋 ¡Hola! Soy <b>Axo</b>. ¿Tienes dudas sobre MetaEducación? ¡Pregúntame!';
        document.getElementById('axoChatbot').appendChild(tooltipEl);

        // Auto-dismiss after 8s
        setTimeout(() => {
            if (tooltipEl) {
                tooltipEl.style.transition = 'all 0.3s ease';
                tooltipEl.style.opacity = '0';
                tooltipEl.style.transform = 'translateY(10px)';
                setTimeout(() => {
                    if (tooltipEl && tooltipEl.parentNode) {
                        tooltipEl.parentNode.removeChild(tooltipEl);
                        tooltipEl = null;
                    }
                }, 300);
            }
        }, 8000);
    }

    function removeTooltip() {
        if (tooltipEl && tooltipEl.parentNode) {
            tooltipEl.parentNode.removeChild(tooltipEl);
            tooltipEl = null;
        }
    }

    // Toggle chat
    chatToggle.addEventListener('click', () => {
        if (isChatOpen) {
            closeChat();
        } else {
            openChat();
        }
    });

    chatClose.addEventListener('click', closeChat);

    function openChat() {
        isChatOpen = true;
        chatWindow.classList.add('axo-open');
        chatToggle.classList.add('axo-hidden');
        chatBadge.style.display = 'none';
        removeTooltip();

        if (!hasOpenedOnce) {
            hasOpenedOnce = true;
            addBotMessage('¡Hola! 👋 Soy <b>Axo</b>, tu asistente virtual de <b>MetaEducación</b>.\n\n¿En qué puedo ayudarte? Puedes escribirme o usar los botones rápidos de abajo. 😊');
        }

        setTimeout(() => chatInput.focus(), 400);
    }

    function closeChat() {
        isChatOpen = false;
        chatWindow.classList.remove('axo-open');
        chatToggle.classList.remove('axo-hidden');
    }

    // Send message
    chatSend.addEventListener('click', handleUserMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleUserMessage();
    });

    function handleUserMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        addUserMessage(text);
        chatInput.value = '';

        // Show typing indicator
        showTyping();

        // Find response
        const response = findBestResponse(text);

        // Simulate typing delay (600-1200ms)
        const delay = 600 + Math.random() * 600;
        setTimeout(() => {
            removeTyping();
            addBotMessage(response);
        }, delay);
    }

    // Quick action buttons
    quickActions.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.dataset.question;
            const questionMap = {
                'carreras': '¿Qué carreras ofrecen?',
                'becas': '¿Tienen becas disponibles?',
                'inscripcion': '¿Cómo me inscribo?',
                'horarios': '¿Qué horarios tienen?',
                'costos': '¿Cuánto cuesta la colegiatura?',
                'contacto': '¿Cómo los contacto?'
            };

            const displayText = questionMap[question] || question;
            addUserMessage(displayText);

            showTyping();

            const response = findBestResponse(question);
            const delay = 600 + Math.random() * 600;
            setTimeout(() => {
                removeTyping();
                addBotMessage(response);
            }, delay);
        });
    });

    // Message rendering
    function addBotMessage(html) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'axo-msg axo-msg-bot';
        msgDiv.innerHTML = `
            <div class="axo-msg-avatar">
                <img src="assets/axo-polo-laptop.png" alt="Axo">
            </div>
            <div class="axo-msg-bubble">${html.replace(/\n/g, '<br>')}</div>
        `;
        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function addUserMessage(text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'axo-msg axo-msg-user';
        msgDiv.innerHTML = `
            <div class="axo-msg-bubble">${escapeHtml(text)}</div>
        `;
        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function showTyping() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'axo-msg axo-msg-bot';
        typingDiv.id = 'axoTyping';
        typingDiv.innerHTML = `
            <div class="axo-msg-avatar">
                <img src="assets/axo-polo-laptop.png" alt="Axo">
            </div>
            <div class="axo-msg-bubble axo-typing">
                <span class="axo-typing-dot"></span>
                <span class="axo-typing-dot"></span>
                <span class="axo-typing-dot"></span>
            </div>
        `;
        chatMessages.appendChild(typingDiv);
        scrollToBottom();
    }

    function removeTyping() {
        const typing = document.getElementById('axoTyping');
        if (typing) typing.remove();
    }

    function scrollToBottom() {
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 50);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Intent matching with scoring
    function findBestResponse(input) {
        const normalized = input.toLowerCase()
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // Remove accents
            .replace(/[^a-z0-9\s]/g, '');

        const words = normalized.split(/\s+/);
        let bestScore = 0;
        let bestAnswer = null;

        for (const entry of AXO_KNOWLEDGE) {
            let score = 0;
            for (const keyword of entry.keywords) {
                const normalizedKeyword = keyword.toLowerCase()
                    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                    .replace(/[^a-z0-9\s]/g, '');

                // Exact phrase match (highest score)
                if (normalized.includes(normalizedKeyword)) {
                    score += 3;
                }
                // Word-level match
                const keywordWords = normalizedKeyword.split(/\s+/);
                for (const kw of keywordWords) {
                    for (const w of words) {
                        if (w === kw) score += 2;
                        else if (w.length > 3 && kw.startsWith(w)) score += 1;
                        else if (kw.length > 3 && w.startsWith(kw)) score += 1;
                    }
                }
            }

            if (score > bestScore) {
                bestScore = score;
                bestAnswer = entry.answer;
            }
        }

        if (bestScore >= 2 && bestAnswer) {
            return bestAnswer;
        }

        // Fallback
        return FALLBACK_RESPONSES[Math.floor(Math.random() * FALLBACK_RESPONSES.length)];
    }

    // Close chat on click outside
    document.addEventListener('click', (e) => {
        if (isChatOpen && !chatWindow.contains(e.target) && !chatToggle.contains(e.target)) {
            closeChat();
        }
    });

    // Prevent chat close when clicking inside
    chatWindow.addEventListener('click', (e) => {
        e.stopPropagation();
    });

    // Flip modality cards on click
    document.querySelectorAll('.modality-card-inner').forEach(card => {
        card.addEventListener('click', () => {
            card.classList.toggle('flipped');
        });
    });
});



