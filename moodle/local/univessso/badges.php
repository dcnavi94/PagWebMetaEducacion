<?php
$moodleconfig = '/opt/bitnami/moodle/config.php';
if (!is_file($moodleconfig)) {
    $moodleconfig = dirname(__DIR__, 3) . '/config.php';
}
require_once($moodleconfig);
require_once($CFG->dirroot . '/lib/badgeslib.php');
require_once($CFG->dirroot . '/badges/classes/badge.php');

header('Content-Type: application/json; charset=utf-8');

function unives_badges_fail(string $message, int $status = 400): void {
    http_response_code($status);
    echo json_encode(['ok' => false, 'message' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

function unives_badges_seed(): array {
    global $DB, $CFG;
    $definitions = [
        'Excelencia Académica' => 'Reconoce un desempeño académico sobresaliente y resultados de alta calidad.',
        'Participación Destacada' => 'Reconoce aportaciones constantes, preguntas valiosas y participación activa.',
        'Trabajo en Equipo' => 'Reconoce colaboración, liderazgo positivo y apoyo efectivo al grupo.',
        'Constancia' => 'Reconoce disciplina, cumplimiento y esfuerzo sostenido durante el curso.',
    ];
    $ids = [];
    foreach ($definitions as $name => $description) {
        $badge = $DB->get_record('badge', ['name' => $name, 'type' => BADGE_TYPE_SITE]);
        if (!$badge) {
            $now = time();
            $record = (object) [
                'name' => $name,
                'description' => $description,
                'timecreated' => $now,
                'timemodified' => $now,
                'usercreated' => 2,
                'usermodified' => 2,
                'issuername' => 'UNIVES',
                'issuerurl' => $CFG->wwwroot,
                'issuercontact' => 'admin@unives.local',
                'expiredate' => null,
                'expireperiod' => null,
                'type' => BADGE_TYPE_SITE,
                'courseid' => null,
                'message' => '¡Felicidades! Has recibido la insignia "' . $name . '".',
                'messagesubject' => 'Nueva insignia UNIVES',
                'attachment' => 0,
                'notification' => 0,
                'status' => BADGE_STATUS_ACTIVE,
                'nextcron' => null,
                'version' => '2.0',
                'language' => 'es',
                'imagecaption' => $name,
            ];
            $record->id = $DB->insert_record('badge', $record);
            $badge = $record;
        }
        $ids[] = (int) $badge->id;
    }
    return $ids;
}

function unives_user_enrolled(int $userid, int $courseid): bool {
    global $DB;
    return $DB->record_exists_sql(
        'SELECT 1
           FROM {user_enrolments} ue
           JOIN {enrol} e ON e.id = ue.enrolid
          WHERE ue.userid = :userid AND e.courseid = :courseid AND ue.status = 0',
        ['userid' => $userid, 'courseid' => $courseid]
    );
}

$action = required_param('action', PARAM_ALPHANUMEXT);
$timestamp = required_param('timestamp', PARAM_INT);
$teacherid = optional_param('teacherid', 0, PARAM_INT);
$userid = optional_param('userid', 0, PARAM_INT);
$courseid = optional_param('courseid', 0, PARAM_INT);
$badgeid = optional_param('badgeid', 0, PARAM_INT);
$signature = required_param('signature', PARAM_ALPHANUM);
$secret = getenv('UNIVES_SSO_SECRET') ?: '';

if ($secret === '' || abs(time() - $timestamp) > 120) {
    unives_badges_fail('Solicitud expirada o integración no configurada', 401);
}
$payload = implode('|', [$timestamp, $action, $teacherid, $userid, $courseid, $badgeid]);
$expected = hash_hmac('sha256', $payload, $secret);
if (!hash_equals($expected, $signature)) {
    unives_badges_fail('Firma inválida', 401);
}

$catalogids = unives_badges_seed();

if ($action === 'catalog') {
    if (!$teacherid || !$courseid || !unives_user_enrolled($teacherid, $courseid)) {
        unives_badges_fail('El docente no está enrolado en este curso', 403);
    }
    $badges = $DB->get_records_list('badge', 'id', $catalogids, 'name ASC');
    echo json_encode([
        'ok' => true,
        'badges' => array_values(array_map(static function($badge) {
            return [
                'id' => (int) $badge->id,
                'name' => $badge->name,
                'description' => $badge->description,
                'status' => (int) $badge->status,
            ];
        }, $badges)),
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'user') {
    if (!$userid) {
        unives_badges_fail('Usuario requerido');
    }
    $records = $DB->get_records_sql(
        'SELECT bi.id AS issueid, bi.dateissued, bi.uniquehash,
                b.id, b.name, b.description, b.issuername,
                ma.issuerid, ma.issuerrole
           FROM {badge_issued} bi
           JOIN {badge} b ON b.id = bi.badgeid
      LEFT JOIN {badge_manual_award} ma
             ON ma.badgeid = b.id AND ma.recipientid = bi.userid
          WHERE bi.userid = :userid
       ORDER BY bi.dateissued DESC',
        ['userid' => $userid]
    );
    $badges = [];
    foreach ($records as $record) {
        $issuer = $record->issuerid ? $DB->get_record('user', ['id' => $record->issuerid]) : null;
        $badges[] = [
            'id' => (int) $record->id,
            'issue_id' => (int) $record->issueid,
            'name' => $record->name,
            'description' => $record->description,
            'issuer_name' => $issuer ? fullname($issuer) : $record->issuername,
            'date_issued' => (int) $record->dateissued,
            'unique_hash' => $record->uniquehash,
        ];
    }
    echo json_encode(['ok' => true, 'badges' => $badges], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($action === 'award') {
    if (!$teacherid || !$userid || !$courseid || !$badgeid) {
        unives_badges_fail('Faltan datos para entregar la insignia');
    }
    if (!in_array($badgeid, $catalogids, true)) {
        unives_badges_fail('Insignia no permitida', 403);
    }
    if (!unives_user_enrolled($teacherid, $courseid) || !unives_user_enrolled($userid, $courseid)) {
        unives_badges_fail('Docente y alumno deben pertenecer al curso', 403);
    }
    $badge = new \core_badges\badge($badgeid);
    if ($badge->is_issued($userid)) {
        unives_badges_fail('El alumno ya tiene esta insignia', 409);
    }
    global $DB;
    $manual = (object) [
        'badgeid' => $badgeid,
        'recipientid' => $userid,
        'issuerid' => $teacherid,
        'issuerrole' => 3,
        'datemet' => time(),
    ];
    $DB->insert_record('badge_manual_award', $manual);
    $badge->issue($userid, true);
    echo json_encode(['ok' => true, 'message' => 'Insignia entregada correctamente'], JSON_UNESCAPED_UNICODE);
    exit;
}

unives_badges_fail('Acción no soportada', 404);
