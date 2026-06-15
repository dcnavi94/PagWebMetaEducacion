<?php
$moodleconfig = '/opt/bitnami/moodle/config.php';
if (!is_file($moodleconfig)) {
    $moodleconfig = dirname(__DIR__, 3) . '/config.php';
}
require_once($moodleconfig);

$userid = required_param('userid', PARAM_INT);
$expires = required_param('expires', PARAM_INT);
$target = optional_param('target', '/my/', PARAM_LOCALURL);
$signature = required_param('signature', PARAM_ALPHANUM);
$secret = getenv('UNIVES_SSO_SECRET') ?: '';

if ($secret === '' || $expires < time() || $expires > time() + 120) {
    throw new moodle_exception('invalidkey');
}

$payload = $userid . '|' . $expires . '|' . $target;
$expected = hash_hmac('sha256', $payload, $secret);
if (!hash_equals($expected, $signature)) {
    throw new moodle_exception('invalidkey');
}

$user = core_user::get_user($userid, '*', MUST_EXIST);
core_user::require_active_user($user, true, true);

if (isloggedin() && !isguestuser() && $USER->id !== $user->id) {
    require_logout();
}

if (!isloggedin() || isguestuser()) {
    complete_user_login(get_complete_user_data('id', $user->id));
    \core\session\manager::apply_concurrent_login_limit($user->id, session_id());
}

redirect(new moodle_url($target ?: '/my/'));
