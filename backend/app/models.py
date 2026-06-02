from sqlalchemy import Boolean, Column, Integer, String, Enum as SQLEnum, Float, ForeignKey, DateTime, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
import enum
from datetime import datetime

class Career(Base):
    __tablename__ = "careers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)

    students = relationship("User", back_populates="career_rel")
    study_plans = relationship("StudyPlan", back_populates="career", passive_deletes=True)

class Modality(Base):
    __tablename__ = "modalities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    students = relationship("User", back_populates="modality_rel")

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    SERVICES = "services"

class UserStatus(str, enum.Enum):
    ACTIVO = "Activo"
    BAJA = "Baja"
    BLOQUEADO = "Bloqueado"

class EnrollmentStatus(str, enum.Enum):
    INSCRITO = "Inscrito"
    NO_INSCRITO = "No Inscrito"
    BAJA_TEMPORAL = "Baja Temporal"
    BAJA_DEFINITIVA = "Baja Definitiva"
    GRADUADO = "Graduado"

class PaymentStatus(str, enum.Enum):
    PENDIENTE = "Pendiente"
    PAGADO = "Pagado"
    VENCIDO = "Vencido"

class ChargeType(str, enum.Enum):
    TUITION = "Colegiatura"
    ENROLLMENT = "Inscripcion"
    REENROLLMENT = "Reinscripcion"
    SERVICE = "Tramite"
    SURCHARGE = "Recargo"
    SCHOLARSHIP = "Beca"
    OTHER = "Otro"

class GradeStatus(str, enum.Enum):
    CURSANDO = "Cursando"
    APROBADA = "Aprobada"
    REPROBADA = "Reprobada"
    PROXIMAMENTE = "Proximamente"

class AttemptType(str, enum.Enum):
    REGULAR = "Regular"
    RECURSA = "Recursa"
    EXTEMPORANEO = "Extemporaneo"

class ServiceRequestStatus(str, enum.Enum):
    EN_PROCESO = "En Proceso"
    LISTO = "Listo"
    ENTREGADO = "Entregado"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)  # Matrícula
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    curp = Column(String, nullable=True, index=True)
    seg_unique_key = Column(String, nullable=True, index=True)
    hashed_password = Column(String)
    moodle_id = Column(Integer, unique=True, nullable=True, index=True)
    role = Column(
        SQLEnum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        default=UserRole.STUDENT,
        server_default=UserRole.STUDENT.value,
        nullable=False,
    )
    user_status = Column(
        SQLEnum(UserStatus, name="user_status", values_callable=lambda x: [e.value for e in x]),
        default=UserStatus.ACTIVO,
        server_default=UserStatus.ACTIVO.value,
        nullable=False,
    )
    enrollment_status = Column(
        SQLEnum(EnrollmentStatus, name="enrollment_status", values_callable=lambda x: [e.value for e in x]),
        default=EnrollmentStatus.NO_INSCRITO,
        server_default=EnrollmentStatus.NO_INSCRITO.value,
        nullable=False,
    )
    # Campos legacy: se conservan como espejo temporal para compatibilidad,
    # pero la fuente operativa ya vive en StudentEnrollment/Group.
    carrera = Column(String, nullable=True)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="SET NULL"), nullable=True)
    modalidad = Column(String, nullable=True)
    modality_id = Column(Integer, ForeignKey("modalities.id", ondelete="SET NULL"), nullable=True)
    semestre = Column(String, nullable=True)
    grupo = Column(String, nullable=True)
    academic_advisor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    career_rel = relationship("Career", back_populates="students")
    modality_rel = relationship("Modality", back_populates="students")
    payments = relationship("Payment", back_populates="student", passive_deletes=True)
    charges = relationship("Charge", back_populates="student", passive_deletes=True)
    grades = relationship("Grade", back_populates="student", passive_deletes=True)
    service_requests = relationship("ServiceRequest", back_populates="student", passive_deletes=True)
    student_documents = relationship("StudentDocument", back_populates="student", passive_deletes=True)
    student_enrollments = relationship("StudentEnrollment", back_populates="student", passive_deletes=True)
    # Asignaciones del docente (qué materias imparte en qué ciclos)
    assignments = relationship("SubjectAssignment", back_populates="teacher", passive_deletes=True)
    received_notifications = relationship(
        "NotificationMessage",
        back_populates="recipient_user",
        passive_deletes=True,
        foreign_keys="NotificationMessage.recipient_user_id",
    )
    sent_notifications = relationship(
        "NotificationMessage",
        back_populates="created_by_user",
        passive_deletes=True,
        foreign_keys="NotificationMessage.created_by_user_id",
    )
    academic_advisor = relationship("User", remote_side=[id], foreign_keys=[academic_advisor_id])

