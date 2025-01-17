import pytest
from ert.config import ErtConfig
from ropt.config.enopt import EnOptConfig

from everest.config import EverestConfig
from everest.optimizer.everest2ropt import everest2ropt
from everest.simulator.everest2res import everest2res
from everest.suite import _EverestWorkflow
from tests.test_config_validation import has_error
from tests.utils import relpath, tmpdir

CONFIG_DIR = relpath("test_data", "mocked_test_case")
CONFIG_FILE = "config_multi_objectives.yml"


@tmpdir(CONFIG_DIR)
def test_config_multi_objectives():
    config = EverestConfig.load_file(CONFIG_FILE)
    config_dict = config.to_dict()

    obj_funcs = config_dict["objective_functions"]
    assert len(obj_funcs) == 2

    obj_funcs[0]["weight"] = 1.0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Weight should be given either for all of the"
        " objectives or for none of them",
    )  # weight given only for some obj

    obj_funcs[1]["weight"] = 3
    assert (
        len(EverestConfig.lint_config_dict(config_dict)) == 0
    )  # weight given for all the objectivs

    obj_funcs.append({"weight": 1, "normalization": 1})
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Field required",
    )  # no name

    obj_funcs[-1]["name"] = " test_obj"
    obj_funcs[-1]["weight"] = -0.3
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Input should be greater than 0",
    )  # negative weight

    obj_funcs[-1]["weight"] = 0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Input should be greater than 0",
    )  # 0 weight

    obj_funcs[-1]["weight"] = 1
    obj_funcs[-1]["normalization"] = 0
    assert has_error(
        EverestConfig.lint_config_dict(config_dict),
        match="Normalization value cannot be zero",
    )  # 0 normalization

    obj_funcs[-1]["normalization"] = -125
    assert (
        len(EverestConfig.lint_config_dict(config_dict)) == 0
    )  # negative normalization is ok)

    obj_funcs.pop()
    assert len(EverestConfig.lint_config_dict(config_dict)) == 0

    # test everest initialization
    _EverestWorkflow(config)


@tmpdir(CONFIG_DIR)
def test_multi_objectives2res():
    config = EverestConfig.load_file(CONFIG_FILE)
    res = everest2res(config, site_config=ErtConfig.read_site_config())
    ErtConfig.from_dict(config_dict=res)


@tmpdir(CONFIG_DIR)
def test_multi_objectives2ropt():
    # pylint: disable=unbalanced-tuple-unpacking
    config = EverestConfig.load_file(CONFIG_FILE)
    config_dict = config.to_dict()
    ever_objs = config_dict["objective_functions"]
    ever_objs[0]["weight"] = 1.33
    ever_objs[0]["normalization"] = 1
    ever_objs[1]["weight"] = 3.1
    assert len(EverestConfig.lint_config_dict(config_dict)) == 0

    norm = ever_objs[0]["weight"] + ever_objs[1]["weight"]

    enopt_config = EnOptConfig.model_validate(
        everest2ropt(EverestConfig.model_validate(config_dict))
    )
    assert len(enopt_config.objective_functions.names) == 2
    assert enopt_config.objective_functions.names[1] == ever_objs[1]["name"]
    assert enopt_config.objective_functions.weights[1] == ever_objs[1]["weight"] / norm
    assert enopt_config.objective_functions.names[0] == ever_objs[0]["name"]
    assert enopt_config.objective_functions.weights[0] == ever_objs[0]["weight"] / norm
    assert enopt_config.objective_functions.scales[0] == ever_objs[0]["normalization"]


@pytest.mark.integration_test
@tmpdir(CONFIG_DIR)
def test_multi_objectives_run():
    config = EverestConfig.load_file(CONFIG_FILE)
    workflow = _EverestWorkflow(config)
    workflow.start_optimization()

    # Loop through objective functions in config and ensure they are in the
    # result object
    for obj in config.objective_functions:
        assert obj.name in workflow.result.expected_objectives
