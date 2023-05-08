from datetime import date, datetime, timedelta
from functools import wraps
from typing import Optional, cast

import redis
from delphi.epidata.common.logger import get_structured_logger
from flask import g, request
from werkzeug.exceptions import Unauthorized
from werkzeug.local import LocalProxy

from ._common import app, get_real_ip_addr
from ._config import (API_KEY_REQUIRED_STARTING_AT, REDIS_HOST, REDIS_PASSWORD,
                      URL_PREFIX)
from .admin.models import User, UserRole

API_KEY_HARD_WARNING = API_KEY_REQUIRED_STARTING_AT - timedelta(days=14)
API_KEY_SOFT_WARNING = API_KEY_HARD_WARNING - timedelta(days=14)

API_KEY_WARNING_TEXT = (
    "an api key will be required starting at {}, go to https://delphi.cmu.edu to request one".format(
        API_KEY_REQUIRED_STARTING_AT
    )
)

TESTING_MODE = app.config.get("TESTING", False)


logger = get_structured_logger("api_security")


def resolve_auth_token() -> Optional[str]:
    for n in ("auth", "api_key", "token"):
        if n in request.values:
            return request.values[n]
    # username password
    if request.authorization and request.authorization.username == "epidata":
        return request.authorization.password
    # bearer token authentication
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :]
    return None


def show_soft_api_key_warning() -> bool:
    n = date.today()
    return not current_user and not TESTING_MODE and API_KEY_SOFT_WARNING <= n < API_KEY_HARD_WARNING

def show_hard_api_key_warning() -> bool:
    n = date.today()
    return not current_user and not TESTING_MODE and API_KEY_HARD_WARNING <= n < API_KEY_REQUIRED_STARTING_AT

def require_api_key() -> bool:
    n = date.today()
    return not TESTING_MODE and API_KEY_REQUIRED_STARTING_AT <= n




def _get_current_user():
    if "user" not in g:
        api_key = resolve_auth_token()
        user = User.find_user(api_key=api_key)
        if api_key and user is None:
            raise Unauthorized("Provided API Key does not exist. Please, check your API Key and try again.")
        g.user = user
        if user is not None:
            logger.info(
                "Received API request with API Key",
                method=request.method,
                url=request.url,
                path=request.full_path,
                form_args=request.form,
                req_length=request.content_length,
                remote_addr=request.remote_addr,
                real_remote_addr=get_real_ip_addr(request),
                api_key=user.api_key,
                user_agent=request.user_agent.string,
            )
        else:
            logger.info(
                "Received API request witout API Key",
                method=request.method,
                url=request.url,
                path=request.full_path,
                form_args=request.form,
                req_length=request.content_length,
                remote_addr=request.remote_addr,
                real_remote_addr=get_real_ip_addr(request),
                user_agent=request.user_agent.string,
            )
    return g.user


current_user: User = cast(User, LocalProxy(_get_current_user))


def register_user_role(role_name: str) -> None:
    UserRole.create_role(role_name)


def _is_public_route() -> bool:
    public_routes_list = ["lib", "admin", "version"]
    for route in public_routes_list:
        if request.path.startswith(f"{URL_PREFIX}/{route}"):
            return True
    return False


@app.before_request
def resolve_user():
    if _is_public_route():
        return
    _get_current_user()


def require_role(required_role: str):
    def decorator_wrapper(f):
        if not required_role:
            return f

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user or not current_user.has_role(required_role):
                raise Unauthorized
            return f(*args, **kwargs)

        return decorated_function

    return decorator_wrapper


@app.after_request
def update_key_last_time_used(response):
    if TESTING_MODE or _is_public_route():
        return response
    r = redis.Redis(host=REDIS_HOST, password=REDIS_PASSWORD)
    if g.user is not None:
        r.set(f"LAST_USED/{g.user.api_key}", datetime.strftime(datetime.now(), "%Y-%m-%d"))
    return response
