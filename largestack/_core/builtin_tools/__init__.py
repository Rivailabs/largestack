from largestack._core.builtin_tools.web import web_search, web_fetch
from largestack._core.builtin_tools.code import code_execute
from largestack._core.builtin_tools.files import read_file, write_file
from largestack._core.builtin_tools.http_tool import http_request
from largestack._core.builtin_tools.calc import calculator
from largestack._core.builtin_tools.shell import shell_command
from largestack._core.builtin_tools.db import database_query
from largestack._core.builtin_tools.time_tool import get_current_time

ALL_BUILTIN = [web_search, web_fetch, code_execute, read_file, write_file,
               http_request, calculator, shell_command, database_query, get_current_time]