class StudentDocument(Base):
    __tablename__ = "student_documents"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("User", back_populates="student_documents")

class Charge(Base):
    __tablename__ = "charges"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_enrollment_id = Column(Integer, ForeignKey("student_enrollments.id", ondelete="SET NULL"), nullable=True)
    charge_type = Column(
        SQLEnum(ChargeType, name="charge_type", values_callable=lambda x: [e.value for e in x]),
        default=ChargeType.OTHER,
        server_default=ChargeType.OTHER.value,
        nullable=False,
    )
    concept = Column(String, nullable=False)
    period_label = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(
        SQLEnum(PaymentStatus, name="charge_status", values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.PENDIENTE,
        server_default=PaymentStatus.PENDIENTE.value,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("User", back_populates="charges")
    student_enrollment = relationship("StudentEnrollment", back_populates="charges")
    payments = relationship("Payment", back_populates="charge", passive_deletes=True)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    charge_id = Column(Integer, ForeignKey("charges.id", ondelete="SET NULL"), nullable=True)
    concept = Column(String)
    amount = Column(Float)
    due_date = Column(DateTime)
    status = Column(
        SQLEnum(PaymentStatus, name="payment_status", values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.PENDIENTE,
        server_default=PaymentStatus.PENDIENTE.value,
        nullable=False,
    )

    student = relationship("User", back_populates="payments")
    charge = relationship("Charge", back_populates="payments")

class Subject(Base):
    """Plantilla de materia (catálogo). No contiene docente; usa SubjectAssignment."""
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    credits = Column(Integer)
    semester = Column(String)
    career = Column(String)
    modality = Column(String, default="presencial")
    moodle_course_id = Column(Integer, unique=True, nullable=True)

    grades = relationship("Grade", back_populates="subject", passive_deletes=True)
    assignments = relationship("SubjectAssignment", back_populates="subject", passive_deletes=True)
    study_plan_subjects = relationship("StudyPlanSubject", back_populates="subject", passive_deletes=True)


class SubjectAssignment(Base):
    """Asignación de un docente a una materia para un ciclo escolar.

    Permite que múltiples docentes impartan la misma materia en el mismo ciclo
    (grupos distintos). El campo cycle_id es nullable para datos migrados sin ciclo.
    """
    __tablename__ = "subject_assignments"
    __table_args__ = (
        # Un docente no puede tener dos asignaciones de la misma materia para el mismo grupo en el mismo ciclo.
        UniqueConstraint("subject_id", "teacher_id", "cycle_id", "group_id", name="uq_assignment_subject_teacher_cycle_group"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cycle_id = Column(Integer, ForeignKey("school_cycles.id", ondelete="SET NULL"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)

    subject = relationship("Subject", back_populates="assignments")
    teacher = relationship("User", back_populates="assignments")
    cycle = relationship("SchoolCycle", back_populates="assignments")
    group = relationship("Group")
    grades = relationship("Grade", back_populates="assignment", passive_deletes=True)
    course_enrollments = relationship("CourseEnrollment", back_populates="assignment", passive_deletes=True)


class Grade(Base):
    """Resultado evaluativo final de una carga académica.

    - course_enrollment_id: apunta a la inscripción académica concreta del alumno.
    - assignment_id: se conserva para retrocompatibilidad y datos migrados.
    - subject_id: se mantiene para consultas directas e historial legacy.
    - attempt_type: describe la oportunidad evaluativa del resultado final.
    """
    __tablename__ = "grades"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 10", name="ck_grades_score_range"),
    )
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("subject_assignments.id", ondelete="SET NULL"), nullable=True)
    course_enrollment_id = Column(Integer, ForeignKey("course_enrollments.id", ondelete="SET NULL"), nullable=True)
    attempt_type = Column(
        SQLEnum(AttemptType, name="attempt_type", values_callable=lambda x: [e.value for e in x]),
        default=AttemptType.REGULAR,
        server_default=AttemptType.REGULAR.value,
        nullable=False,
    )
    score = Column(Float, nullable=True)
    recorded_at = Column(DateTime, nullable=True)
    teacher_locked = Column(Boolean, default=False, nullable=False, server_default="false")
    status = Column(
        SQLEnum(GradeStatus, name="grade_status", values_callable=lambda x: [e.value for e in x]),
        default=GradeStatus.CURSANDO,
        server_default=GradeStatus.CURSANDO.value,
        nullable=False,
    )
    document_filename = Column(String, nullable=True)
    document_path = Column(String, nullable=True)

    student = relationship("User", back_populates="grades")
    subject = relationship("Subject", back_populates="grades")
    assignment = relationship("SubjectAssignment", back_populates="grades")
    course_enrollment = relationship("CourseEnrollment", back_populates="grades")


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String)
    attachment_filename = Column(String, nullable=True)
    attachment_path = Column(String, nullable=True)
    status = Column(
        SQLEnum(ServiceRequestStatus, name="service_status", values_callable=lambda x: [e.value for e in x]),
        default=ServiceRequestStatus.EN_PROCESO,
        server_default=ServiceRequestStatus.EN_PROCESO.value,
        nullable=False,
    )
    request_date = Column(DateTime, default=datetime.utcnow)

    student = relationship("User", back_populates="service_requests")


class SchoolCycle(Base):
    __tablename__ = "school_cycles"

    id = Column(Integer, primary_key=True, index=True)
    period = Column(String)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    monthly_amount = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tuitions = relationship("CycleTuition", back_populates="cycle", cascade="all, delete-orphan")
    assignments = relationship("SubjectAssignment", back_populates="cycle")
    student_enrollments = relationship("StudentEnrollment", back_populates="cycle")


class CycleTuition(Base):
    """Costo mensual por carrera+modalidad para un ciclo escolar."""
    __tablename__ = "cycle_tuitions"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("school_cycles.id", ondelete="CASCADE"), nullable=False)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="CASCADE"), nullable=False)
    modality_id = Column(Integer, ForeignKey("modalities.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)

    cycle = relationship("SchoolCycle", back_populates="tuitions")


class StudyPlan(Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        UniqueConstraint("career_id", "name", name="uq_study_plans_career_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    career = relationship("Career", back_populates="study_plans")
    subjects = relationship("StudyPlanSubject", back_populates="study_plan", cascade="all, delete-orphan")


class StudyPlanSubject(Base):
    __tablename__ = "study_plan_subjects"
    __table_args__ = (
        UniqueConstraint("study_plan_id", "subject_id", name="uq_study_plan_subjects_plan_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    study_plan_id = Column(Integer, ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    semester = Column(String, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    is_required = Column(Boolean, default=True, nullable=False)

    study_plan = relationship("StudyPlan", back_populates="subjects")
    subject = relationship("Subject", back_populates="study_plan_subjects")


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("name", "modality_id", name="uq_groups_name_modality"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    modality_id = Column(Integer, ForeignKey("modalities.id", ondelete="SET NULL"), nullable=True)
    tutor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    modality = relationship("Modality")
    tutor = relationship("User", foreign_keys=[tutor_id])
    career = relationship("Career", foreign_keys=[career_id])
    student_enrollments = relationship("StudentEnrollment", back_populates="group")


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "cycle_id", name="uq_student_enrollment_student_cycle"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cycle_id = Column(Integer, ForeignKey("school_cycles.id", ondelete="CASCADE"), nullable=False)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="SET NULL"), nullable=True)
    modality_id = Column(Integer, ForeignKey("modalities.id", ondelete="SET NULL"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    semester = Column(String, nullable=True)
    enrollment_status = Column(
        SQLEnum(EnrollmentStatus, name="student_enrollment_status", values_callable=lambda x: [e.value for e in x]),
        default=EnrollmentStatus.NO_INSCRITO,
        server_default=EnrollmentStatus.NO_INSCRITO.value,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    change_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    student = relationship("User", back_populates="student_enrollments")
    cycle = relationship("SchoolCycle", back_populates="student_enrollments")
    career = relationship("Career")
    modality = relationship("Modality")
    group = relationship("Group", back_populates="student_enrollments")
    course_enrollments = relationship("CourseEnrollment", back_populates="student_enrollment", passive_deletes=True)
    charges = relationship("Charge", back_populates="student_enrollment", passive_deletes=True)


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("student_enrollment_id", "assignment_id", "attempt_type", name="uq_course_enrollment_student_assignment_attempt"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_enrollment_id = Column(Integer, ForeignKey("student_enrollments.id", ondelete="CASCADE"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("subject_assignments.id", ondelete="CASCADE"), nullable=False)
    attempt_type = Column(
        SQLEnum(AttemptType, name="course_enrollment_attempt_type", values_callable=lambda x: [e.value for e in x]),
        default=AttemptType.REGULAR,
        server_default=AttemptType.REGULAR.value,
        nullable=False,
    )
    status = Column(
        SQLEnum(GradeStatus, name="course_enrollment_status", values_callable=lambda x: [e.value for e in x]),
        default=GradeStatus.CURSANDO,
        server_default=GradeStatus.CURSANDO.value,
        nullable=False,
    )
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    dropped_at = Column(DateTime, nullable=True)

    student_enrollment = relationship("StudentEnrollment", back_populates="course_enrollments")
    assignment = relationship("SubjectAssignment", back_populates="course_enrollments")
    grades = relationship("Grade", back_populates="course_enrollment", passive_deletes=True)


class NotificationMessage(Base):
    __tablename__ = "notification_messages"

    id = Column(Integer, primary_key=True, index=True)
    recipient_role = Column(
        SQLEnum(UserRole, name="notification_recipient_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_scope = Column(String, nullable=False, default="role", server_default="role")
    recipient_group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    category = Column(String, nullable=False, default="general", server_default="general")
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    level = Column(String, nullable=False, default="info", server_default="info")
    action_url = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_read = Column(Boolean, nullable=False, default=False, server_default="false")
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    recipient_user = relationship("User", back_populates="received_notifications", foreign_keys=[recipient_user_id])
    created_by_user = relationship("User", back_populates="sent_notifications", foreign_keys=[created_by_user_id])
    recipient_group = relationship("Group", foreign_keys=[recipient_group_id])


class AdvisorySessionStatus(str, enum.Enum):
    PENDIENTE = "Pendiente"
    CONFIRMADA = "Confirmada"
    CANCELADA = "Cancelada"
    REALIZADA = "Realizada"


class AdvisorySession(Base):
    __tablename__ = "advisory_sessions"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=30, nullable=False)
    topic = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    status = Column(
        SQLEnum(AdvisorySessionStatus, name="advisory_session_status", values_callable=lambda x: [e.value for e in x]),
        default=AdvisorySessionStatus.PENDIENTE,
        server_default=AdvisorySessionStatus.PENDIENTE.value,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    teacher = relationship("User", foreign_keys=[teacher_id])
    student = relationship("User", foreign_keys=[student_id])


# ── Página Web ──────────────────────────────────────────────────────────────

class ProjectCategory(str, enum.Enum):
    PORTFOLIO = "portfolio"
    EVENTO = "evento"

class ContactStatus(str, enum.Enum):
    NUEVO = "nuevo"
    CONTACTADO = "contactado"
    INSCRITO = "inscrito"

class Project(Base):
    """Portafolio de alumnos y eventos de la institución."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    short_description = Column(String, nullable=True)
    category = Column(
        SQLEnum(ProjectCategory, name="project_category", values_callable=lambda x: [e.value for e in x]),
        default=ProjectCategory.PORTFOLIO,
        server_default=ProjectCategory.PORTFOLIO.value,
        nullable=False,
    )
    image_url = Column(String, nullable=True)
    date = Column(DateTime, nullable=True)          # solo eventos
    location = Column(String, nullable=True)        # solo eventos
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Contact(Base):
    """Leads capturados desde el formulario de contacto de la landing."""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    email = Column(String, nullable=True)
    programa = Column(String, nullable=True)
    mensaje = Column(String, nullable=True)
    status = Column(
        SQLEnum(ContactStatus, name="contact_status", values_callable=lambda x: [e.value for e in x]),
        default=ContactStatus.NUEVO,
        server_default=ContactStatus.NUEVO.value,
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SuccessStory(Base):
    """Historias de éxito de egresados mostradas en la landing."""
    __tablename__ = "success_stories"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    role       = Column(String, nullable=False)          # "Desarrollador de Software"
    company    = Column(String, nullable=True)           # "Identidad Films"
    quote      = Column(String, nullable=False)          # frase testimonial
    photo_url  = Column(String, nullable=True)           # foto de perfil
    sort_order = Column(Integer, default=0, nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TestimonialReel(Base):
    """Reels/videos testimoniales de alumnos, padres y docentes."""
    __tablename__ = "testimonial_reels"

    id          = Column(Integer, primary_key=True, index=True)
    badge_text  = Column(String, nullable=False)         # "Alumno", "Padre de familia", "Profesor"
    badge_color = Column(String, nullable=False, default="pink")  # pink, warning, blue
    quote       = Column(String, nullable=False)         # titular en la tarjeta
    description = Column(String, nullable=True)          # texto de apoyo
    video_url   = Column(String, nullable=False)         # ruta o URL del video
    poster_url  = Column(String, nullable=True)          # imagen previa (thumbnail)
    sort_order  = Column(Integer, default=0, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExtracurricularCourse(Base):
    """Cursos extracurriculares administrables mostrados en la landing."""
    __tablename__ = "extracurricular_courses"

    id            = Column(Integer, primary_key=True, index=True)
    title         = Column(String, nullable=False)
    description   = Column(String, nullable=False)
    level         = Column(String, nullable=True)        # "Básico", "Intermedio", "Idiomas", etc.
    color         = Column(String, nullable=False, default="blue")  # blue, green, purple, orange, pink
    icon          = Column(String, nullable=False, default="bi-book")
    image_url     = Column(String, nullable=True)
    whatsapp_text = Column(String, nullable=True)        # texto para el enlace de WhatsApp
    sort_order    = Column(Integer, default=0, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)


# ── Pasaporte Digital ───────────────────────────────────────────────────────

class ThesisStatus(str, enum.Enum):
    SIN_INICIAR = "Sin Iniciar"
    PERFIL = "Perfil"
    PROTOCOLO = "Protocolo"
    MARCO_TEORICO = "Marco Teorico"
    DISENO = "Diseño"
    IMPLEMENTACION = "Implementacion"
    PRUEBAS = "Pruebas"
    REDACCION = "Redaccion"
    REVISIONES = "Revisiones"
    DEFENSA = "Defensa"
    TITULADO = "Titulado"


class SocialServiceStatus(str, enum.Enum):
    PENDIENTE = "Pendiente"
    REGISTRADO = "Registrado"
    EN_SERVICIO = "En Servicio"
    COMPLETADO = "Completado"
    LIBERADO = "Liberado"


class SocialServiceType(str, enum.Enum):
    UNIVERSITARIO = "Universitario"
    SEGURO_SOCIAL = "Seguro Social"


class ThesisRecord(Base):
    __tablename__ = "thesis_records"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    title = Column(String, nullable=True)
    director = Column(String, nullable=True)
    institution = Column(String, nullable=True)
    status = Column(
        SQLEnum(ThesisStatus, name="thesis_status", values_callable=lambda x: [e.value for e in x]),
        default=ThesisStatus.SIN_INICIAR,
        server_default=ThesisStatus.SIN_INICIAR.value,
        nullable=False,
    )
    notes = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student = relationship("User", foreign_keys=[student_id])


class SocialServiceRecord(Base):
    __tablename__ = "social_service_records"
    __table_args__ = (
        UniqueConstraint("student_id", "service_type", name="uq_social_service_student_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service_type = Column(
        SQLEnum(SocialServiceType, name="social_service_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    institution = Column(String, nullable=True)
    status = Column(
        SQLEnum(SocialServiceStatus, name="social_service_status", values_callable=lambda x: [e.value for e in x]),
        default=SocialServiceStatus.PENDIENTE,
        server_default=SocialServiceStatus.PENDIENTE.value,
        nullable=False,
    )
    hours_required = Column(Integer, nullable=True, default=480)
    hours_completed = Column(Integer, nullable=True, default=0)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    student = relationship("User", foreign_keys=[student_id])


class CommunityColor(str, enum.Enum):
    BLUE   = "blue"
    PINK   = "pink"
    ORANGE = "orange"
    PURPLE = "purple"
    GREEN  = "green"
    TEAL   = "teal"

class Community(Base):
    """Comunidades de la Legión Axolot mostradas en la landing."""
    __tablename__ = "communities"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    description = Column(String, nullable=False)
    icon        = Column(String, nullable=False, default="bi-people-fill")   # Bootstrap icon class
    color       = Column(
        SQLEnum(CommunityColor, name="community_color", values_callable=lambda x: [e.value for e in x]),
        default=CommunityColor.BLUE,
        server_default=CommunityColor.BLUE.value,
        nullable=False,
    )
    frequency   = Column(String, nullable=True)    # "Semanal", "Mensual", etc.
    image_url   = Column(String, nullable=True)
    member_count = Column(Integer, nullable=True)
    sort_order  = Column(Integer, default=0, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
