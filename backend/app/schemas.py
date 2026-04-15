import enum
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

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
    EXTEMPORANEO = "Extemporaneo"

class ServiceRequestType(str, enum.Enum):
    CONSTANCIA_ESTUDIOS = "Constancia de Estudios"
    CONSTANCIA = "Constancia"
    KARDEX = "Kardex"
    CREDENCIAL = "Credencial"
    CERTIFICADO = "Certificado"
    BAJA_TEMPORAL = "Baja Temporal"
    TITULACION = "Titulación"
    OTRO = "Otro"

class ServiceRequestStatus(str, enum.Enum):
    EN_PROCESO = "En Proceso"
    LISTO = "Listo"
    ENTREGADO = "Entregado"

class UserBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: UserRole
    user_status: UserStatus = UserStatus.ACTIVO
    enrollment_status: EnrollmentStatus = EnrollmentStatus.NO_INSCRITO
    career_id: Optional[int] = None
    carrera: Optional[str] = None
    modality_id: Optional[int] = None
    modalidad: Optional[str] = None
    semestre: Optional[str] = None
    grupo: Optional[str] = None

class UserCreate(UserBase):
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9._-]{4,32}$", v):
            raise ValueError("Username must be 4-32 chars, alphanumerics, dot, underscore or hyphen")
        return v

    @field_validator("grupo")
    @classmethod
    def validate_group(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[A-Za-z0-9-]{1,10}$", v):
            raise ValueError("Grupo must be alphanumeric/hyphen and up to 10 chars")
        return v

    @field_validator("semestre")
    @classmethod
    def validate_semestre(cls, v):
        if v is not None:
            if v.lower() == "especial":
                return "Especial"
            if not re.match(r'^\d{1,2}$', v):
                raise ValueError('Semestre must be a number between 1 and 9 or "Especial"')
            sem = int(v)
            if not 1 <= sem <= 9:
                raise ValueError('Semestre must be between 1 and 9 or "Especial"')
        return v

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    user_status: Optional[UserStatus] = None
    enrollment_status: Optional[EnrollmentStatus] = None
    career_id: Optional[int] = None
    carrera: Optional[str] = None
    modality_id: Optional[int] = None
    modalidad: Optional[str] = None
    semestre: Optional[str] = None
    grupo: Optional[str] = None

class PaymentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concept: str
    amount: float = Field(gt=0)
    due_date: datetime
    status: PaymentStatus

class PaymentCreate(PaymentBase):
    student_username: str

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        if v <= datetime.now():
            raise ValueError('Due date must be in the future')
        return v

class PaymentUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    concept: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    due_date: Optional[datetime] = None
    status: Optional[PaymentStatus] = None

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, v):
        if v is not None and v <= datetime.now():
            raise ValueError('Due date must be in the future')
        return v

class Payment(PaymentBase):
    id: int
    student_id: int
    charge_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class PaymentWithStudent(Payment):
    student: UserBase
    model_config = ConfigDict(from_attributes=True)


class ChargeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    charge_type: ChargeType = ChargeType.OTHER
    concept: str
    period_label: Optional[str] = None
    amount: float = Field(gt=0)
    due_date: datetime
    status: PaymentStatus = PaymentStatus.PENDIENTE


class ChargeCreate(ChargeBase):
    student_username: str
    cycle_id: Optional[int] = None
    student_enrollment_id: Optional[int] = None


class ChargeUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    charge_type: Optional[ChargeType] = None
    concept: Optional[str] = None
    period_label: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    due_date: Optional[datetime] = None
    status: Optional[PaymentStatus] = None


class Charge(ChargeBase):
    id: int
    student_id: int
    student_enrollment_id: Optional[int] = None
    created_at: datetime


class ChargeWithStudent(Charge):
    student: UserBase
    model_config = ConfigDict(from_attributes=True)

class TeacherInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

class SubjectBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    credits: int = Field(gt=0)
    semester: str
    career: str

    @field_validator("semester")
    @classmethod
    def validate_semester(cls, v):
        # Acepta etiquetas tipo "1", "1er Semestre" o "Otoño 2026"
        if not v or len(v.strip()) == 0:
            raise ValueError('Semester must be a non-empty string')
        if len(v) > 50:
            raise ValueError('Semester must be at most 50 characters')
        return v

class SubjectCreate(SubjectBase):
    pass

class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    credits: Optional[int] = Field(None, gt=0)
    semester: Optional[str] = None
    career: Optional[str] = None
    teacher_username: Optional[str] = None

    @field_validator("semester")
    @classmethod
    def validate_semester(cls, v):
        if v is not None:
            if len(v.strip()) == 0:
                raise ValueError('Semester must be a non-empty string')
            if len(v) > 50:
                raise ValueError('Semester must be at most 50 characters')
        return v

