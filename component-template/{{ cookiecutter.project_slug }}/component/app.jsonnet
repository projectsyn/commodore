local kap = import 'lib/kapitan.libjsonnet';
local inv = kap.inventory();
local params = inv.parameters.{{ cookiecutter.component_param_key }};
local argocd = import 'lib/argocd.libjsonnet';

local app = argocd.App('{{ cookiecutter.component }}', params.namespace);

{
  '{{ cookiecutter.component }}': app,
}
