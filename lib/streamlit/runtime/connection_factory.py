# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib
import re
from typing import Any, Dict, Optional, Type, TypeVar, overload

from typing_extensions import Final, Literal

from streamlit.connections import SQL, ExperimentalBaseConnection, Snowpark
from streamlit.errors import StreamlitAPIException
from streamlit.runtime.caching import cache_resource
from streamlit.runtime.metrics_util import gather_metrics
from streamlit.runtime.secrets import secrets_singleton

# NOTE: Adding support for a new first party connection requires:
#   1. Adding the new connection name and class to this dict.
#   2. Writing a new @overload for connection_factory.
#   3. Updating test_get_first_party_connection_helper in connection_factory_test.py.
FIRST_PARTY_CONNECTIONS = {
    "snowpark": Snowpark,
    "sql": SQL,
}
MODULE_EXTRACTION_REGEX = re.compile(r"No module named \'(.+)\'")
MODULES_TO_PYPI_PACKAGES: Final[Dict[str, str]] = {
    "sqlalchemy": "sqlalchemy",
    "snowflake": "snowflake-snowpark-python",
    "snowflake.snowpark": "snowflake-snowpark-python",
}

# The ExperimentalBaseConnection bound is parameterized to `Any` below as subclasses of
# ExperimentalBaseConnection are responsible for binding the type parameter of
# ExperimentalBaseConnection to a concrete type, but the type it gets bound to isn't
# important to us here.
ConnectionClass = TypeVar("ConnectionClass", bound=ExperimentalBaseConnection[Any])


# NOTE: The order of the decorators below is important: @gather_metrics must be above
# @cache_resource so that it is called even if the return value of _create_connection
# is cached.
@gather_metrics("experimental_connection")
@cache_resource
def _create_connection(
    name: str, connection_class: Type[ConnectionClass], **kwargs
) -> ConnectionClass:
    """Create an instance of connection_class with the given name and kwargs.

    This function is useful because it allows us to @gather_metrics at a point where
    connection_class must be a concrete type. The public-facing connection API allows
    the user to specify the connection class to use as a string literal for convenience.
    """

    if not issubclass(connection_class, ExperimentalBaseConnection):
        raise StreamlitAPIException(
            f"{connection_class} is not a subclass of ExperimentalBaseConnection!"
        )

    return connection_class(connection_name=name, **kwargs)


def _get_first_party_connection(connection_class: str):
    if connection_class in FIRST_PARTY_CONNECTIONS:
        return FIRST_PARTY_CONNECTIONS[connection_class]

    raise StreamlitAPIException(
        f"Invalid connection '{connection_class}'. "
        f"Supported connection classes: {FIRST_PARTY_CONNECTIONS}"
    )


@overload
def connection_factory(
    name: str, type: Literal["sql"], autocommit: bool = False, **kwargs
) -> SQL:
    pass


@overload
def connection_factory(name: str, type: Literal["snowpark"], **kwargs) -> Snowpark:
    pass


@overload
def connection_factory(
    name: str, type: Type[ConnectionClass], **kwargs
) -> ConnectionClass:
    pass


@overload
def connection_factory(
    name: str, type: Optional[str], **kwargs
) -> ExperimentalBaseConnection[Any]:
    pass


def connection_factory(name, type=None, **kwargs):
    """TODO(vdonato): Write a docstring (maybe with the help of the documentation team).

    The docstring should describe:
      * Using st.connection with one of our first party connections by passing a string
        literal as the type.
      * Plugging your own ConnectionClass into st.experimental_connection.
    """
    if type is None:
        secrets_singleton.load_if_toml_exists()

        # The user didn't specify a type, so we try to pull it out from their
        # secrets.toml file. NOTE: we're okay with any of the dict lookups below
        # exploding with a KeyError since, if type isn't explicitly specified here, it
        # must be the case that it's defined in secrets.toml and should raise an
        # Exception otherwise.
        type = secrets_singleton["connections"][name]["type"]

    # type is a nice kwarg name for the st.experimental_connection user but is annoying
    # to work with since it conflicts with the builtin function name and thus gets
    # syntax highlighted.
    connection_class = type

    if isinstance(connection_class, str):
        # We assume that a connection_class specified via string is either the fully
        # qualified name of a class (its module and exported classname) or the string
        # literal shorthand for one of our first party connections. In the former case,
        # connection_class will always contain a "." in its name.
        if "." in connection_class:
            parts = connection_class.split(".")
            classname = parts.pop()
            connection_module = importlib.import_module(".".join(parts))
            connection_class = getattr(connection_module, classname)
        else:
            connection_class = _get_first_party_connection(connection_class)

    # At this point, connection_class should be of type Type[ConnectionClass].
    try:
        return _create_connection(name, connection_class, **kwargs)
    except ModuleNotFoundError as e:
        err_string = str(e)
        missing_module = re.search(MODULE_EXTRACTION_REGEX, err_string)

        # TODO(vdonato): Finalize these error messages.
        extra_info = "You may be missing a dependency required to use this connection."
        if missing_module:
            pypi_package = MODULES_TO_PYPI_PACKAGES.get(missing_module.group(1))
            if pypi_package:
                extra_info = f"You need to install the '{pypi_package}' package to use this connection."

        raise ModuleNotFoundError(f"{str(e)}. {extra_info}")