class Subject(SubjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SubjectWithTeacher(Subject):
    teacher_id: Optional[int] = None
    teacher_username: Optional[str] = None


class StudyPlanBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    career_id: int
    name: str
    version: str = "1"
    is_active: bool = True


class StudyPlanCreate(StudyPlanBase):
    pass


class StudyPlanSubjectBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_id: int
    semester: Optional[str] = None
    order_index: int = 0
    is_required: bool = True


class StudyPlanSubjectCreate(StudyPlanSubjectBase):
    pass


class StudyPlanSubject(StudyPlanSubjectBase):
    id: int
    study_plan_id: int
    subject: Optional[Subject] = None


class StudyPlan(StudyPlanBase):
    id: int
    created_at: datetime


class StudyPlanWithSubjects(StudyPlan):
    career: Optional["Career"] = None
    subjects: List[StudyPlanSubject] = []

# ─── Asignación de docente a materia por ciclo ───────────────────────────────

class SubjectAssignmentCreate(BaseModel):
    subject_id: int
    teacher_username: str
    cycle_id: Optional[int] = None  # None = usar ciclo activo automáticamente

class SubjectAssignmentUpdate(BaseModel):
    teacher_username: Optional[str] = None

class SubjectInfo(BaseModel):
    """Info mínima de materia para incrustar en asignación."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    credits: int
    semester: str
    career: str

class SubjectAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subject_id: int
    teacher_id: Optional[int] = None
    cycle_id: Optional[int] = None
    subject: Optional[SubjectInfo] = None
    teacher: Optional[TeacherInfo] = None

class GradeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: Optional[float] = Field(None, ge=0, le=10)
    status: GradeStatus

class GradeUpdate(BaseModel):
    score: Optional[float] = Field(None, ge=0, le=10)
    status: Optional[GradeStatus] = None

class ExtemporaneGradeCreate(BaseModel):
    """Crea una calificación de examen extemporáneo para un alumno en una asignación."""
    score: Optional[float] = Field(None, ge=0, le=10)
    status: GradeStatus = GradeStatus.CURSANDO

class Grade(GradeBase):
    id: int
    student_id: int
    subject_id: int
    assignment_id: Optional[int] = None
    course_enrollment_id: Optional[int] = None
    attempt_type: AttemptType = AttemptType.REGULAR
    recorded_at: Optional[datetime] = None
    teacher_locked: bool = False
    subject: Optional[Subject] = None
    model_config = ConfigDict(from_attributes=True)


class AcademicHistoryItem(BaseModel):
    grade_id: Optional[int] = None
    course_enrollment_id: Optional[int] = None
    assignment_id: Optional[int] = None
    subject_id: Optional[int] = None
    subject_name: Optional[str] = None
    semester: Optional[str] = None
    credits: Optional[int] = None
    cycle: Optional[str] = None
    teacher: Optional[str] = None
    attempt_type: Optional[AttemptType] = None
    final_score: Optional[float] = None
    status: Optional[GradeStatus] = None
    dropped_at: Optional[datetime] = None

class ServiceRequestBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: ServiceRequestType
    status: ServiceRequestStatus
    request_date: datetime

class ServiceRequestCreate(ServiceRequestBase):
    student_username: str

    @field_validator("request_date", mode="before")
    @classmethod
    def normalize_request_date(cls, v):
        if isinstance(v, str) and len(v) == 10:
            return datetime.fromisoformat(f"{v}T12:00:00")
        return v

    @field_validator("request_date")
    @classmethod
    def validate_request_date(cls, v: datetime) -> datetime:
        if v.date() < datetime.now().date():
            raise ValueError("request_date cannot be in the past")
        return v


class ServiceRequestSelfCreate(BaseModel):
    type: ServiceRequestType
    request_date: datetime

    @field_validator("request_date", mode="before")
    @classmethod
    def normalize_request_date(cls, v):
        if isinstance(v, str) and len(v) == 10:
            return datetime.fromisoformat(f"{v}T12:00:00")
        return v

    @field_validator("request_date")
    @classmethod
    def validate_request_date(cls, v: datetime) -> datetime:
        if v.date() < datetime.now().date():
            raise ValueError("request_date cannot be in the past")
        return v

class ServiceRequestUpdate(BaseModel):
    type: Optional[ServiceRequestType] = None
    status: Optional[ServiceRequestStatus] = None
    request_date: Optional[datetime] = None

class ServiceRequest(ServiceRequestBase):
    id: int
    student_id: int
    attachment_filename: Optional[str] = None
    attachment_path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ServiceRequestWithStudent(ServiceRequest):
    student: UserBase
    model_config = ConfigDict(from_attributes=True)

class User(UserBase):
    id: int
    payments: List[Payment] = []
    grades: List[Grade] = []
    service_requests: List[ServiceRequest] = []
    model_config = ConfigDict(from_attributes=True)

class Career(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None

class CareerCreate(BaseModel):
    name: str
    description: Optional[str] = None

class Modality(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str

class ModalityCreate(BaseModel):
    name: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None


class TokenPair(Token):
    refresh_token: str
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class CycleTuitionEntry(BaseModel):
    career_id: int
    modality_id: int
    amount: float = Field(gt=0)

class SchoolCycleBase(BaseModel):
    period: str
    start_date: datetime
    end_date: datetime
    monthly_amount: float = Field(default=0, ge=0)  # default fallback
    is_active: bool = True

class SchoolCycleCreate(SchoolCycleBase):
    tuitions: List[CycleTuitionEntry] = []

class SchoolCycle(SchoolCycleBase):
    id: int
    created_at: datetime
    tuitions: List[CycleTuitionEntry] = []
    model_config = ConfigDict(from_attributes=True)

class SchoolCyclePaymentResult(BaseModel):
    payments_created: int
    students_affected: int
    months: list


class GroupBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    modality_id: Optional[int] = None
    tutor_id: Optional[int] = None
    is_active: bool = True


class Group(GroupBase):
    id: int
    created_at: datetime


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    modality_id: Optional[int] = None
    tutor_id: Optional[int] = None
    is_active: Optional[bool] = None


class GroupWithRelations(Group):
    modality: Optional[Modality] = None
    tutor: Optional[TeacherInfo] = None


class GroupSummary(BaseModel):
    group_id: int
    grupo: str
    carrera: str
    total: int
    modality_id: Optional[int] = None
    tutor_id: Optional[int] = None
    tutor_name: Optional[str] = None


class MigrationAuditResult(BaseModel):
    active_cycle_id: Optional[int] = None
    active_cycle_period: Optional[str] = None
    legacy_students_with_seed_data: int
    student_enrollments_in_active_cycle: int
    legacy_students_missing_enrollment: list[str] = []
    legacy_students_with_group: int
    active_cycle_group_memberships: int
    grades_total: int
    grades_linked_to_course_enrollment: int
    grades_without_course_enrollment: int


class EnrollmentSummaryRow(BaseModel):
    cycle_id: Optional[int] = None
    cycle_period: Optional[str] = None
    career: Optional[str] = None
    modality: Optional[str] = None
    semester: Optional[str] = None
    group_name: Optional[str] = None
    total_students: int


class GradeOutcomeRow(BaseModel):
    assignment_id: Optional[int] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None
    cycle_period: Optional[str] = None
    approved_count: int
    failed_count: int
    in_progress_count: int
    total_records: int


class FinanceSummary(BaseModel):
    total_charges: int
    total_charge_amount: float
    paid_amount: float
    pending_amount: float
    overdue_amount: float
    paid_count: int
    pending_count: int
    overdue_count: int


class BlockedStudentRow(BaseModel):
    student_id: int
    username: str
    full_name: Optional[str] = None
    overdue_charges: int
    overdue_amount: float
    total_pending_amount: float


class AdminOverviewReport(BaseModel):
    cycle_id: Optional[int] = None
    cycle_period: Optional[str] = None
    total_students: int
    active_enrollments: int
    groups_count: int
    teachers_with_assignments: int
    subjects_with_assignments: int
    average_final_score: float
    approval_rate: float
    failed_rate: float
    failed_count: int
    in_progress_count: int
    blocked_students: int
    overdue_amount: float
    pending_services: int


class EnrollmentStatusRow(BaseModel):
    enrollment_status: str
    total_students: int


class TeacherWorkloadRow(BaseModel):
    teacher_username: Optional[str] = None
    teacher_name: Optional[str] = None
    assignments_count: int
    students_count: int
    subjects_count: int
    groups_count: int


class AcademicRiskRow(BaseModel):
    username: str
    full_name: Optional[str] = None
    career: Optional[str] = None
    semester: Optional[str] = None
    group_name: Optional[str] = None
    failed_count: int
    in_progress_count: int
    average_score: float


class ServiceSummaryRow(BaseModel):
    service_type: str
    status: str
    total_requests: int


class ChargeBreakdownRow(BaseModel):
    charge_type: str
    status: str
    total_charges: int
    total_amount: float


class StudentEnrollmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: int
    cycle_id: int
    career_id: Optional[int] = None
    modality_id: Optional[int] = None
    group_id: Optional[int] = None
    semester: Optional[str] = None
    enrollment_status: EnrollmentStatus = EnrollmentStatus.NO_INSCRITO
    is_active: bool = True
    change_reason: Optional[str] = None


class StudentEnrollment(StudentEnrollmentBase):
    id: int
    created_at: datetime
    updated_at: datetime


class StudentEnrollmentWithRelations(StudentEnrollment):
    student: Optional[UserBase] = None
    cycle: Optional[SchoolCycle] = None
    group: Optional[Group] = None
    career: Optional[Career] = None
    modality: Optional[Modality] = None


class CourseEnrollmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_enrollment_id: int
    assignment_id: int
    attempt_type: AttemptType = AttemptType.REGULAR
    status: GradeStatus = GradeStatus.CURSANDO


class CourseEnrollment(CourseEnrollmentBase):
    id: int
    enrolled_at: datetime
    dropped_at: Optional[datetime] = None


class CourseEnrollmentWithRelations(CourseEnrollment):
    student_enrollment: Optional[StudentEnrollmentWithRelations] = None
    assignment: Optional[SubjectAssignment] = None


class CourseEnrollmentCreate(BaseModel):
    username: str
    assignment_id: int
    attempt_type: AttemptType = AttemptType.REGULAR
    status: GradeStatus = GradeStatus.CURSANDO
    create_grade_record: bool = True


class CourseEnrollmentDropRequest(BaseModel):
    dropped_at: Optional[datetime] = None


class MoveStudentGroupRequest(BaseModel):
    username: str
    group_name: Optional[str] = None
    cycle_id: Optional[int] = None
    modality_id: Optional[int] = None
    reason: Optional[str] = None


StudyPlanWithSubjects.model_rebuild()


# ── Página Web ──────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    short_description: Optional[str] = None
    category: str = "portfolio"   # "portfolio" | "evento"
    image_url: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    is_active: bool = True

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    short_description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None

class ProjectOut(BaseModel):
    id: int
    title: str
    short_description: Optional[str] = None
    category: str
    image_url: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    nombre: str
    telefono: str
    email: Optional[str] = None
    programa: Optional[str] = None
    mensaje: Optional[str] = None

class ContactStatusUpdate(BaseModel):
    status: str   # "nuevo" | "contactado" | "inscrito"

class ContactOut(BaseModel):
    id: int
    nombre: str
    telefono: str
    email: Optional[str] = None
    programa: Optional[str] = None
    mensaje: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SuccessStoryCreate(BaseModel):
    name: str
    role: str
    company: Optional[str] = None
    quote: str
    photo_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

class SuccessStoryUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    quote: Optional[str] = None
    photo_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class SuccessStoryOut(BaseModel):
    id: int
    name: str
    role: str
    company: Optional[str] = None
    quote: str
    photo_url: Optional[str] = None
    sort_order: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class TestimonialReelCreate(BaseModel):
    badge_text: str
    badge_color: str = "pink"
    quote: str
    description: Optional[str] = None
    video_url: str
    poster_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

class TestimonialReelUpdate(BaseModel):
    badge_text: Optional[str] = None
    badge_color: Optional[str] = None
    quote: Optional[str] = None
    description: Optional[str] = None
    video_url: Optional[str] = None
    poster_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class TestimonialReelOut(BaseModel):
    id: int
    badge_text: str
    badge_color: str
    quote: str
    description: Optional[str] = None
    video_url: str
    poster_url: Optional[str] = None
    sort_order: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ExtracurricularCourseCreate(BaseModel):
    title: str
    description: str
    level: Optional[str] = None
    color: str = "blue"
    icon: str = "bi-book"
    image_url: Optional[str] = None
    whatsapp_text: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

class ExtracurricularCourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    whatsapp_text: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class ExtracurricularCourseOut(BaseModel):
    id: int
    title: str
    description: str
    level: Optional[str] = None
    color: str
    icon: str
    image_url: Optional[str] = None
    whatsapp_text: Optional[str] = None
    sort_order: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CommunityCreate(BaseModel):
    name: str
    description: str
    icon: str = "bi-people-fill"
    color: str = "blue"
    frequency: Optional[str] = None
    image_url: Optional[str] = None
    member_count: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True

class CommunityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    frequency: Optional[str] = None
    image_url: Optional[str] = None
    member_count: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class CommunityOut(BaseModel):
    id: int
    name: str
    description: str
    icon: str
    color: str
    frequency: Optional[str] = None
    image_url: Optional[str] = None
    member_count: Optional[int] = None
    sort_order: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
