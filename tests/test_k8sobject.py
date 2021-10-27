import pytest

from commodore import k8sobject

_test_objs = [
    {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": "test",
            "namespace": "test",
        },
    },
    {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": "test-sa-2",
            "namespace": "test",
        },
    },
    {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "test",
            "namespace": "test",
            "labels": {
                "name": "test",
            },
        },
        "spec": {
            "image": "image",
            "command": "pause",
        },
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": "test-role",
            "namespace": "test",
        },
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {
            "name": "test-role",
            "namespace": "test-2",
        },
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {
            "name": "test-cr",
        },
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {
            "name": "test-cr-2",
        },
    },
    {
        "test": "testing",
    },
]


@pytest.mark.parametrize(
    "k8sdict,expected",
    zip(
        [None] + _test_objs,
        [
            {
                "kind": "",
                "name": "",
                "namespace": "",
            },
            {
                "kind": "ServiceAccount",
                "name": "test",
                "namespace": "test",
            },
            {
                "kind": "ServiceAccount",
                "name": "test-sa-2",
                "namespace": "test",
            },
            {
                "kind": "Pod",
                "name": "test",
                "namespace": "test",
            },
            {
                "kind": "Role",
                "name": "test-role",
                "namespace": "test",
                "spec": {
                    "test": "testing",
                },
            },
            {
                "kind": "Role",
                "name": "test-role",
                "namespace": "test-2",
                "spec": {
                    "test": "testing2",
                },
            },
            {
                "kind": "ClusterRole",
                "namespace": "",
                "name": "test-cr",
            },
            {
                "kind": "ClusterRole",
                "namespace": "",
                "name": "test-cr-2",
            },
            {
                "name": "",
                "namespace": "",
                "kind": "",
            },
        ],
    ),
)
def test_k8sobject_constructor(k8sdict, expected):
    o = k8sobject.K8sObject(k8sdict)
    assert expected["kind"] == o._kind
    assert expected["name"] == o._name
    assert expected["namespace"] == o._namespace


_cluster_scoped_obj = k8sobject.K8sObject(
    {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": "test",
            "labels": {
                "name": "test",
            },
        },
    }
)
_ns_scoped_obj = k8sobject.K8sObject(
    {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {
            "name": "test",
            "labels": {
                "name": "test",
            },
        },
    }
)


@pytest.mark.parametrize(
    "k8sdict,to_cluster_scoped,to_ns_scoped",
    zip(
        _test_objs,
        [False, False, False, False, False, True, True, True],
        [False, False, True, True, True, True, True, True],
    ),
)
def test_k8sobject_less_than(k8sdict, to_cluster_scoped, to_ns_scoped):
    o = k8sobject.K8sObject(k8sdict)
    assert (o < _cluster_scoped_obj) == to_cluster_scoped
    assert (o < _ns_scoped_obj) == to_ns_scoped
    assert (o > _cluster_scoped_obj) == (not to_cluster_scoped)
    assert (o > _ns_scoped_obj) == (not to_ns_scoped)


@pytest.mark.parametrize("k8sdict_a", _test_objs)
@pytest.mark.parametrize("k8sdict_b", _test_objs)
def test_k8sobject_equal(k8sdict_a, k8sdict_b):
    a = k8sobject.K8sObject(k8sdict_a)
    b = k8sobject.K8sObject(k8sdict_b)
    expect = False
    if (
        k8sdict_a.get("kind", "") == k8sdict_b.get("kind", "")
        and k8sdict_a.get("metadata", {}).get("namespace", "")
        == k8sdict_b.get("metadata", {}).get("namespace", "")
        and k8sdict_a.get("metadata", {}).get("name", "")
        == k8sdict_b.get("metadata", {}).get("name", "")
    ):
        expect = True
    assert (a == b) == expect
