import pytest
from pydantic import ValidationError
from src.models import ProbesFile


VALID_PROBES = {
    "scrape_configs": [
        {
            "job_name": "check-charmhub-connectivity",
            "metrics_path": "/probe",
            "params": {"module": ["http_2xx"]},
            "modules": ["http_2xx"],
            "static_configs": [
                {"targets": ["https://charmhub.io", "https://ububtu.com"]}
            ],
        }
    ]
}


def test_valid_probes_file_passes():
    probes = ProbesFile(**VALID_PROBES)
    assert probes.scrape_configs[0].job_name == "check-charmhub-connectivity"


def test_empty_job_name_fails():
    data = VALID_PROBES.copy()
    data["scrape_configs"][0]["job_name"] = ""

    with pytest.raises(ValidationError) as exc:
        ProbesFile(**data)

    assert "job_name cannot be empty" in str(exc.value)


def test_wrong_metrics_path_fails():
    data = VALID_PROBES.copy()
    data["scrape_configs"][0]["metrics_path"] = "/metrics"

    with pytest.raises(ValidationError) as exc:
        ProbesFile(**data)

    assert 'metrics_path must be "/probe"' in str(exc.value)


def test_missing_targets_fails():
    data = VALID_PROBES.copy()
    data["scrape_configs"][0]["static_configs"] = [{"targets": []}]

    with pytest.raises(ValidationError):
        ProbesFile(**data)


def test_missing_scrape_configs_fails():
    with pytest.raises(ValidationError):
        ProbesFile(**{})
