import json, os
from .helpers import clean, api_request, fetch_git_repository

def fetch_inventory(cfg, customer, cluster):
    return api_request(cfg.api_url, 'inventory', customer, cluster)

def fetch_config(cfg, response):
    config = response['global']['config']
    print(f"Updating global config...")
    fetch_git_repository(f"{cfg.global_git_base}/{config}.git", f"inventory/classes/global")

def fetch_component(cfg, component):
    repository_url = f"{cfg.global_git_base}/components/{component}.git"
    target_directory = f"dependencies/{component}"
    fetch_git_repository(repository_url, target_directory)
    os.symlink(os.path.abspath(f"{target_directory}/class/{component}.yml"), f"inventory/classes/components/{component}.yml")

def fetch_components(cfg, response):
    components = response['global']['components']
    os.makedirs('inventory/classes/components', exist_ok=True)
    for c in components:
        print(f"Updating component {c}...")
        fetch_component(cfg, c)

def fetch_target(cfg, customer, cluster):
    return api_request(cfg.api_url, 'targets', customer, cluster)

def fetch_customer_config(cfg, repo, customer):
    if repo is None:
        repo = f"{cfg.customer_git_base}/{customer}.git"
    print("Updating customer config...")
    fetch_git_repository(repo, f"inventory/classes/{customer}")

def clean():
    import shutil
    shutil.rmtree("inventory", ignore_errors=True)
    shutil.rmtree("dependencies", ignore_errors=True)
    shutil.rmtree("compiled", ignore_errors=True)

def kapitan_compile():
    # TODO: maybe use kapitan.targets.compile_targets directly?
    import shlex, subprocess
    subprocess.run(shlex.split("kapitan compile"))

def compile(config, customer, cluster):
    clean()

    r = fetch_inventory(config, customer, cluster)

    # Fetch all Git repos
    fetch_config(config, r)
    fetch_components(config, r)
    fetch_customer_config(config, r['cluster'].get('override', None), customer)

    target = fetch_target(config, customer, cluster)
    os.makedirs('inventory/targets', exist_ok=True)
    with open(f"inventory/targets/{target['target']}.yml", 'w') as tgt:
        json.dump(target['contents'], tgt)

    kapitan_compile()
