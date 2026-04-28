import httpx
import logging
from urllib.parse import urlparse
from typing import Any, Optional

from .config import settings

logger = logging.getLogger("unives.moodle")


class MoodleClient:
    def __init__(self):
        self.base_url = settings.MOODLE_BASE_URL
        self.token = settings.MOODLE_REST_TOKEN
        self.public_host = urlparse(settings.MOODLE_PUBLIC_URL).netloc or None
        self._last_error: Optional[str] = None

    def _set_last_error(self, message: str) -> None:
        self._last_error = message

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def _is_success_without_payload(self, result: Optional[Any]) -> bool:
        if result is None:
            return self.get_last_error() is None
        return isinstance(result, dict) and "exception" not in result

    async def _post(self, function: str, params: dict) -> Optional[Any]:
        self._last_error = None
        if not self.token:
            msg = "MOODLE_REST_TOKEN no esta configurado. Omitiendo llamada a Moodle."
            logger.warning(msg)
            self._set_last_error(msg)
            return None

        data = {
            "wstoken": self.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        data.update(params)
        headers = {}
        if self.public_host:
            headers["Host"] = self.public_host

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                response = await client.post(self.base_url, data=data, headers=headers)
                if response.status_code in (301, 302, 303, 307, 308):
                    response = await client.post(self.base_url, data=data, headers=headers)

                response.raise_for_status()
                result = response.json()
                if isinstance(result, dict) and "exception" in result:
                    message = result.get("message") or result.get("errorcode") or "Error desconocido en Moodle"
                    logger.error("Error en Moodle API (%s): %s", function, message)
                    self._set_last_error(f"{function}: {message}")
                    return None
                return result
        except httpx.RequestError as exc:
            msg = f"Fallo en la conexion con Moodle: {exc}"
            logger.error(msg)
            self._set_last_error(msg)
            return None
        except Exception as exc:
            msg = f"Error inesperado al llamar a Moodle: {exc}"
            logger.error(msg)
            self._set_last_error(msg)
            return None

    async def create_user(self, username: str, password: str, firstname: str, lastname: str, email: str) -> Optional[int]:
        result = await self._post(
            "core_user_create_users",
            {
                "users[0][username]": username,
                "users[0][password]": password,
                "users[0][firstname]": firstname,
                "users[0][lastname]": lastname,
                "users[0][email]": email,
            },
        )
        if isinstance(result, list) and result:
            return result[0].get("id")
        return None

    async def get_user_by_username(self, username: str) -> Optional[int]:
        result = await self._post(
            "core_user_get_users",
            {"criteria[0][key]": "username", "criteria[0][value]": username},
        )
        if result and "users" in result and result["users"]:
            return result["users"][0].get("id")
        return None

    async def get_user_by_email(self, email: str) -> Optional[int]:
        if not email:
            return None
        result = await self._post(
            "core_user_get_users",
            {"criteria[0][key]": "email", "criteria[0][value]": email},
        )
        if result and "users" in result and result["users"]:
            return result["users"][0].get("id")
        return None

    async def check_user_exists(self, user_id: int) -> bool:
        result = await self._post(
            "core_user_get_users_by_field",
            {"field": "id", "values[0]": str(user_id)},
        )
        return isinstance(result, list) and any(u.get("id") == user_id for u in result)

    async def update_user_account(
        self,
        *,
        user_id: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        firstname: Optional[str] = None,
        lastname: Optional[str] = None,
        email: Optional[str] = None,
    ) -> bool:
        params: dict[str, Any] = {"users[0][id]": int(user_id)}
        if username is not None:
            params["users[0][username]"] = username
        if password is not None:
            params["users[0][password]"] = password
        if firstname is not None:
            params["users[0][firstname]"] = firstname
        if lastname is not None:
            params["users[0][lastname]"] = lastname
        if email is not None:
            params["users[0][email]"] = email

        result = await self._post("core_user_update_users", params)
        return self._is_success_without_payload(result)

    async def create_course_admin(
        self,
        *,
        fullname: str,
        shortname: str,
        category_id: int = 1,
        summary: Optional[str] = None,
        format_name: Optional[str] = None,
        visible: Optional[bool] = None,
        startdate: Optional[int] = None,
        enddate: Optional[int] = None,
        idnumber: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Optional[dict]:
        params: dict[str, Any] = {
            "courses[0][fullname]": fullname,
            "courses[0][shortname]": shortname,
            "courses[0][categoryid]": category_id,
        }
        if summary is not None:
            params["courses[0][summary]"] = summary
            params["courses[0][summaryformat]"] = 1
        if format_name:
            params["courses[0][format]"] = format_name
        if visible is not None:
            params["courses[0][visible]"] = 1 if visible else 0
        if startdate is not None:
            params["courses[0][startdate]"] = int(startdate)
        if enddate is not None:
            params["courses[0][enddate]"] = int(enddate)
        if idnumber:
            params["courses[0][idnumber]"] = idnumber
        if lang:
            params["courses[0][lang]"] = lang

        result = await self._post("core_course_create_courses", params)
        if isinstance(result, list) and result:
            return result[0]
        return None

    async def enrol_user(self, user_id: int, course_id: int, role_id: int = 5) -> bool:
        result = await self._post(
            "enrol_manual_enrol_users",
            {
                "enrolments[0][roleid]": role_id,
                "enrolments[0][userid]": user_id,
                "enrolments[0][courseid]": course_id,
            },
        )
        return self._is_success_without_payload(result)

    async def assign_system_role(
        self,
        user_id: int,
        role_id: int,
        context_id: Optional[int] = None,
        context_level: Optional[str] = None,
        instance_id: Optional[int] = None,
    ) -> bool:
        params = {
            "assignments[0][roleid]": role_id,
            "assignments[0][userid]": user_id,
        }
        if context_id is not None:
            params["assignments[0][contextid]"] = context_id
        if context_level:
            params["assignments[0][contextlevel]"] = context_level
        if instance_id is not None:
            params["assignments[0][instanceid]"] = instance_id
        result = await self._post("core_role_assign_roles", params)
        return self._is_success_without_payload(result)

    async def get_user_courses(self, user_id: int) -> Optional[list]:
        result = await self._post("core_enrol_get_users_courses", {"userid": user_id})
        return result if isinstance(result, list) else None

    async def get_course_contents(self, course_id: int) -> Optional[list]:
        result = await self._post("core_course_get_contents", {"courseid": course_id})
        return result if isinstance(result, list) else None

    async def get_site_info(self) -> Optional[dict]:
        result = await self._post("core_webservice_get_site_info", {})
        return result if isinstance(result, dict) else None

    async def get_users(self, query: str, limit: int = 25) -> Optional[list]:
        q = (query or "").strip()
        if not q:
            result = await self._post("core_user_get_users", {"criteria[0][key]": "idnumber", "criteria[0][value]": ""})
            if isinstance(result, dict):
                return (result.get("users") or [])[:limit]
            return None

        collected = []
        seen_ids = set()

        def _add_users(users: list) -> None:
            for user in users:
                uid = user.get("id")
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                collected.append(user)

        for field in ("username", "email"):
            result = await self._post(
                "core_user_get_users_by_field",
                {"field": field, "values[0]": q.lower() if field == "username" else q},
            )
            if isinstance(result, list):
                _add_users(result)

        for key in ("firstname", "lastname"):
            result = await self._post(
                "core_user_get_users",
                {"criteria[0][key]": key, "criteria[0][value]": q},
            )
            if isinstance(result, dict):
                _add_users(result.get("users") or [])

        filtered = [
            u
            for u in collected
            if q.lower() in (u.get("fullname") or "").lower()
            or q.lower() in (u.get("firstname") or "").lower()
            or q.lower() in (u.get("lastname") or "").lower()
            or q.lower() in (u.get("username") or "").lower()
            or q.lower() in (u.get("email") or "").lower()
        ]
        return filtered[:limit]

    async def search_courses(self, query: str) -> Optional[list]:
        result = await self._post(
            "core_course_search_courses",
            {"criterianame": "search", "criteriavalue": query or ""},
        )
        if isinstance(result, dict):
            return result.get("courses") or []
        return None

    async def get_enrolled_users(self, course_id: int) -> Optional[list]:
        result = await self._post("core_enrol_get_enrolled_users", {"courseid": course_id})
        return result if isinstance(result, list) else None

    async def check_course_exists(self, course_id: int) -> bool:
        result = await self._post(
            "core_course_get_courses_by_field",
            {"field": "id", "value": str(course_id)},
        )
        if isinstance(result, dict) and isinstance(result.get("courses"), list):
            return any(course.get("id") == course_id for course in result["courses"])
        return False


moodle_client = MoodleClient()
