import functools
import hmac
import io
import logging
import sys
import os
import re

import stripe
from urllib.parse import parse_qsl, quote_plus

from typing_extensions import Type, TYPE_CHECKING
from typing import (
    TypeVar,
    Union,
    overload,
    Dict,
    List,
    cast,
    Any,
    Optional,
)

from stripe.stripe_response import StripeResponse

if TYPE_CHECKING:
    from stripe.stripe_object import StripeObject

STRIPE_LOG = os.environ.get("STRIPE_LOG")

logger: logging.Logger = logging.getLogger("stripe")

__all__ = [
    "io",
    "parse_qsl",
    "log_info",
    "log_debug",
    "dashboard_link",
    "logfmt",
]


def is_appengine_dev():
    return "APPENGINE_RUNTIME" in os.environ and "Dev" in os.environ.get(
        "SERVER_SOFTWARE", ""
    )


def _console_log_level():
    if stripe.log in ["debug", "info"]:
        return stripe.log
    elif STRIPE_LOG in ["debug", "info"]:
        return STRIPE_LOG
    else:
        return None


def log_debug(message, **params):
    msg = logfmt(dict(message=message, **params))
    if _console_log_level() == "debug":
        print(msg, file=sys.stderr)
    logger.debug(msg)


def log_info(message, **params):
    msg = logfmt(dict(message=message, **params))
    if _console_log_level() in ["debug", "info"]:
        print(msg, file=sys.stderr)
    logger.info(msg)


def _test_or_live_environment():
    if stripe.api_key is None:
        return
    match = re.match(r"sk_(live|test)_", stripe.api_key)
    if match is None:
        return
    return match.groups()[0]


def dashboard_link(request_id):
    return "https://dashboard.stripe.com/{env}/logs/{reqid}".format(
        env=_test_or_live_environment() or "test", reqid=request_id
    )


def logfmt(props):
    def fmt(key, val):
        # Handle case where val is a bytes or bytesarray
        if hasattr(val, "decode"):
            val = val.decode("utf-8")
        # Check if val is already a string to avoid re-encoding into
        # ascii. Since the code is sent through 2to3, we can't just
        # use unicode(val, encoding='utf8') since it will be
        # translated incorrectly.
        if not isinstance(val, str):
            val = str(val)
        if re.search(r"\s", val):
            val = repr(val)
        # key should already be a string
        if re.search(r"\s", key):
            key = repr(key)
        return u"{key}={val}".format(key=key, val=val)

    return u" ".join([fmt(key, val) for key, val in sorted(props.items())])


# Borrowed from Django's source code
if hasattr(hmac, "compare_digest"):
    # Prefer the stdlib implementation, when available.
    def secure_compare(val1, val2):
        return hmac.compare_digest(val1, val2)

else:

    def secure_compare(val1, val2):
        """
        Returns True if the two strings are equal, False otherwise.
        The time taken is independent of the number of characters that match.
        For the sake of simplicity, this function executes in constant time
        only when the two strings have the same length. It short-circuits when
        they have different lengths.
        """
        if len(val1) != len(val2):
            return False
        result = 0
        if isinstance(val1, bytes) and isinstance(val2, bytes):
            for x, y in zip(val1, val2):
                result |= x ^ y
        else:
            for x, y in zip(val1, val2):
                result |= ord(cast(str, x)) ^ ord(cast(str, y))
        return result == 0


def get_object_classes():
    # This is here to avoid a circular dependency
    from stripe.object_classes import OBJECT_CLASSES

    return OBJECT_CLASSES


Resp = Union[StripeResponse, Dict[str, Any], List["Resp"]]


