import contextlib
import logging
import os
import pathlib
import shutil
import sys
import tempfile
from io import StringIO
from unittest import mock

import decorator
import pytest

from everest.bin.main import start_everest
from everest.config import EverestConfig
from everest.detached import ServerStatus, everserver_status
from everest.jobs import script_names
from everest.util import has_opm
from everest.util.forward_models import collect_forward_models


def skipif_no_opm(function):
    """Decorator to skip a test if opm is not available

    If this decorator is used on a test, there should be a corresponding
    test that verifies the expected behavior in case opm is not available
    (use the hide_opm decorator)
    """
    return pytest.mark.skipif(not has_opm(), reason="OPM not found")(function)


def skipif_no_simulator(function):
    """Decorator to skip a test if no project res is available is not available"""
    return pytest.mark.skipif(
        condition=os.environ.get("NO_PROJECT_RES", False),
        reason="Skipping tests when no access to /project/res",
    )(function)


def hide_opm(function):
    """Decorator for faking that the opm module is not present"""

    def wrapper(function, *args, **kwargs):
        with mock.patch("everest.util.has_opm", return_value=False):
            return function(*args, **kwargs)

    return decorator.decorator(wrapper, function)


def relpath(*path):
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), *path)


def tmpdir(path, teardown=True):
    """Decorator based on the  `tmp` context"""

    def real_decorator(function):
        def wrapper(function, *args, **kwargs):
            with tmp(path, teardown=teardown):
                return function(*args, **kwargs)

        return decorator.decorator(wrapper, function)

    return real_decorator


@contextlib.contextmanager
def tmp(path=None, teardown=True):
    """Create and go into tmp directory, returns the path.

    This function creates a temporary directory and enters that directory.  The
    returned object is the path to the created directory.

    If @path is not specified, we create an empty directory, otherwise, it must
    be a path to an existing directory.  In that case, the directory will be
    copied into the temporary directory.

    If @teardown is True (defaults to True), the directory is (attempted)
    deleted after context, otherwise it is kept as is.

    """
    cwd = os.getcwd()
    fname = tempfile.NamedTemporaryFile().name

    if path:
        if not os.path.isdir(path):
            logging.debug("tmp:raise no such path")
            raise IOError("No such directory: %s" % path)
        shutil.copytree(path, fname)
    else:
        # no path to copy, create empty dir
        os.mkdir(fname)

    os.chdir(fname)

    yield fname  # give control to caller scope

    os.chdir(cwd)

    if teardown:
        try:
            shutil.rmtree(fname)
        except OSError as oserr:
            logging.debug("tmp:rmtree failed %s (%s)" % (fname, oserr))
            shutil.rmtree(fname, ignore_errors=True)


@contextlib.contextmanager
def capture_streams():
    """Context that allows capturing text sent to stdout and stderr

    Use as follow:
    with capture_streams() as (out, err):
        foo()
    assert( 'output of foo' in out.getvalue())
    """
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield new_out, new_err
    finally:
        sys.stdout, sys.stderr = old_out, old_err


@contextlib.contextmanager
def capture_logger(name=None):
    """Context that allows capturing text sent to a logger

    Use as follow:
    with capture_logger('everest') as logstream:
        foo()
    assert( 'log of foo' in logstream)
    """
    logstream = StringIO()
    loghandler = logging.StreamHandler(logstream)
    loghandler.setLevel(logging.DEBUG)  # lowest, so only logger level matters
    logger = logging.getLogger(name) if name is not None else logging.getLogger()
    try:
        logger.addHandler(loghandler)
        yield logstream
    finally:
        logger.removeHandler(loghandler)


def satisfy(predicate):
    """Return a class that equals to an obj if predicate(obj) is True

    This method is expected to be used with `assert_called_with()` on mocks.
    An example can be found in `test_everest_entry.test_everest_run`
    Inspired by
    https://stackoverflow.com/questions/21611559/assert-that-a-method-was-called-with-one-argument-out-of-several
    """

    class _PredicateChecker(object):
        def __eq__(self, obj):
            return predicate(obj)

    return _PredicateChecker()


def satisfy_type(the_type):
    """Specialization of satisfy for checking object type"""
    return satisfy(lambda obj: isinstance(obj, the_type))


def satisfy_callable():
    """Specialization of satisfy for checking that object is callable"""
    return satisfy(lambda obj: callable(obj))


class MockParser(object):
    """
    Small class that contains the necessary functions in order to test custom
    validation functions used with the argparse module
    """

    def __init__(self):
        self.error_msg = None

    def get_error(self):
        return self.error_msg

    def error(self, value=None):
        self.error_msg = value


def everest_default_jobs(output_dir):
    return [
        (
            script_name,
            os.path.join(output_dir, ".jobs", "_%s" % script_name),
        )
        for script_name in script_names
    ] + [(job["name"], job["path"]) for job in collect_forward_models()]


def create_cached_mocked_test_case(request, monkeypatch) -> pathlib.Path:
    """This function will run everest to create some mocked data,
    this is quite slow, but the results will be cached. If something comes
    out of sync, clear the cache and start again. (rm -fr .pytest_cache/)
    """
    config_file = "mocked_multi_batch.yml"
    config_path = relpath("test_data", "mocked_test_case")
    cache_path = request.config.cache.mkdir(
        "snake_oil_data" + os.environ.get("PYTEST_XDIST_WORKER", "")
    )
    if not os.path.exists(cache_path / "mocked_run"):
        monkeypatch.chdir(cache_path)
        shutil.copytree(config_path, "mocked_run")
        monkeypatch.chdir("mocked_run")
        start_everest(["everest", "run", config_file])
        config = EverestConfig.load_file(config_file)
        status = everserver_status(config)
        assert status["status"] == ServerStatus.completed
    return cache_path / "mocked_run"
