import pytest

from pathlib import Path

from commodore import refs
from commodore.config import Config


@pytest.fixture
def inventory():
    """
    Setup test inventory
    """

    kapitan = {
        "secrets": {
            "vaultkv": {
                "VAULT_ADDR": "https://vault.example.com",
                "VAULT_CAPATH": "/etc/ssl/certs/",
                "VAULT_SKIP_VERIFY": "false",
                "auth": "token",
                "engine": "kv-v2",
                "mount": "clusters/kv",
            }
        },
    }

    return {
        "cluster": {
            "parameters": {
                "_instance": "cluster",
                "test": {
                    "accesskey": "?{vaultkv:t-tenant/c-cluster/test/cluster-accesskey}",
                    "secretkey": "?{vaultkv:t-tenant/c-cluster/test/cluster-secretkey}",
                    "config": "something else",
                    "params": {
                        "env": [
                            {"key": "envA", "value": "valA"},
                            {"key": "envB", "value": "valB"},
                        ],
                        "complex": True,
                    },
                },
                "non_component": {
                    "password": "?{vaultkv:t-tenant/c-cluster/global/password}",
                },
                "other_component": {
                    "enabled": True,
                    "thesecret": "?{vaultkv:t-tenant/c-cluster/other-component/thesecret}",
                    "users": ["user1", "user2"],
                },
                "kapitan": kapitan,
            },
        },
        "test-a": {
            "parameters": {
                "_instance": "test-a",
                "test": {
                    "accesskey": "?{vaultkv:t-tenant/c-cluster/test/test-a-accesskey}",
                    "secretkey": "?{vaultkv:t-tenant/c-cluster/test/test-a-secretkey}",
                    "config": "something else",
                    "params": {
                        "env": [
                            {"key": "envA", "value": "valA"},
                            {"key": "envB", "value": "valB"},
                        ],
                        "complex": True,
                    },
                },
                "non_component": {
                    "password": "?{vaultkv:t-tenant/c-cluster/global/password}",
                },
                "other_component": {
                    "enabled": True,
                    "thesecret": "?{vaultkv:t-tenant/c-cluster/other-component/thesecret}",
                    "users": ["user1", "user2"],
                },
                "kapitan": kapitan,
            },
        },
        "test-b": {
            "parameters": {
                "_instance": "test-b",
                "test": {
                    "accesskey": "?{vaultkv:t-tenant/c-cluster/test/test-b-accesskey}",
                    "secretkey": "?{vaultkv:t-tenant/c-cluster/test/test-b-secretkey}",
                    "config": "something else",
                    "params": {
                        "env": [
                            {"key": "envA", "value": "valA"},
                            {"key": "envB", "value": "valB"},
                        ],
                        "complex": True,
                    },
                },
                "non_component": {
                    "password": "?{vaultkv:t-tenant/c-cluster/global/password}",
                },
                "other_component": {
                    "enabled": True,
                    "thesecret": "?{vaultkv:t-tenant/c-cluster/other-component/thesecret}",
                    "users": ["user1", "user2"],
                },
                "kapitan": kapitan,
            },
        },
        "other-component": {
            "parameters": {
                "_instance": "other-component",
                "test": {
                    "accesskey": "?{vaultkv:t-tenant/c-cluster/test/other-component-accesskey}",
                    "secretkey": "?{vaultkv:t-tenant/c-cluster/test/other-component-secretkey}",
                    "config": "something else",
                    "params": {
                        "env": [
                            {"key": "envA", "value": "valA"},
                            {"key": "envB", "value": "valB"},
                        ],
                        "complex": True,
                    },
                },
                "non_component": {
                    "password": "?{vaultkv:t-tenant/c-cluster/global/password}",
                },
                "other_component": {
                    "enabled": True,
                    "thesecret": "?{vaultkv:t-tenant/c-cluster/other-component/thesecret}",
                    "users": ["user1", "user2"],
                },
                "kapitan": kapitan,
            },
        },
    }


@pytest.fixture
def config(tmp_path: Path):
    """
    Setup test config
    """
    c = Config(work_dir=tmp_path)
    aliases = {
        "other-component": "other-component",
        "test-a": "test",
        "test-b": "test",
    }
    c.register_component_aliases(aliases)
    return c


def test_update_refs(tmp_path: Path, config, inventory):
    aliases = config.get_component_aliases()
    refs.update_refs(config, aliases, inventory)
    ref_prefix = config.refs_dir / "t-tenant" / "c-cluster"
    expected_refs = [
        Path("other-component/thesecret"),
        Path("test/test-a-accesskey"),
        Path("test/test-a-secretkey"),
        Path("test/test-b-accesskey"),
        Path("test/test-b-secretkey"),
        Path("global/password"),
    ]
    for ref in expected_refs:
        refpath = ref_prefix / ref
        assert refpath.is_file()

    not_expected_refs = [
        Path("test/cluster-accesskey"),
        Path("test/cluster-secretkey"),
        Path("test/other-component-accesskey"),
        Path("test/other-component-secretkey"),
    ]
    for ref in not_expected_refs:
        refpath = ref_prefix / ref
        assert not refpath.exists()
