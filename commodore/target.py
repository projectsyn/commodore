import click, os

from .helpers import (
        api_request,
        ApiError,
        yaml_dump
    )

def fetch_target(cfg, customer, cluster):
    return api_request(cfg.api_url, 'targets', customer, cluster)

def _full_target(customer, cluster, apidata):
    cloud_type = apidata['cloud_type']
    cloud_region = apidata['cloud_region']
    cluster_distro = apidata['cluster_distribution']
    return {
        'classes': [
            'global.common',
            f"global.{cloud_type}",
            f"global.{cluster_distro}",
            f"{customer}.{cluster}"
        ],
        'parameters': {
            'target_name': 'cluster',
            'cluster': {
                'name': f"{cluster}",
                'dist': f"{cluster_distro}"
            },
            'cloud': {
                'type': f"{cloud_type}",
                'region': f"{cloud_region}"
            },
            'customer': {
                'name': f"{customer}"
            },
            'kapitan': {
                'secrets': {
                    'vaultkv': {
                        'auth': 'token',
                        'engine': 'kv-v2',
                        'mount': 'kv',
                        'VAULT_ADDR': 'http://vault.syn-vault.svc:8200',
                        'VAULT_SKIP_VERIFY': 'true'
                    }
                }
            }
        }
    }

def update_target(cfg, customer, cluster):
    click.secho('Updating Kapitan target...', bold=True)
    try:
        target = fetch_target(cfg, customer, cluster)
    except ApiError as e:
        raise click.ClickException(f"While fetching target: {e}") from e

    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(customer, cluster, target),
            'inventory/targets/cluster.yml')

    return 'cluster'