@overload
def convert_to_stripe_object(
    resp: Union[StripeResponse, Dict[str, Any]],
    api_key: Optional[str] = None,
    stripe_version: Optional[str] = None,
    stripe_account: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> "StripeObject":
    ...


@overload
def convert_to_stripe_object(
    resp: List[Resp],
    api_key: Optional[str] = None,
    stripe_version: Optional[str] = None,
    stripe_account: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> List["StripeObject"]:
    ...


def convert_to_stripe_object(
    resp: Resp,
    api_key: Optional[str] = None,
    stripe_version: Optional[str] = None,
    stripe_account: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Union["StripeObject", List["StripeObject"]]:
    # If we get a StripeResponse, we'll want to return a
    # StripeObject with the last_response field filled out with
    # the raw API response information
    stripe_response = None

    if isinstance(resp, stripe.stripe_response.StripeResponse):
        stripe_response = resp
        resp = cast(Resp, stripe_response.data)

    if isinstance(resp, list):
        return [
            convert_to_stripe_object(
                cast("Union[StripeResponse, Dict[str, Any]]", i),
                api_key,
                stripe_version,
                stripe_account,
            )
            for i in resp
        ]
    elif isinstance(resp, dict) and not isinstance(
        resp, stripe.stripe_object.StripeObject
    ):
        resp = resp.copy()
        klass_name = resp.get("object")
        if isinstance(klass_name, str):
            klass = get_object_classes().get(
                klass_name, stripe.stripe_object.StripeObject
            )
        else:
            klass = stripe.stripe_object.StripeObject

        obj = klass.construct_from(
            resp,
            api_key,
            stripe_version=stripe_version,
            stripe_account=stripe_account,
            last_response=stripe_response,
        )

        # We only need to update _retrieve_params when special params were
        # actually passed. Otherwise, leave it as is as the list / search result
        # constructors will instantiate their own params.
        if (
            params is not None
            and hasattr(obj, "object")
            and (
                (getattr(obj, "object") == "list")
                or (getattr(obj, "object") == "search_result")
            )
        ):
            obj._retrieve_params = params

        return obj
    else:
        return cast("StripeObject", resp)


def convert_to_dict(obj):
    """Converts a StripeObject back to a regular dict.

    Nested StripeObjects are also converted back to regular dicts.

    :param obj: The StripeObject to convert.

    :returns: The StripeObject as a dict.
    """
    if isinstance(obj, list):
        return [convert_to_dict(i) for i in obj]
    # This works by virtue of the fact that StripeObjects _are_ dicts. The dict
    # comprehension returns a regular dict and recursively applies the
    # conversion to each value.
    elif isinstance(obj, dict):
        return {k: convert_to_dict(v) for k, v in obj.items()}
    else:
        return obj


@overload
def populate_headers(
    idempotency_key: str,
) -> Dict[str, str]:
    ...


@overload
def populate_headers(idempotency_key: None) -> None:
    ...


def populate_headers(
    idempotency_key: Union[str, None]
) -> Union[Dict[str, str], None]:
    if idempotency_key is not None:
        return {"Idempotency-Key": idempotency_key}
    return None


T = TypeVar("T")


def read_special_variable(
    params: Optional[Dict[str, Any]], key_name: str, default_value: T
) -> Optional[T]:
    value = default_value
    params_value = None

    if params is not None and key_name in params:
        params_value = params[key_name]
        del params[key_name]

    if value is None:
        value = params_value

    return value


def merge_dicts(x, y):
    z = x.copy()
    z.update(y)
    return z


def sanitize_id(id):
    quotedId = quote_plus(id)
    return quotedId


class class_method_variant(object):
    def __init__(self, class_method_name):
        self.class_method_name = class_method_name

    def __call__(self, method):
        self.method = method
        return self

    def __get__(self, obj, objtype: Optional[Type[Any]] = None):
        @functools.wraps(self.method)
        def _wrapper(*args, **kwargs):
            if obj is not None:
                # Method was called as an instance method, e.g.
                # instance.method(...)
                return self.method(obj, *args, **kwargs)
            elif (
                len(args) > 0
                and objtype is not None
                and isinstance(args[0], objtype)
            ):
                # Method was called as a class method with the instance as the
                # first argument, e.g. Class.method(instance, ...) which in
                # Python is the same thing as calling an instance method
                return self.method(args[0], *args[1:], **kwargs)
            else:
                # Method was called as a class method, e.g. Class.method(...)
                class_method = getattr(objtype, self.class_method_name)
                return class_method(*args, **kwargs)

        return _wrapper
